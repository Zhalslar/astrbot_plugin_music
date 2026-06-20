import base64
import random
from io import BytesIO

from PIL import Image as PILImage

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.core.message.components import File, Image, Record
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)

from .config import PluginConfig
from .downloader import Downloader
from .lyrics_renderer import LyricsRenderer
from .model import Song
from .platform import BaseMusicPlayer, TXQQMusic
from .song_renderer import VideoCardRenderer


class MusicSender:
    def __init__(
        self,
        config: PluginConfig,
        lyrics_renderer: LyricsRenderer,
        downloader: Downloader,
        song_renderer: VideoCardRenderer,
    ):
        self.cfg = config
        self.lyrics_renderer = lyrics_renderer
        self.downloader = downloader
        self.song_renderer = song_renderer

    @staticmethod
    def _format_time(duration_ms):
        """格式化歌曲时长"""
        duration = duration_ms // 1000

        hours = duration // 3600
        minutes = (duration % 3600) // 60
        seconds = duration % 60

        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes:02d}:{seconds:02d}"

    @staticmethod
    async def send_msg(event: AiocqhttpMessageEvent, payloads: dict) -> int | None:
        if event.is_private_chat():
            payloads["user_id"] = event.get_sender_id()
            result = await event.bot.api.call_action("send_private_msg", **payloads)
        else:
            payloads["group_id"] = event.get_group_id()
            result = await event.bot.api.call_action("send_group_msg", **payloads)
        return result.get("message_id")

    async def send_song_selection(
        self,
        event: AstrMessageEvent,
        songs: list[Song],
        title: str | None = None,
        player: BaseMusicPlayer | None = None,
    ) -> int | None:
        """
        发送歌曲选择
        """
        if self.cfg.select_mode == "image":
            return await self._send_song_selection_image(
                event=event, songs=songs, player=player
            )

        formatted_songs = [
            f"{index + 1}. {song.name} - {song.artists}"
            for index, song in enumerate(songs)
        ]
        if title:
            formatted_songs.insert(0, title)

        msg = "\n".join(formatted_songs)
        if isinstance(event, AiocqhttpMessageEvent):
            payloads = {"message": [{"type": "text", "data": {"text": msg}}]}
            return await self.send_msg(event, payloads)

        await event.send(event.plain_result(msg))
        return None

    async def _send_song_selection_image(
        self,
        event: AstrMessageEvent,
        songs: list[Song],
        player: BaseMusicPlayer | None = None,
    ) -> int | None:
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
            return await self.send_msg(event, payloads)

        await event.send(MessageChain(chain=[Image.fromBytes(image_bytes)]))
        return None

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

    async def send_card(
        self, event: AiocqhttpMessageEvent, player: BaseMusicPlayer, song: Song
    ) -> bool:
        """发卡片"""
        if isinstance(player, TXQQMusic):
            if not song.audio_url or not song.cover_url:
                song = await player.fetch_extra(song)

            payloads: dict = {
                "message": [
                    {
                        "type": "music",
                        "data": {
                            "type": "custom",
                            "url": song.audio_url or "",
                            "audio": song.audio_url or "",
                            "title": song.name or "",
                            "image": song.cover_url or "",
                            "singer": song.artists or "",
                        },
                    }
                ]
            }
        else:
            payloads = {
                "message": [
                    {
                        "type": "music",
                        "data": {
                            "type": "163",
                            "id": song.id,
                        },
                    }
                ]
            }
        try:
            await self.send_msg(event, payloads)
            return True
        except Exception as e:
            logger.error(e)
            await event.send(event.plain_result(str(e)))
            return False

    async def send_record(
        self, event: AstrMessageEvent, player: BaseMusicPlayer, song: Song
    ) -> bool:
        """发语音"""
        if not song.audio_url:
            song = await player.fetch_extra(song)
        if not song.audio_url:
            await event.send(event.plain_result(f"【{song.name}】音频获取失败"))
            return False
        try:
            logger.debug(f"正在发送【{song.name}】音频: {song.audio_url}")
            seg = Record.fromURL(song.audio_url)
            await event.send(event.chain_result([seg]))
            return True
        except Exception as e:
            logger.error(f"【{song.name}】音频发送失败: {e}")
            return False

    async def send_file(
        self, event: AstrMessageEvent, player: BaseMusicPlayer, song: Song
    ):
        """发文件"""
        if not song.audio_url:
            song = await player.fetch_extra(song)
        if not song.audio_url:
            await event.send(event.plain_result(f"【{song.name}】音频获取失败"))
            return False

        file_path = await self.downloader.download_song(song.audio_url)

        async def send_by_url():
            try:
                # 默认使用 mp3 后缀
                file_name_url = f"{song.name}_{song.artists}.mp3"
                if song.audio_url:
                    seg_url = File(name=file_name_url, url=song.audio_url)
                    await event.send(event.chain_result([seg_url]))
                    return True
            except Exception as e_url:
                logger.error(f"URL 发送失败: {e_url}")
                return False

        if not file_path:
            logger.warning(f"【{song.name}】下载失败，尝试直接发送 URL")
            if await send_by_url():
                return True
            await event.send(
                event.plain_result(f"【{song.name}】音频文件下载和发送均失败")
            )
            return False

        try:
            file_name = f"{song.name}_{song.artists}{file_path.suffix}"
            seg = File(name=file_name, file=str(file_path.resolve()))
            await event.send(event.chain_result([seg]))
            return True
        except Exception as e:
            logger.warning(f"【{song.name}】本地文件发送失败: {e}，尝试直接发送 URL")
            if await send_by_url():
                return True

            await event.send(
                event.plain_result(f"【{song.name}】音频文件发送失败: {e}")
            )
            return False

    async def send_text(
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

    def _get_sender(self, mode: str):
        return {
            "card": self.send_card,
            "record": self.send_record,
            "file": self.send_file,
            "text": self.send_text,
        }.get(mode)

    def _is_mode_supported(self, mode: str, event: AstrMessageEvent) -> bool:
        platform = event.get_platform_name()
        match mode:
            case "text":
                return True
            case "card":
                return platform == "aiocqhttp"
            case "record":
                return platform in self.cfg.record_supported
            case "file":
                return platform in self.cfg.file_supported
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

        # 附加内容不影响主流程
        if sent and self.cfg.enable_comments:
            await self.send_comment(event, player, song)

        if sent and self.cfg.enable_lyrics:
            await self.send_lyrics(event, player, song)
