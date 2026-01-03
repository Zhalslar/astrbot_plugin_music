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

from .core.downloader import Downloader
from .core.platform import BaseMusicPlayer
from .core.renderer import MusicRenderer
from .core.sender import MusicSender


class MusicPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.song_limit = (
            1 if config["select_mode"] == "single" else config["song_limit"]
        )
        self.data_dir = StarTools.get_data_dir()
        self.font_path = Path(__file__).parent / "fonts" / "simhei.ttf"
        self.player_names: list[str] = [
            name.split("(", 1)[0].strip() for name in config["enable_players"]
        ]
        if not self.player_names:
            raise ValueError("请至少配置一个音乐平台")
        self.players: list[BaseMusicPlayer] = []
        self.default_player_name = (
            self.config["default_player_name"].split("(", 1)[0].strip()
        )

    def get_player(
        self, name: str | None = None, word: str | None = None
    ) -> BaseMusicPlayer:
        for player in self.players:
            if name:
                p = player.platform
                if p.display_name == name or p.name == name:
                    return player
            elif word:
                for keyword in player.platform.keywords:
                    if keyword in word:
                        return player
        # 兜底
        return (
            next(
                player
                for player in self.players
                if player.platform.display_name == self.default_player_name
            )
            or self.players[0]
        )

    async def initialize(self):
        """插件加载时会调用"""
        self._register_parser()
        self.downloader = Downloader(self.data_dir)
        self.renderer = MusicRenderer(self.config, self.font_path)
        self.sender = MusicSender(self.config, self.renderer)

    async def terminate(self):
        """当插件被卸载/停用时会调用"""
        await self.downloader.close()
        for parser in self.players:
            await parser.close()

    def _register_parser(self):
        """注册音乐播放器"""
        # 获取所有播放器
        all_subclass = BaseMusicPlayer.get_all_subclass()
        # 过滤掉禁用的播放器
        enabled_classes = [
            _cls
            for _cls in all_subclass
            if _cls.platform.display_name in self.config["enable_players"]
        ]
        # 启用的播放器
        platform_names = []
        for _cls in enabled_classes:
            player = _cls(self.config)
            platform_names.append(player.platform.display_name)
            self.players.append(player)
        logger.debug(f"启用音乐播放器: {'、'.join(platform_names)}")

    @filter.command(
        command_name="点歌",
        aliases=["网易点歌", "NJ点歌", "nj点歌", "TX点歌", "tx点歌"],
    )
    async def search_song(self, event: AstrMessageEvent):
        """搜索歌曲供用户选择"""
        # 解析参数
        player_arg, _, searchr_arg = event.message_str.partition("点歌")
        args = searchr_arg.split()
        if not args:
            yield event.plain_result("没给歌名")
            return
        index: int = int(args[-1]) if args[-1].isdigit() else 0
        song_name = " ".join(args[:-1]) if args[-1].isdigit() else " ".join(args)
        player = self.get_player(word=player_arg.strip().lower())
        # 搜索歌曲
        songs = await player.fetch_songs(keyword=song_name, limit=self.song_limit)
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
            await self.sender.send_song_selection(event=event, songs=songs)

            @session_waiter(timeout=self.config["timeout"])  # type: ignore  # noqa: F821
            async def empty_mention_waiter(
                controller: SessionController, event: AstrMessageEvent
            ):
                index = event.message_str
                if not index.isdigit() or int(index) < 1 or int(index) > len(songs):
                    return
                selected_song = songs[int(index) - 1]
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
        player = self.get_player()
        songs = await player.fetch_songs(
            keyword=song_name, limit=self.config["song_limit"]
        )
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
        player = self.get_player()
        songs = await player.fetch_songs(keyword=song_name)
        if not songs:
            return "没找到相关歌曲"
        await self.sender.send_song(event, player, songs[0])
