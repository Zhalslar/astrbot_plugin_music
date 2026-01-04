import traceback
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.star.star_tools import StarTools
from astrbot.core.utils.session_waiter import (
    SessionController,
    session_waiter,
)

from .core.database import PlaylistDatabase
from .core.downloader import Downloader
from .core.platform import BaseMusicPlayer
from .core.renderer import MusicRenderer
from .core.sender import MusicSender


class MusicPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

        self.font_path = Path(__file__).parent / "fonts" / "simhei.ttf"
        self.data_dir = StarTools.get_data_dir()
        self.songs_dir = self.data_dir / "songs"
        self.songs_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建歌单目录
        self.playlist_dir = self.data_dir / "playlist"
        self.playlist_dir.mkdir(parents=True, exist_ok=True)
        
        # 数据库路径
        self.db_path = self.data_dir / "playlist.db"

        self.song_limit: int = (
            1 if "single" in config["select_mode"] else config["song_limit"]
        )
        self.default_player_name: str = (
            self.config["default_player_name"].split("(", 1)[0].strip()
        )

        self.players: list[BaseMusicPlayer] = []
        self.keywords: list[str] = []

    async def initialize(self):
        """插件加载时会调用"""
        self._register_parser()
        self.downloader = Downloader(self.config, self.songs_dir)
        await self.downloader.initialize()
        self.renderer = MusicRenderer(self.config, self.font_path)
        self.sender = MusicSender(self.config, self.renderer, self.downloader)
        
        # 初始化歌单数据库
        self.playlist_db = PlaylistDatabase(self.db_path)
        await self.playlist_db.initialize()

    async def terminate(self):
        """当插件被卸载/停用时会调用"""
        await self.downloader.close()
        for parser in self.players:
            await parser.close()
        await self.playlist_db.close()

    def get_player(
        self, name: str | None = None, word: str | None = None, default: bool = False
    ) -> BaseMusicPlayer | None:
        if default:
            word = self.default_player_name
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

    def _register_parser(self):
        """注册音乐播放器"""
        all_subclass = BaseMusicPlayer.get_all_subclass()
        for _cls in all_subclass:
            player = _cls(self.config)
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
            keyword=song_name, limit=self.song_limit, extra=cmd
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
            await self.sender.send_song_selection(event=event, songs=songs, title=title)

            @session_waiter(timeout=self.config["timeout"])  # type: ignore  # noqa: F821
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

    @filter.command("收藏")
    async def collect_song(self, event: AstrMessageEvent, song_name: str):
        """收藏 <歌名>"""
        user_id = str(event.get_sender_id())
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
        
        # 检查是否已收藏
        if await self.playlist_db.is_song_in_playlist(user_id, song.id, platform):
            yield event.plain_result(f"【{song.name}】已在你的歌单中")
            return
        
        # 添加到歌单
        success = await self.playlist_db.add_song(user_id, song, platform)
        if success:
            yield event.plain_result(f"✓ 已收藏【{song.name} - {song.artists}】")
        else:
            yield event.plain_result("收藏失败")

    @filter.command("取消收藏")
    async def uncollect_song(self, event: AstrMessageEvent, song_name: str):
        """取消收藏 <歌名>"""
        user_id = str(event.get_sender_id())
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
        success = await self.playlist_db.remove_song(user_id, song.id, platform)
        if success:
            yield event.plain_result(f"✓ 已取消收藏【{song.name} - {song.artists}】")
        else:
            yield event.plain_result(f"【{song.name}】不在你的歌单中")

    @filter.command("查看歌单")
    async def view_playlist(self, event: AstrMessageEvent):
        """查看歌单"""
        user_id = str(event.get_sender_id())
        
        # 获取歌单数量
        count = await self.playlist_db.get_playlist_count(user_id)
        if count == 0:
            yield event.plain_result("你的歌单是空的，使用「收藏 <歌名>」来添加歌曲")
            return
        
        # 获取歌单
        songs = await self.playlist_db.get_user_playlist(user_id, limit=50)
        if not songs:
            yield event.plain_result("获取歌单失败")
            return
        
        # 格式化歌单
        playlist_text = f"📝 你的歌单（共{count}首）\n\n"
        for i, song in enumerate(songs, 1):
            duration_str = ""
            if song.duration:
                mins, secs = divmod(song.duration // 1000, 60)
                duration_str = f" [{mins}:{secs:02d}]"
            playlist_text += f"{i}. {song.name} - {song.artists}{duration_str}\n"
        
        playlist_text += "\n使用「歌单点歌 <序号>」来播放歌单中的歌曲"
        yield event.plain_result(playlist_text.strip())

    @filter.command("歌单点歌")
    async def play_from_playlist(self, event: AstrMessageEvent, index: str):
        """歌单点歌 <序号>"""
        user_id = str(event.get_sender_id())
        
        # 验证序号
        if not index.isdigit():
            yield event.plain_result("请输入有效的序号")
            return
        
        idx = int(index)
        if idx < 1:
            yield event.plain_result("序号必须大于0")
            return
        
        # 获取歌单
        songs = await self.playlist_db.get_user_playlist(user_id, limit=50)
        if not songs:
            yield event.plain_result("你的歌单是空的")
            return
        
        if idx > len(songs):
            yield event.plain_result(f"序号超出范围，你的歌单只有{len(songs)}首歌")
            return
        
        # 获取指定的歌曲
        song = songs[idx - 1]
        
        # 找到对应的播放器（从note中提取平台信息）
        platform_name = None
        if song.note and "平台: " in song.note:
            platform_name = song.note.split("平台: ")[1].strip()
        
        player = self.get_player(name=platform_name) if platform_name else self.get_player(default=True)
        if not player:
            yield event.plain_result("无可用播放器")
            return
        
        # 发送歌曲
        await self.sender.send_song(event, player, song)
