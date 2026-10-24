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
from .core.lyrics_renderer import LyricsRenderer
from .core.platform import BaseMusicPlayer
from .core.sender import MusicSender
from .core.song_renderer import CardRenderer
from .core.utils import parse_user_input, pick_best_song


class MusicPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.context = context
        self.cfg = PluginConfig(config, context)
        self.lyrics_renderer = LyricsRenderer(self.cfg)
        self.song_renderer = CardRenderer(self.cfg)
        self.sender = MusicSender(
            self.cfg,
            self.context,
            self.lyrics_renderer,
            self.song_renderer,
        )
        self.players: list[BaseMusicPlayer] = []
        self.keywords: list[str] = []
        self.trigger_routes: dict[str, tuple[BaseMusicPlayer, str | None]] = {}

    async def initialize(self):
        self._register_player()

    async def terminate(self):
        await self.sender.close()
        for parser in self.players:
            await parser.close()

    def get_player(
        self, name: str | None = None, word: str | None = None, default: bool = False
    ) -> BaseMusicPlayer | None:
        if default:
            name = self.cfg.search_config.default_source
        for player in self.players:
            if name:
                name_ = name.strip().lower()
                p = player.platform
                if p.display_name.lower() == name_ or p.name.lower() == name_:
                    return player
            elif word:
                route = self.trigger_routes.get(word.strip().lower())
                if route:
                    return route[0]

    def _register_player(self):
        """注册音乐播放器"""
        all_subclass = BaseMusicPlayer.get_all_subclass()
        enabled_platforms = set(self.cfg.players.enabled_platforms())
        self.keywords.append("点歌")
        for _cls in all_subclass:
            if _cls.platform.name not in enabled_platforms:
                continue
            player = _cls(self.cfg)
            self.players.append(player)
            for trigger in player.platform_cfg.trigger_words or []:
                command, separator, source = trigger.partition(":")
                command = command.strip().lower()
                if not command:
                    continue
                self.trigger_routes[command] = (
                    player,
                    source.strip() if separator and source.strip() else None,
                )
                self.keywords.append(command)
        logger.debug(f"已注册触发词：{self.keywords}")

    @filter.command("点歌")
    async def search_song(self, event: AstrMessageEvent):
        """点歌 <歌手歌名>, 也可用命令：网易点歌 NJ点歌 QQ点歌..."""
        # 此函数仅用于注册显示命令
        pass

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_search_song(self, event: AstrMessageEvent):
        """根据音源触发词路由歌曲搜索。"""
        # 解析参数
        cmd, _, arg = event.message_str.partition(" ")
        if not arg:
            return
        if not event.is_at_or_wake_command and cmd.lower() not in self.keywords:
            return
        route = self.trigger_routes.get(cmd.lower())
        player = route[0] if route else None
        source = route[1] if route else None
        if cmd.lower() == "点歌" and not route:
            player = self.get_player(default=True)
            source = None
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
            keyword=song_name, limit=self.cfg.real_song_limit, extra=source
        )
        if not songs:
            yield event.plain_result(f"未找到歌曲：{song_name}")
            return

        # 单曲模式
        if len(songs) == 1:
            index = 1

        # 输入了序号，直接发送歌曲
        if index and 0 <= index <= len(songs):
            selected_song = songs[int(index) - 1]
            await self.sender.send_song(event, player, selected_song)
            event.stop_event()
            return

        # 未提输入序号，等待用户选择歌曲
        selection_mode = await self.sender.send_song_selection(
            event=event, songs=songs, player=player
        )

        if selection_mode == "button":
            event.stop_event()
            return
        if selection_mode not in {"image", "text"}:
            self.sender.clear_selection_context(event)
            event.stop_event()
            return

        @session_waiter(timeout=self.cfg.search_config.timeout)
        async def empty_mention_waiter(
            controller: SessionController, event: AstrMessageEvent
        ):
            arg = event.message_str.strip()
            arg_lower = arg.lower()
            waiter_command = arg_lower.partition(" ")[0]
            if waiter_command in self.keywords:
                controller.stop()
                return
            # 解析输入格式
            index, modes, error = parse_user_input(arg)
            if error:
                await event.send(event.plain_result(error))
                return
            if index == 0:
                return
            if index < 1 or index > len(songs):
                controller.stop()
                return
            selected_song = songs[index - 1]
            controller.stop()
            await self.sender.send_song(event, player, selected_song, modes=modes)

        try:
            await empty_mention_waiter(event)
        except TimeoutError as _:
            self.sender.clear_selection_context(event)
            yield event.plain_result("点歌超时！")
        except Exception as e:
            logger.error(traceback.format_exc())
            logger.error("点歌发生错误" + str(e))

        event.stop_event()

    @filter.command("查歌词", alias={"查看歌词"})
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
    async def query_lyrics_by_name(self, event: AstrMessageEvent, song_name: str):
        """当用户想查看歌词时，根据歌名（可含歌手）搜索并发送歌词图片。

        Args:
            song_name(string): 歌曲名称或包含歌手的关键词
        """
        player = self.get_player(default=True)
        if not player:
            return "无可用播放器"
        songs = await player.fetch_songs(keyword=song_name, limit=1)
        if not songs:
            return "没找到相关歌曲"
        sent = await self.sender.send_lyrics(event, player, songs[0])
        if not sent:
            return "歌词获取或发送失败"

    @filter.llm_tool()
    async def play_song_by_name(
        self, event: AstrMessageEvent, song_name: str, platform: str = ""
    ):
        """当用户想听歌时，根据歌名（可含歌手）搜索并播放音乐。

        Args:
            song_name(string): 歌曲名称或包含歌手的关键词
            platform(string): 音源标识或显示名称，例如 netease、netease_nodejs、neko、qqmusic、txqq。留空时使用默认音源。
        """

        player = (
            self.get_player(name=platform)
            if platform
            else self.get_player(default=True)
        )
        if not player:
            return f"无可用播放器 {platform}"
        songs = await player.fetch_songs(
            keyword=song_name, limit=self.cfg.search_config.song_limit
        )
        if not songs:
            return "没找到相关歌曲"
        selected_song = pick_best_song(song_name, songs)
        if not selected_song:
            return "没找到相关歌曲"
        sent = await self.sender.send_song(event, player, selected_song)
        if (
            sent
            and self.cfg.send_config.return_play_song_result
            and not selected_song.comments
        ):
            author = selected_song.artists or selected_song.author or "未知歌手"
            return f"已发送《{selected_song.name} - {author}》 "
