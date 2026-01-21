
import asyncio
import random

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.core.message.components import File, Image, Record
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)

from .config import PluginConfig
from .downloader import Downloader
from .model import Song
from .platform import BaseMusicPlayer, NetEaseMusic, NetEaseMusicNodeJS
from .renderer import MusicRenderer


class MusicSender:
    def __init__(
        self, config: PluginConfig, renderer: MusicRenderer, downloader: Downloader
    ):
        self.cfg = config
        self.renderer = renderer
        self.downloader = downloader

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
        self, event: AstrMessageEvent, songs: list[Song], title: str | None = None
    ) -> None:
        """
        发送歌曲选择
        """
        formatted_songs = [
            f"{index + 1}. {song.name} - {song.artists}"
            for index, song in enumerate(songs)
        ]
        if title:
            formatted_songs.insert(0, title)

        msg = "\n".join(formatted_songs)
        if isinstance(event, AiocqhttpMessageEvent):
            payloads = {"message": [{"type": "text", "data": {"text": msg}}]}
            message_id = await self.send_msg(event, payloads)
            if message_id and self.cfg.timeout_recall:
                await asyncio.sleep(self.cfg.timeout)
                await event.bot.delete_msg(message_id=message_id)
        else:
            await event.send(event.plain_result(msg))

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
        if not song.lyrics:
            logger.error(f"【{song.name}】歌词获取失败")
            return False
        try:
            image = self.renderer.draw_lyrics(song.lyrics)
            await event.send(MessageChain(chain=[Image.fromBytes(image)]))
            return True
        except Exception as e:
            logger.error(f"【{song.name}】歌词渲染/发送失败: {e}")
            return False
    async def send_card(
        self, event: AiocqhttpMessageEvent, player: BaseMusicPlayer, song: Song
    ) -> bool:
        """发卡片"""
        payloads: dict = {
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
        if not file_path:
            await event.send(event.plain_result(f"【{song.name}】音频文件下载失败"))
            return False
        try:
            file_name = f"{song.name}_{song.artists}{file_path.suffix}"
            seg = File(name=file_name, file=str(file_path))
            await event.send(event.chain_result([seg]))
            return True
        except Exception as e:
            await event.send(event.plain_result(f"【{song.name}】音频文件发送失败: {e}"))
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

    def _is_mode_supported(self, mode: str, event, player) -> bool:
        if mode == "card":
            return isinstance(event, AiocqhttpMessageEvent) and isinstance(
                player, NetEaseMusic | NetEaseMusicNodeJS
            )
        # 延迟导入，防止初始化卡顿
        from astrbot.core.platform.sources.discord.discord_platform_event import (
            DiscordViewComponent,
        )
        from astrbot.core.platform.sources.telegram.tg_event import (
            TelegramPlatformEvent,
        )

        if mode == "record":
            return isinstance(
                event,
                AiocqhttpMessageEvent | TelegramPlatformEvent,
            )

        if mode == "file":
            return isinstance(
                event,
                AiocqhttpMessageEvent | TelegramPlatformEvent | DiscordViewComponent,
            )

        if mode == "text":
            return True

        return False

    async def send_song(self, event: AstrMessageEvent, player: BaseMusicPlayer, song: Song):
        logger.debug(
            f"{event.get_sender_name()}（{event.get_sender_id()}）点歌："
            f"{player.platform.display_name} -> {song.name}_{song.artists}"
        )

        sent = False

        for mode in self.cfg.real_send_modes:
            if not self._is_mode_supported(mode, event, player):
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
