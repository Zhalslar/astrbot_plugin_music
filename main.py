
import random
import traceback
from astrbot.api.event import filter, AstrMessageEvent
import astrbot.api.message_components as Comp
from astrbot.api.star import Context, Star, register
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.message.components import Record
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.utils.session_waiter import (
    session_waiter,
    SessionController,
)
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
from astrbot import logger
from data.plugins.astrbot_plugin_music.draw import draw_lyrics
from data.plugins.astrbot_plugin_music.utils import format_time


@register(
    "astrbot_plugin_music",
    "Zhalslar",
    "音乐搜索、热评",
    "1.0.1",
    "https://github.com/Zhalslar/astrbot_plugin_music",
)
class MusicPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)

        # 默认API
        self.default_api = config.get("default_api", "netease")
        # 网易云nodejs服务的默认端口
        self.nodejs_base_url = config.get(
            "nodejs_base_url", "http://netease_cloud_music_api:3000"
        )
        if self.default_api == "netease":
            from .api import NetEaseMusicAPI

            self.api = NetEaseMusicAPI()

        elif self.default_api == "netease_nodejs":
            from .api import NetEaseMusicAPINodeJs
            self.api = NetEaseMusicAPINodeJs(base_url=self.nodejs_base_url)
        # elif self.default_api == "tencent":
        #     from .api import TencentMusicAPI
        #     self.api = TencentMusicAPI()
        # elif self.default_api == "kugou":
        #     from .api import KuGouMusicAPI
        #     self.api = KuGouMusicAPI()

        # 选择模式
        self.select_mode = config.get("select_mode", "text")

        # 发送模式
        self.send_mode = config.get("send_mode", "card")

        # 是否启用评论
        self.enable_comments = config.get("enable_comments", True)

        # 是否启用歌词
        self.enable_lyrics = config.get("enable_lyrics", False)

        # 等待超时时长
        self.timeout = config.get("timeout", 30)

    @filter.command("点歌")
    async def search_song(self, event: AstrMessageEvent):
        """搜索歌曲供用户选择"""
        args = event.message_str.replace("点歌", "").split()
        if not args:
            yield event.plain_result("没给歌名喵~")
            return

        # 解析序号和歌名
        index: int = int(args[-1]) if args[-1].isdigit() else 0
        song_name = " ".join(args[:-1]) if args[-1].isdigit() else " ".join(args)

        # 搜索歌曲
        songs = await self.api.fetch_data(keyword=song_name)
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

            @session_waiter(timeout=self.timeout, record_history_chains=False)  # type: ignore  # noqa: F821
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
        if self.select_mode == "image":
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

        platform_name = event.get_platform_name()
        send_mode = self.send_mode

        # 发卡片
        if platform_name == "aiocqhttp" and send_mode == "card":
            assert isinstance(event, AiocqhttpMessageEvent)
            client = event.bot
            is_private  = event.is_private_chat()
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
            if is_private:
                payloads["user_id"] = event.get_sender_id()
                await client.api.call_action("send_private_msg", **payloads)
            else:
                payloads["group_id"] = event.get_group_id()
                await client.api.call_action("send_group_msg", **payloads)

        # 发语音
        elif (
            platform_name in ["telegram", "lark", "aiocqhttp"] and send_mode == "record"
        ):
            audio_url = (await self.api.fetch_extra(song_id=song["id"]))["audio_url"]
            await event.send(event.chain_result([Record.fromURL(audio_url)]))

        # 发文字
        else:
            audio_url = (await self.api.fetch_extra(song_id=song["id"]))["audio_url"]
            song_info_str = (
                f"🎶{song.get('name')} - {song.get('artists')} {format_time(song['duration'])}\n"
                f"🔗链接：{audio_url}"
            )
            await event.send(event.plain_result(song_info_str))

        # 发送评论
        if self.enable_comments:
            comments = await self.api.fetch_comments(song_id=song["id"])
            content = random.choice(comments)["content"]
            await event.send(event.plain_result(content))

        # 发送歌词
        if self.enable_lyrics:
            lyrics = await self.api.fetch_lyrics(song_id=song["id"])
            image = draw_lyrics(lyrics)
            await event.send(MessageChain(chain=[Comp.Image.fromBytes(image)]))




