import asyncio
import traceback

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.utils.session_waiter import (
    SessionController,
    session_waiter,
)

from .core.config import PluginConfig
from .core.downloader import Downloader
from .core.platform import BaseMusicPlayer
from .core.playlist import Playlist
from .core.renderer import MusicRenderer
from .core.sender import MusicSender


class MusicPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.cfg = PluginConfig(config, context)
        self.players: list[BaseMusicPlayer] = []
        self.keywords: list[str] = []


    async def initialize(self):
        """插件加载时会调用"""
        self._register_player()
        self.downloader = Downloader(self.cfg)
        await self.downloader.initialize()
        self.renderer = MusicRenderer(self.cfg)
        self.sender = MusicSender(self.cfg, self.renderer, self.downloader)

        # 歌单管理器
        self.playlist = Playlist(self.cfg)
        await self.playlist.initialize()

    async def terminate(self):
        """当插件被卸载/停用时会调用"""
        await self.downloader.close()
        for parser in self.players:
            await parser.close()
        await self.playlist.close()

    def get_player(
        self, name: str | None = None, word: str | None = None, default: bool = False
    ) -> BaseMusicPlayer | None:
        if default:
            word = self.cfg.default_player_name
        for player in self.players:
            if name:
                name_ = name.strip().lower()
                p = player.platform
                if p.display_name.lower() == name_ or p.name.lower() == name_:
                    return player
            elif word:
                word_ = word.strip().lower()
                for keyword in player.platform.keywords:
                    if keyword.lower() in word_:
                        return player

    def _register_player(self):
        """注册音乐播放器"""
        all_subclass = BaseMusicPlayer.get_all_subclass()
        for _cls in all_subclass:
            player = _cls(self.cfg)
            self.players.append(player)
            self.keywords.extend(player.platform.keywords)
        logger.debug(f"已注册触发词：{self.keywords}")

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_search_song(self, event: AstrMessageEvent):
        """监听点歌命令： 点歌、网易点歌、网易nj、QQ点歌、酷狗点歌、酷我点歌、百度点歌、咪咕点歌、荔枝点歌、蜻蜓点歌、喜马拉雅、5sing原创、5sing翻唱、全民K歌"""
        # 解析参数
        if not event.is_at_or_wake_command:
            return
        cmd, _, arg = event.message_str.partition(" ")
        if not arg:
            return
        player = self.get_player(word=cmd)
        if "点歌" == cmd:
            player = self.get_player(default=True)
        if not player:
            return
        args = arg.split()
        index: int = int(args[-1]) if args[-1].isdigit() else 0
        song_name = arg.removesuffix(str(index))
        if not song_name:
            yield event.plain_result("未指定歌名")
            return
        # 搜索歌曲
        logger.debug(f"正在通过{player.platform.display_name}搜索歌曲：{song_name}")
        songs = await player.fetch_songs(
            keyword=song_name, limit=self.cfg.song_limit, extra=cmd
        )
        if not songs:
            yield event.plain_result(f"搜索【{song_name}】无结果")
            return

        # 单曲模式
        if len(songs) == 1:
            index = 1

        # 输入了序号，直接发送歌曲
        if index and 0 <= index <= len(songs):
            selected_song = songs[int(index) - 1]
            await self.sender.send_song(event, player, selected_song)

        # 未提输入序号，等待用户选择歌曲
        else:
            title = f"【{player.platform.display_name}】"
            asyncio.create_task(
                self.sender.send_song_selection(event=event, songs=songs, title=title)
            )

            @session_waiter(timeout=self.cfg.timeout)
            async def empty_mention_waiter(
                controller: SessionController, event: AstrMessageEvent
            ):
                arg = event.message_str.partition(" ")[0]
                arg_ = arg.strip().lower()
                for kw in self.keywords:
                    if kw in arg_:
                        controller.stop()
                        return
                if not arg.isdigit():
                    return
                if int(arg) < 1 or int(arg) > len(songs):
                    controller.stop()
                    return
                selected_song = songs[int(arg) - 1]
                await self.sender.send_song(event, player, selected_song)
                controller.stop()

            try:
                await empty_mention_waiter(event)  # type: ignore
            except TimeoutError as _:
                yield event.plain_result("点歌超时！")
            except Exception as e:
                logger.error(traceback.format_exc())
                logger.error("点歌发生错误" + str(e))

        event.stop_event()

    @filter.command("查歌词")
    async def query_lyrics(self, event: AstrMessageEvent, song_name: str):
        """查歌词 <搜索词>"""
        player = self.get_player(default=True)
        if not player:
            yield event.plain_result("无可用播放器")
            return
        songs = await player.fetch_songs(keyword=song_name, limit=1)
        if not songs:
            yield event.plain_result("没找到相关歌曲")
            return
        await self.sender.send_lyrics(event, player, songs[0])

    @filter.llm_tool()
    async def play_song_by_name(self, event: AstrMessageEvent, song_name: str):
        """
        当用户想听歌时，根据歌名（可含歌手）搜索并播放音乐。
        Args:
            song_name(string): 歌曲名称或包含歌手的关键词
        """
        player = self.get_player(default=True)
        if not player:
            return "无可用播放器"
        songs = await player.fetch_songs(keyword=song_name, limit=1)
        if not songs:
            return "没找到相关歌曲"
        await self.sender.send_song(event, player, songs[0])

    @filter.command("歌单收藏")
    async def collect_song(self, event: AstrMessageEvent, song_name: str):
        """歌单收藏 <歌名>"""
        user_id = event.get_sender_id()
        player = self.get_player(default=True)
        if not player:
            yield event.plain_result("无可用播放器")
            return

        # 搜索歌曲
        songs = await player.fetch_songs(keyword=song_name, limit=1)
        if not songs:
            yield event.plain_result(f"搜索【{song_name}】无结果")
            return

        song = songs[0]
        platform = player.platform.name

        # 添加到歌单
        success = await self.playlist.add_song(user_id, song, platform)
        if success:
            yield event.plain_result(f"已收藏【{song.name}_{song.artists}】")
        else:
            yield event.plain_result(f"【{song.name}】已在你的歌单中")

    @filter.command("歌单取藏")
    async def uncollect_song(self, event: AstrMessageEvent, song_name: str):
        """歌单取藏 <歌名>"""
        user_id = event.get_sender_id()
        player = self.get_player(default=True)
        if not player:
            yield event.plain_result("无可用播放器")
            return

        # 搜索歌曲
        songs = await player.fetch_songs(keyword=song_name, limit=1)
        if not songs:
            yield event.plain_result(f"搜索【{song_name}】无结果")
            return

        song = songs[0]
        platform = player.platform.name

        # 从歌单移除
        success = await self.playlist.remove_song(user_id, song.id, platform)
        if success:
            yield event.plain_result(f"已取消收藏【{song.name}_{song.artists}】")
        else:
            yield event.plain_result(f"【{song.name}】不在你的歌单中")

    @filter.command("歌单列表")
    async def view_playlist(self, event: AstrMessageEvent):
        """查看歌单"""
        user_id = event.get_sender_id()
        user_name = event.get_sender_name()

        # 检查歌单是否为空
        if await self.playlist.is_empty(user_id):
            yield event.plain_result("你的歌单是空的，使用「收藏 <歌名>」来添加歌曲")
            return

        # 获取歌单
        songs_with_platform = await self.playlist.get_songs(user_id)
        if not songs_with_platform:
            yield event.plain_result("获取歌单失败")
            return

        # 格式化歌单
        playlist_text = f"【{user_name}的歌单】\n"
        for i, (song, platform) in enumerate(songs_with_platform, 1):
            playlist_text += f"{i}. {song.name} - {song.artists}\n"

        yield event.plain_result(playlist_text.strip())

    @filter.command("歌单点歌")
    async def play_from_playlist(self, event: AstrMessageEvent, index: str):
        """歌单点歌 <序号>"""
        user_id = event.get_sender_id()

        # 验证序号
        if not index.isdigit():
            yield event.plain_result("请输入有效的序号")
            return

        idx = int(index)
        if idx < 1:
            yield event.plain_result("序号必须大于0")
            return

        # 获取歌单
        songs_with_platform = await self.playlist.get_songs(user_id)
        if not songs_with_platform:
            yield event.plain_result("你的歌单是空的")
            return

        if idx > len(songs_with_platform):
            yield event.plain_result(
                f"序号超出范围，你的歌单只有{len(songs_with_platform)}首歌"
            )
            return

        # 获取指定的歌曲和平台
        song, platform_name = songs_with_platform[idx - 1]

        # 找到对应的播放器
        player = self.get_player(name=platform_name)
        if not player:
            # 如果找不到对应平台的播放器，使用默认播放器
            player = self.get_player(default=True)

        if not player:
            yield event.plain_result("无可用播放器")
            return

        # 发送歌曲
        await self.sender.send_song(event, player, song)
