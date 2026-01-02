import random
import traceback
from pathlib import Path

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.message.components import Record
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
from astrbot.core.platform.sources.lark.lark_event import LarkMessageEvent
from astrbot.core.platform.sources.telegram.tg_event import TelegramPlatformEvent
from astrbot.core.star.star_tools import StarTools
from astrbot.core.utils.session_waiter import (
    SessionController,
    session_waiter,
)

from .core.downloader import Downloader
from .core.platform import create_music_platform
from .core.renderer import MusicRenderer
from .core.utils import format_time


class MusicPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.data_dir = StarTools.get_data_dir()
        self.font_path = Path(__file__).parent / "fonts" / "simhei.ttf"

    async def initialize(self):
        """插件加载时会调用"""
        self.downloader = Downloader(self.data_dir) # 下载器, 未来拓展时用到
        self.renderer = MusicRenderer(self.config, self.font_path)
        self.platform = create_music_platform(self.config)

    async def terminate(self):
        """当插件被卸载/停用时会调用"""
        await self.downloader.close()

    @filter.command("点歌")
    async def search_song(self, event: AstrMessageEvent):
        """搜索歌曲供用户选择"""
        args = event.message_str.replace("点歌", "").split()
        if not args:
            yield event.plain_result("没给歌名")
            return

        # 解析序号和歌名
        index: int = int(args[-1]) if args[-1].isdigit() else 0
        song_name = " ".join(args[:-1]) if args[-1].isdigit() else " ".join(args)

        # 搜索歌曲
        songs = await self.platform.fetch_data(keyword=song_name)
        if not songs:
            yield event.plain_result("没能找到这首歌喵~")
            return

        # 输入了序号，直接发送歌曲
        if index and 0 <= index <= len(songs):
            selected_song = songs[int(index) - 1]
            await self._send_song(event, selected_song)

        # 未提输入序号，等待用户选择歌曲
        else:
            await self._send_selection(event=event, songs=songs)

            @session_waiter(timeout=self.config["timeout"])  # type: ignore  # noqa: F821
            async def empty_mention_waiter(
                controller: SessionController, event: AstrMessageEvent
            ):
                index = event.message_str
                if not index.isdigit() or int(index) < 1 or int(index) > len(songs):
                    return
                selected_song = songs[int(index) - 1]
                await self._send_song(event=event, song=selected_song)
                controller.stop()

            try:
                await empty_mention_waiter(event)  # type: ignore
            except TimeoutError as _:
                yield event.plain_result("点歌超时！")
            except Exception as e:
                logger.error(traceback.format_exc())
                logger.error("点歌发生错误" + str(e))

        event.stop_event()

    async def _send_selection(self, event: AstrMessageEvent, songs: list) -> None:
        """
        发送歌曲选择
        """
        if self.config["select_mode"] == "image":
            formatted_songs = [
                f"{index + 1}. {song['name']} - {song['artists']}"
                for index, song in enumerate(songs)
            ]
            image = await self.text_to_image("\n".join(formatted_songs))
            await event.send(MessageChain(chain=[Comp.Image.fromURL(image)]))

        else:
            formatted_songs = [
                f"{index + 1}. {song['name']} - {song['artists']}"
                for index, song in enumerate(songs)
            ]
            await event.send(event.plain_result("\n".join(formatted_songs)))

    async def _send_song(self, event: AstrMessageEvent, song: dict):
        """发送歌曲、热评、歌词"""

        # 发卡片
        if (
            isinstance(event, AiocqhttpMessageEvent)
            and self.config["send_mode"] == "card"
        ):
            payloads: dict = {
                "message": [
                    {
                        "type": "music",
                        "data": {
                            "type": "163",
                            "id": str(song["id"]),
                        },
                    }
                ],
            }
            if event.is_private_chat():
                payloads["user_id"] = event.get_sender_id()
                await event.bot.api.call_action("send_private_msg", **payloads)
            else:
                payloads["group_id"] = event.get_group_id()
                await event.bot.api.call_action("send_group_msg", **payloads)

        # 发语音
        elif (
            isinstance(
                event, LarkMessageEvent | TelegramPlatformEvent | AiocqhttpMessageEvent
            )
            and self.config["send_mode"] == "record"
        ):
            audio_url = (await self.platform.fetch_extra(song_id=song["id"]))[
                "audio_url"
            ]
            await event.send(event.chain_result([Record.fromURL(audio_url)]))

        # 发文字
        else:
            audio_url = (await self.platform.fetch_extra(song_id=song["id"]))[
                "audio_url"
            ]
            song_info_str = (
                f"🎶{song.get('name')} - {song.get('artists')} {format_time(song['duration'])}\n"
                f"🔗链接：{audio_url}"
            )
            await event.send(event.plain_result(song_info_str))

        # 发送评论
        if self.config["enable_comments"]:
            if comments:= await self.platform.fetch_comments(song_id=song["id"]):
                content = random.choice(comments)["content"]
                await event.send(event.plain_result(content))

        # 发送歌词
        if self.config["enable_lyrics"]:
            lyrics = await self.platform.fetch_lyrics(song_id=song["id"])
            image = self.renderer.draw_lyrics(lyrics)
            await event.send(MessageChain(chain=[Comp.Image.fromBytes(image)]))
