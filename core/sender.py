
import random

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.message.components import File, Image, Plain, Record
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
from astrbot.core.platform.sources.discord.discord_platform_event import (
    DiscordViewComponent,
)
from astrbot.core.platform.sources.lark.lark_event import LarkMessageEvent
from astrbot.core.platform.sources.telegram.tg_event import TelegramPlatformEvent

from .downloader import Downloader
from .model import Song
from .platform import BaseMusicPlayer
from .renderer import MusicRenderer


class MusicSender:
    def __init__(
        self, config: AstrBotConfig, renderer: MusicRenderer, downloader: Downloader
    ):
        self.config = config
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
    async def send_msg(event: AiocqhttpMessageEvent, payloads: dict):
        if event.is_private_chat():
            payloads["user_id"] = event.get_sender_id()
            await event.bot.api.call_action("send_private_msg", **payloads)
        else:
            payloads["group_id"] = event.get_group_id()
            await event.bot.api.call_action("send_group_msg", **payloads)

    async def send_song_selection(
        self, event: AstrMessageEvent, songs: list[Song]
    ) -> None:
        """
        发送歌曲选择
        """
        formatted_songs = [
            f"{index + 1}. {song.name} - {song.artists}"
            for index, song in enumerate(songs)
        ]
        if self.config["select_mode"] == "image":
            msg = "\n\n".join(formatted_songs)
            await event.send(MessageChain(chain=[Plain(msg)], use_t2i_=True))

        else:
            msg = "\n".join(formatted_songs)
            await event.send(event.plain_result(msg))

    async def send_comment(
        self, event: AstrMessageEvent, player: BaseMusicPlayer, song: Song
    ):
        """发评论"""
        if not song.comments:
            await player.fetch_comments(song)
        if not song.comments:
            # 没有评论
            return
        content = random.choice(song.comments).get("content")
        await event.send(event.plain_result(content))

    async def send_lyrics(
        self, event: AstrMessageEvent, player: BaseMusicPlayer, song: Song
    ):
        """发歌词"""
        if not song.lyrics:
            await player.fetch_lyrics(song)
        if not song.lyrics:
            logger.error(f"【{song.name}】歌词获取失败")
            return
        image = self.renderer.draw_lyrics(song.lyrics)
        await event.send(MessageChain(chain=[Image.fromBytes(image)]))

    async def send_card(self, event: AiocqhttpMessageEvent, song: Song):
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
        except Exception as e:
            logger.error(e)
            await event.send(event.plain_result(str(e)))

    async def send_record(
        self, event: AstrMessageEvent, player: BaseMusicPlayer, song: Song
    ):
        """发语音"""
        if not song.audio_url:
            song = await player.fetch_extra(song)
        if not song.audio_url:
            await event.send(event.plain_result(f"【{song.name}】音频获取失败"))
            return
        logger.debug(f"正在发送【{song.name}】音频: {song.audio_url}")
        seg = Record.fromURL(song.audio_url)
        await event.send(event.chain_result([seg]))

    async def send_file(
        self, event: AstrMessageEvent, player: BaseMusicPlayer, song: Song
    ):
        """发文件"""
        if not song.audio_url:
            song = await player.fetch_extra(song)
        if not song.audio_url:
            await event.send(event.plain_result(f"【{song.name}】音频获取失败"))
            return

        file_path = await self.downloader.download_song(song.audio_url)
        if not file_path:
            await event.send(event.plain_result(f"【{song.name}】音频文件下载失败"))
            return

        file_name = f"{song.name or file_path.stem}{file_path.suffix}"
        seg = File(name=file_name, file=str(file_path))
        await event.send(event.chain_result([seg]))

    async def send_text(
        self, event: AstrMessageEvent, player: BaseMusicPlayer, song: Song
    ):
        """发文本"""
        info = f"🎶{song.name} - {song.artists} {self._format_time(song.duration)}"
        song = await player.fetch_extra(song)
        info = song.to_lines()
        await event.send(event.plain_result(info))

    async def send_song(
        self, event: AstrMessageEvent, player: BaseMusicPlayer, song: Song
    ):
        """综合发送策略"""
        logger.debug(
            f"{event.get_sender_name()}（{event.get_sender_id()}）触发点歌事件：{player.platform.display_name} -> {song.name}_{song.artists}"
        )
        # 发卡片
        if self.config["send_mode"] == "card" and isinstance(
            event, AiocqhttpMessageEvent
        ):
            await self.send_card(event, song)

        # 发语音
        elif self.config["send_mode"] == "record" and isinstance(
            event, AiocqhttpMessageEvent | LarkMessageEvent | TelegramPlatformEvent
        ):
            await self.send_record(event, player, song)

        # 发文件
        elif self.config["send_mode"] == "file" and isinstance(
            event, AiocqhttpMessageEvent | TelegramPlatformEvent | DiscordViewComponent
        ):
            await self.send_file(event, player, song)

        # 发文字
        else:
            await self.send_text(event, player, song)

        # 发送评论
        if self.config["enable_comments"]:
            await self.send_comment(event, player, song)

        # 发送歌词
        if self.config["enable_lyrics"]:
            await self.send_lyrics(event, player, song)
