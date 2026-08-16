import asyncio
import base64
import json
import random
import uuid
from io import BytesIO
from typing import Any

import botpy.message
from botpy.http import Route
from botpy.interaction import Interaction
from botpy.types.inline import (
    Action,
    Button,
    Keyboard,
    KeyboardRow,
    Permission,
    RenderData,
)
from botpy.types.message import KeyboardPayload, MarkdownPayload
from PIL import Image as PILImage

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.core.message.components import File, Image, Plain, Record
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
from astrbot.core.platform.sources.qqofficial.qqofficial_message_event import (
    QQOfficialMessageEvent,
)
from astrbot.core.platform.sources.qqofficial.qqofficial_platform_adapter import (
    QQOfficialPlatformAdapter,
)
from astrbot.core.star.context import Context

from .config import PluginConfig
from .downloader import Downloader
from .lyrics_renderer import LyricsRenderer
from .model import Song
from .platform import BaseMusicPlayer, TXQQMusic
from .song_renderer import CardRenderer
from .card_sender import send_card_via_cz


class MusicSender:
    def __init__(
        self,
        config: PluginConfig,
        context: Context,
        lyrics_renderer: LyricsRenderer,
        downloader: Downloader,
        song_renderer: CardRenderer,
    ):
        self.cfg = config
        self.context = context
        self.lyrics_renderer = lyrics_renderer
        self.downloader = downloader
        self.song_renderer = song_renderer
        self._selection_message_ids: dict[str, str | int] = {}
        self._selection_contexts: dict[str, dict[str, Any]] = {}
        self._selection_context_ids: dict[str, str] = {}
        self._interaction_clients: set[int] = set()
        self.interaction_created: bool = False

    def set_interaction_create(self):
        if self.interaction_created:
            return
        for platform in self.context.platform_manager.get_insts():
            if not isinstance(platform, QQOfficialPlatformAdapter):
                continue
            client = platform.get_client()
            client_id = id(client)
            if client_id in self._interaction_clients:
                continue
            intents = getattr(client, "intents", None)
            if isinstance(intents, int):
                client.intents = intents | (1 << 25) | (1 << 26)
            elif intents is not None:
                intents.interaction = True

            previous_handler = getattr(client, "on_interaction_create", None)

            async def on_interaction_create(
                interaction: Interaction,
                previous_handler=previous_handler,
            ):
                if await self.handle_interaction(interaction):
                    return
                if previous_handler is not None:
                    await previous_handler(interaction)

            setattr(client, "on_interaction_create", on_interaction_create)
            self._interaction_clients.add(client_id)
        self.interaction_created = True

    @staticmethod
    def _format_time(duration_ms):
        duration = duration_ms // 1000

        hours = duration // 3600
        minutes = (duration % 3600) // 60
        seconds = duration % 60

        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes:02d}:{seconds:02d}"

    async def _recall_qqofficial_message(
        self, event: QQOfficialMessageEvent, message_id: str
    ) -> None:
        source = event.message_obj.raw_message
        route_path = None
        route_params = {}

        if isinstance(source, botpy.message.GroupMessage):
            route_path = "/v2/groups/{group_openid}/messages/{message_id}"
            route_params["group_openid"] = source.group_openid
        elif isinstance(source, botpy.message.C2CMessage):
            route_path = "/v2/users/{openid}/messages/{message_id}"
            route_params["openid"] = source.author.user_openid
        elif isinstance(source, botpy.message.DirectMessage):
            route_path = "/dms/{guild_id}/messages/{message_id}"
            route_params["guild_id"] = source.guild_id
        elif isinstance(source, botpy.message.Message):
            await event.bot.api.recall_message(
                channel_id=source.channel_id,
                message_id=message_id,
            )
            return

        if route_path:
            await event.bot.api._http.request(
                Route(
                    "DELETE",
                    route_path,
                    message_id=message_id,
                    **route_params,
                )
            )

    @staticmethod
    def _make_selection_key(event: AstrMessageEvent) -> str:
        return f"{event.unified_msg_origin}:{event.get_sender_id()}"

    def clear_selection_context(self, event: AstrMessageEvent) -> None:
        """Remove the active selection context for an event.

        Args:
            event: The event whose song selection has finished.
        """
        selection_key = self._make_selection_key(event)
        selection_id = self._selection_context_ids.pop(selection_key, None)
        if selection_id:
            self._selection_contexts.pop(selection_id, None)

    async def _recall_selection_message(self, event: AstrMessageEvent) -> None:
        key = self._make_selection_key(event)
        message_id = self._selection_message_ids.pop(key, None)
        if message_id is None:
            return

        try:
            if isinstance(event, AiocqhttpMessageEvent):
                await event.bot.delete_msg(message_id=int(message_id))
            elif isinstance(event, QQOfficialMessageEvent):
                await self._recall_qqofficial_message(event, str(message_id))
        except Exception as e:
            logger.warning(f"Failed to recall song selection message: {e}")

    async def handle_interaction(self, interaction: Any) -> bool:
        resolved = getattr(getattr(interaction, "data", None), "resolved", None)
        if not getattr(resolved, "button_id", "").startswith("music_song_selection_"):
            return False

        await interaction._api.on_interaction_result(interaction.id, 0)
        button_data = getattr(resolved, "button_data", "") or ""
        try:
            payload = json.loads(button_data)
        except (json.JSONDecodeError, TypeError):
            return True
        if not isinstance(payload, dict):
            return True

        selection_id = str(payload.get("selection_id") or "")
        try:
            index = int(payload.get("index"))  # type: ignore
        except (TypeError, ValueError):
            return True
        context = self._selection_contexts.get(selection_id)
        if context is None or context.get("handled"):
            return True

        event = context["event"]
        selection_key = self._make_selection_key(event)
        if self._selection_context_ids.get(selection_key) != selection_id:
            return True

        context["handled"] = True
        songs = context["songs"]
        if index < 1 or index > len(songs):
            return True
        self.clear_selection_context(event)
        asyncio.create_task(
            self.send_song(
                event,
                context["player"],
                songs[index - 1],
            )
        )
        return True

    async def _build_cover_map(
        self, cover_urls: list[str]
    ) -> dict[str, PILImage.Image]:
        cover_map: dict[str, PILImage.Image] = {}
        for cover_url in dict.fromkeys(cover_urls):
            try:
                data = await self.downloader.download_image(cover_url, close_ssl=False)
                if not data:
                    continue
                image = PILImage.open(BytesIO(data)).convert("RGB")
                cover_map[cover_url] = image
            except Exception as e:
                logger.warning(f"封面下载失败: {cover_url}, {e}")
        return cover_map

    @staticmethod
    async def send_msg(event: AiocqhttpMessageEvent, payloads: dict) -> int | None:
        if event.is_private_chat():
            payloads["user_id"] = event.get_sender_id()
            result = await event.bot.api.call_action("send_private_msg", **payloads)
        else:
            payloads["group_id"] = event.get_group_id()
            result = await event.bot.api.call_action("send_group_msg", **payloads)
        return result.get("message_id")

    async def _send_song_selection_text(
        self,
        event: AstrMessageEvent,
        songs: list[Song],
        player: BaseMusicPlayer,
    ) -> str | int | None:
        lins = [f"【{player.platform.display_name}】"]
        for index, song in enumerate(songs):
            lins.append(f"{index + 1}. {song.title} - {song.artists}")
        msg = "\n".join(lins)
        message_id: str | int | None = None
        if isinstance(event, AiocqhttpMessageEvent):
            payloads = {"message": [{"type": "text", "data": {"text": msg}}]}
            message_id = await self.send_msg(event, payloads)
        elif isinstance(event, QQOfficialMessageEvent):
            platform = getattr(event.bot, "platform", None)
            if platform is not None:
                await platform.send_by_session(
                    event.session,
                    MessageChain(chain=[Plain(text=msg)]),
                )
                message_id = getattr(platform, "_session_last_message_id", {}).get(
                    event.session_id
                )
            else:
                await event.send(event.plain_result(msg))
        else:
            await event.send(event.plain_result(msg))

        if message_id is not None:
            key = self._make_selection_key(event)
            self._selection_message_ids[key] = message_id
        return message_id

    async def _send_song_selection_button(
        self,
        event: QQOfficialMessageEvent,
        songs: list[Song],
        player: BaseMusicPlayer,
    ) -> str | None:
        self.set_interaction_create()
        selection_id = uuid.uuid4().hex
        selection_context = {
            "event": event,
            "songs": songs,
            "player": player,
            "handled": False,
        }
        self._selection_contexts[selection_id] = selection_context
        self._selection_context_ids[self._make_selection_key(event)] = selection_id

        buttons = []
        for index, song in enumerate(songs, 1):
            song_info = f"{song.name} - {song.artists}"
            button_data = json.dumps(
                {"selection_id": selection_id, "index": index},
                ensure_ascii=False,
                separators=(",", ":"),
            )
            buttons.append(
                Button(
                    id=f"music_song_selection_{index}",
                    render_data=RenderData(
                        label=f"{index}. {song_info}",
                        visited_label=f"正在发送“{song_info}”...",
                        style=1,
                    ),
                    action=Action(
                        type=1,
                        permission=Permission(
                            type=0,
                            specify_role_ids=[],
                            specify_user_ids=[event.get_sender_id()],
                        ),
                        click_limit=1,
                        data=button_data,
                        at_bot_show_channel_list=False,
                    ),
                )
            )

        keyboard = Keyboard(rows=[KeyboardRow(buttons=[button]) for button in buttons])
        title = f"【{player.platform.display_name}】"
        markdown = MarkdownPayload(content=f"### {title}请选歌：")
        keyboard_payload = KeyboardPayload(content=keyboard)
        source = event.message_obj.raw_message
        result = None

        if isinstance(source, botpy.message.GroupMessage):
            result = await event.bot.api.post_group_message(
                group_openid=source.group_openid,  # type: ignore
                msg_type=2,
                markdown=markdown,
                keyboard=keyboard_payload,  # type: ignore[arg-type]
                msg_id=source.id,
            )
        elif isinstance(source, botpy.message.C2CMessage):
            result = await event.post_c2c_message(
                openid=source.author.user_openid,
                msg_type=2,
                markdown=markdown,
                keyboard=keyboard_payload,  # type: ignore[arg-type]
                msg_id=source.id,
            )
        elif isinstance(source, botpy.message.DirectMessage):
            result = await event.bot.api.post_dms(
                guild_id=source.guild_id,
                markdown=markdown,
                keyboard=keyboard_payload,  # type: ignore[arg-type]
                msg_id=source.id,
            )
        elif isinstance(source, botpy.message.Message):
            result = await event.bot.api.post_message(
                channel_id=source.channel_id,
                markdown=markdown,
                keyboard=keyboard_payload,  # type: ignore[arg-type]
                msg_id=source.id,
            )
        else:
            raise ValueError(f"Unsupported QQ message type: {type(source).__name__}")

        if result is None:
            raise RuntimeError("QQ API returned no message for song selection")
        message_id = (
            result.get("id")
            if isinstance(result, dict)
            else getattr(result, "id", None)
        )
        if message_id is None:
            raise RuntimeError("QQ API response has no message ID")
        key = self._make_selection_key(event)
        self._selection_message_ids[key] = message_id
        return str(message_id)

    async def _send_song_selection_image(
        self,
        event: AstrMessageEvent,
        songs: list[Song],
        player: BaseMusicPlayer | None = None,
    ) -> str | int | None:
        song_items = []
        cover_urls: list[str] = []
        for song in songs:
            if player and (not song.cover_url or not song.audio_url):
                song = await player.fetch_extra(song)
            song_items.append(song)
            if song.cover_url:
                cover_urls.append(song.cover_url)

        cover_map = await self._build_cover_map(cover_urls)
        image_bytes = await self.song_renderer.render_song_list_image(
            song_items, cover_map
        )

        if isinstance(event, AiocqhttpMessageEvent):
            payloads = {
                "message": [
                    {
                        "type": "image",
                        "data": {
                            "file": f"base64://{base64.b64encode(image_bytes).decode()}",
                        },
                    }
                ]
            }
            message_id = await self.send_msg(event, payloads)
        elif isinstance(event, QQOfficialMessageEvent):
            platform = getattr(event.bot, "platform", None)
            if platform is not None:
                await platform.send_by_session(
                    event.session,
                    MessageChain(chain=[Image.fromBytes(image_bytes)]),
                )
                message_id = getattr(platform, "_session_last_message_id", {}).get(
                    event.session_id
                )
            else:
                await event.send(MessageChain(chain=[Image.fromBytes(image_bytes)]))
                message_id = None
        else:
            await event.send(MessageChain(chain=[Image.fromBytes(image_bytes)]))
            message_id = None

        if message_id is not None:
            key = self._make_selection_key(event)
            self._selection_message_ids[key] = message_id
        return message_id

    async def send_song_selection(
        self,
        event: AstrMessageEvent,
        songs: list[Song],
        player: BaseMusicPlayer,
    ) -> str | None:
        for mode in self.cfg.real_select_modes:
            try:
                if mode == "button":
                    if not isinstance(event, QQOfficialMessageEvent):
                        continue
                    await self._send_song_selection_button(event, songs, player)
                    return mode
                if mode == "image":
                    await self._send_song_selection_image(
                        event=event, songs=songs, player=player
                    )
                    return mode
                if mode == "text":
                    await self._send_song_selection_text(event, songs, player)
                    return mode
                if mode != "single":
                    logger.warning(f"Unknown song selection mode: {mode}")
            except Exception as e:
                logger.warning(f"Song selection mode '{mode}' failed: {e}")

        logger.error("All configured song selection modes failed")
        return None

    async def _send_card(
        self, event: AiocqhttpMessageEvent, player: BaseMusicPlayer, song: Song
    ) -> bool:
        """发卡片 — 通过 CZ API 签名 Ark JSON 发送"""
        ckey = getattr(self.cfg, "qingmeng_ckey", "") or ""
        return await send_card_via_cz(event, player, song, ckey)

    async def _send_record_link(
        self, event: AstrMessageEvent, player: BaseMusicPlayer, song: Song
    ) -> bool:
        if not song.audio_url:
            return False
        try:
            seg = Record.fromURL(song.audio_url)
            await event.send(event.chain_result([seg]))
            return True
        except Exception as e:
            logger.error(f"Record link send failed: {e}")
            return False

    async def _send_record_local(
        self, event: AstrMessageEvent, player: BaseMusicPlayer, song: Song
    ) -> bool:
        if not song.audio_url:
            return False

        file_path = await self.downloader.download_song(song.audio_url)
        if not file_path:
            logger.error(f"【{song.name}】下载失败")
            return False

        try:
            seg = Record.fromFileSystem(str(file_path.resolve()))
            await event.send(event.chain_result([seg]))
            return True
        except Exception as e:
            logger.error(f"Local voice send failed: {e}")
            return False

    async def _send_file_link(
        self, event: AstrMessageEvent, player: BaseMusicPlayer, song: Song
    ) -> bool:
        if not song.audio_url:
            return False
        try:
            file_name_url = f"{song.name}_{song.artists}.mp3"
            seg_url = File(name=file_name_url, url=song.audio_url)
            await event.send(event.chain_result([seg_url]))
            return True
        except Exception as e_url:
            logger.error(f"File link send failed: {e_url}")
            return False

    async def _send_file_local(
        self, event: AstrMessageEvent, player: BaseMusicPlayer, song: Song
    ) -> bool:
        if not song.audio_url:
            return False

        file_path = await self.downloader.download_song(song.audio_url)
        if not file_path:
            logger.error(f"【{song.name}】下载失败")
            return False

        try:
            file_name = f"{song.name}_{song.artists}{file_path.suffix}"
            seg = File(name=file_name, file=str(file_path.resolve()))
            await event.send(event.chain_result([seg]))
            return True
        except Exception as e:
            logger.error(f"Local file send failed: {e}")
            return False

    async def _send_text(
        self, event: AstrMessageEvent, player: BaseMusicPlayer, song: Song
    ) -> bool:
        """发文本"""
        try:
            info = f"🎶{song.name} - {song.artists} {self._format_time(song.duration)}"
            song = await player.fetch_extra(song)
            info = song.to_lines()
            await event.send(event.plain_result(info))
            return True
        except Exception as e:
            logger.error(f"发送歌曲信息失败: {e}")
            return False

    async def send_comment(
        self, event: AstrMessageEvent, player: BaseMusicPlayer, song: Song
    ) -> bool:
        """发评论"""
        if not song.comments:
            await player.fetch_comments(song)
        if not song.comments:
            # 没有评论
            return False
        try:
            content = random.choice(song.comments).get("content")
            await event.send(event.plain_result(content))
            return True
        except Exception:
            return False

    async def send_lyrics(
        self, event: AstrMessageEvent, player: BaseMusicPlayer, song: Song
    ) -> bool:
        """发歌词"""
        if not song.lyrics:
            await player.fetch_lyrics(song)
        if song.lyrics:
            await player.resolve_lyrics(song)
        if not song.lyrics:
            logger.error(f"【{song.name}】歌词获取失败")
            return False
        try:
            image = self.lyrics_renderer.draw_lyrics(song.lyrics)
            await event.send(MessageChain(chain=[Image.fromBytes(image)]))
            return True
        except Exception as e:
            logger.error(f"【{song.name}】歌词渲染/发送失败: {e}")
            return False

    def _get_sender(self, mode: str):
        return {
            "card": self._send_card,
            "record_link": self._send_record_link,
            "record_local": self._send_record_local,
            "file_link": self._send_file_link,
            "file_local": self._send_file_local,
            "text": self._send_text,
        }.get(mode)

    def _is_mode_supported(self, mode: str, event: AstrMessageEvent) -> bool:
        platform = event.get_platform_name()
        match mode:
            case "text":
                return True
            case "card":
                return platform == "aiocqhttp"
            case "record_link" | "record_local":
                return platform not in self.cfg.record_unsupported
            case "file_link" | "file_local":
                return platform not in self.cfg.file_unsupported
            case _:
                return False

    async def send_song(
        self,
        event: AstrMessageEvent,
        player: BaseMusicPlayer,
        song: Song,
        modes: list[str] | None = None,
    ):
        logger.debug(
            f"{event.get_sender_name()}（{event.get_sender_id()}）点歌："
            f"{player.platform.display_name} -> {song.name}_{song.artists}"
        )

        if not song.audio_url:
            song = await player.fetch_extra(song)
        if not song.audio_url:
            await event.send(event.plain_result(f"【{song.name}】音频获取失败"))
            return

        sent = False
        target_modes = modes if modes is not None else self.cfg.real_send_modes

        for mode in target_modes:
            if not self._is_mode_supported(mode, event):
                logger.debug(f"{mode} 不支持，跳过")
                continue

            sender = self._get_sender(mode)
            if not sender:
                continue

            try:
                ok = await sender(event, player, song)
            except Exception as e:
                logger.error(f"{mode} 发送异常: {e}")
                ok = False

            if ok:
                logger.debug(f"{mode} 发送成功")
                sent = True
                break
            else:
                logger.debug(f"{mode} 发送失败，尝试下一种")

        if not sent:
            await event.send(event.plain_result("歌曲发送失败"))
            return

        self.clear_selection_context(event)
        if self.cfg.recall_select:
            await self._recall_selection_message(event)

        if self.cfg.enable_comments:
            await self.send_comment(event, player, song)

        if self.cfg.enable_lyrics:
            await self.send_lyrics(event, player, song)
