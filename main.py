
from pathlib import Path
import random
import aiofiles
import aiohttp
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


SAVED_SONGS_DIR = Path("data", "plugins_data", "astrbot_plugin_music", "songs")
SAVED_SONGS_DIR.mkdir(parents=True, exist_ok=True)


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
            print(selected_song)
            song_id = selected_song["id"]
            # 发送歌曲
            await self._send_song(event, selected_song)
            # 发送评论
            if self.enable_comments:
                await self._send_comments(event, song_id)
            # 发送歌词
            if self.enable_lyrics:
                await self._send_lyrics(event, song_id)

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
                # 发送歌曲
                await self._send_song(event=event, song=selected_song)
                # 发送评论
                if self.enable_comments and selected_song:
                    await self._send_comments(event, selected_song["id"])
                # 发送歌词
                if self.enable_lyrics and selected_song:
                    await self._send_lyrics(event, selected_song["id"])

                controller.stop()

            try:
                await empty_mention_waiter(event)  # type: ignore
            except TimeoutError as _:
                yield event.plain_result("点歌超时！")
            except Exception as e:
                logger.error(traceback.format_exc())
                logger.error("点歌发生错误" + str(e))

        event.stop_event()

    async def _send_comments(self, event: AstrMessageEvent, song_id):
        """发送评论（随机发送一条）"""
        comments = await self.api.fetch_comments(song_id=song_id)
        print(comments)
        content = random.choice(comments)["content"]
        await event.send(event.plain_result(content))

    async def _send_lyrics(self, event: AstrMessageEvent, song_id):
        """发送歌词"""
        lyrics = await self.api.fetch_lyrics(song_id=song_id)
        image = draw_lyrics(lyrics)
        await event.send(MessageChain(chain=[Comp.Image.fromBytes(image)]))

    async def _send_selection(self, event: AstrMessageEvent, songs: list) -> None:
        """
        发送歌曲选择
        """
        if self.select_mode == "image":
            # extra_info = await self.api.fetch_extra(song_id=song["id"])
            # cover_url = extra_info["cover_url"]
            # template_path = os.path.join(
            #     os.path.dirname(os.path.abspath(__file__)), "song_info_template.html"
            # )
            # try:
            #     with open(template_path, "r", encoding="utf-8") as f:
            #         template_content = f.read()

            #     template = Template(template_content)
            #     rendered_html = template.render(songs=songs)
            #     image_url = await self.html_render(rendered_html, {})
            #     await event.send(event.image_result(image_url))
            # except Exception as e:
            #     logger.error(f"歌曲信息图片生成失败: {e}")
            return

        elif self.select_mode == "button":
            assert isinstance(event, AiocqhttpMessageEvent)
            buttons = []
            for index, song in enumerate(songs):
                button_row = [
                    {
                        "label": f"{index + 1}. {song['name']} - {song['artists']}",
                        "callback": str(index + 1),
                    }
                ]
                buttons.append(button_row)
            await self.send_button(event, buttons)

        else:
            formatted_songs = [
                f"{index + 1}. {song['name']} - {song['artists']}"
                for index, song in enumerate(songs)
            ]
            await event.send(event.plain_result("\n".join(formatted_songs)))


    async def _send_song(self, event: AstrMessageEvent, song: dict):
        """发送歌曲"""

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
                f"🎶{song.get('name')} - {song.get('artists')} {self.format_time(song['duration'])}\n"
                f"🔗链接：{audio_url}"
            )
            await event.send(event.plain_result(song_info_str))

    @staticmethod
    def format_time(duration_ms):
        """格式化歌曲时长"""
        duration = duration_ms // 1000

        hours = duration // 3600
        minutes = (duration % 3600) // 60
        seconds = duration % 60

        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes:02d}:{seconds:02d}"

    async def send_button(
        self, event: AiocqhttpMessageEvent, buttons: list[list[dict[str, str]]]
    ) -> str | None:
        """调用buttons插件发送按钮"""
        button_plugin = self.context.get_registered_star("astrbot_plugin_buttons")
        if button_plugin.activated:
            cls = button_plugin.star_cls
            await cls.send_button(  # type: ignore
                client=event.bot,
                buttons_info=buttons,
                group_id=event.get_group_id(),
                user_id=event.get_sender_id(),
            )
        else:
            await event.send(
                event.plain_result(
                    "astrbot_plugin_buttons插件未激活，无法调用按钮发送服务"
                )
            )
            return

    @staticmethod
    async def download_image(url: str) -> bytes | None:
        """下载图片"""
        url = url.replace("https://", "http://")
        try:
            async with aiohttp.ClientSession() as client:
                response = await client.get(url)
                img_bytes = await response.read()
                return img_bytes
        except Exception as e:
            logger.error(f"图片下载失败: {e}")

    async def download_song(self, url: str, title: str) -> str | None:
        """下载歌曲"""
        file_path = str(SAVED_SONGS_DIR / f"{title}")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        async with aiofiles.open(file_path, "wb") as f:
                            # 流式写入文件
                            while True:
                                chunk = await response.content.read(1024)
                                if not chunk:
                                    break
                                await f.write(chunk)
                        logger.info(f"歌曲 {title} 下载完成，保存到 {file_path}")
                        return file_path
                    else:
                        logger.error(f"歌曲下载失败，HTTP 状态码：{response.status}")
        except Exception as e:
            logger.error(f"歌曲下载失败，错误信息：{e}")
    async def terminate(self):
        '''可选择实现 terminate 函数，当插件被卸载/停用时会调用。'''
        await self.api.close()