"""歌单管理模块"""

import asyncio
import sqlite3

from astrbot.api import logger

from .config import PluginConfig
from .model import Song


class Playlist:
    """歌单管理类，封装歌单的所有操作"""

    def __init__(self, config: PluginConfig):
        """
        初始化歌单管理器
        :param data_dir: 数据目录路径
        :param limit: 歌单显示数量限制
        """
        self.cfg = config
        self.playlist_dir = self.cfg.playlist_dir
        self.db_path = self.cfg.db_path
        self.limit = self.cfg.playlist_limit

        self._conn: sqlite3.Connection = None  # type: ignore
        self._lock = asyncio.Lock()

    async def initialize(self):
        """初始化数据库表"""
        async with self._lock:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            cursor = self._conn.cursor()

            # 创建歌单表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS playlist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    song_id TEXT NOT NULL,
                    song_name TEXT,
                    artists TEXT,
                    duration INTEGER,
                    cover_url TEXT,
                    audio_url TEXT,
                    platform TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, song_id, platform)
                )
            """)

            # 创建索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_user_id ON playlist(user_id)
            """)

            self._conn.commit()
            logger.info("歌单数据库初始化完成")

    async def close(self):
        """关闭数据库连接"""
        async with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None  # type: ignore

    async def add_song(self, user_id: str, song: Song, platform: str) -> bool:
        """
        添加歌曲到歌单
        :param user_id: 用户ID
        :param song: 歌曲对象
        :param platform: 平台名称
        :return: 是否添加成功
        """
        async with self._lock:
            try:
                cursor = self._conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO playlist
                    (user_id, song_id, song_name, artists, duration, cover_url, audio_url, platform)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        user_id,
                        song.id,
                        song.name,
                        song.artists,
                        song.duration,
                        song.cover_url,
                        song.audio_url,
                        platform,
                    ),
                )
                self._conn.commit()
                logger.debug(f"用户 {user_id} 收藏了歌曲：{song.name}")
                return True
            except sqlite3.IntegrityError:
                # 违反唯一约束，歌曲已存在
                logger.debug(f"歌曲 {song.name} 已在用户 {user_id} 的歌单中")
                return False
            except Exception as e:
                logger.error(f"添加歌曲到歌单失败: {e}")
                return False

    async def remove_song(self, user_id: str, song_id: str, platform: str) -> bool:
        """
        从歌单移除歌曲
        :param user_id: 用户ID
        :param song_id: 歌曲ID
        :param platform: 平台名称
        :return: 是否移除成功
        """
        async with self._lock:
            try:
                cursor = self._conn.cursor()
                cursor.execute(
                    """
                    DELETE FROM playlist
                    WHERE user_id = ? AND song_id = ? AND platform = ?
                """,
                    (user_id, song_id, platform),
                )
                self._conn.commit()

                if cursor.rowcount > 0:
                    logger.debug(f"用户 {user_id} 取消收藏了歌曲：{song_id}")
                    return True
                else:
                    logger.debug(f"歌曲 {song_id} 不在用户 {user_id} 的歌单中")
                    return False
            except Exception as e:
                logger.error(f"从歌单移除歌曲失败: {e}")
                return False

    async def get_songs(
        self, user_id: str, limit: int | None = None
    ) -> list[tuple[Song, str]]:
        """
        获取用户的歌单
        :param user_id: 用户ID
        :param limit: 返回数量限制，默认使用初始化时的limit
        :return: (歌曲, 平台名称) 元组列表
        """
        if limit is None:
            limit = self.limit

        async with self._lock:
            try:
                cursor = self._conn.cursor()
                cursor.execute(
                    """
                    SELECT song_id, song_name, artists, duration, cover_url, audio_url, platform
                    FROM playlist
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """,
                    (user_id, limit),
                )

                rows = cursor.fetchall()
                result = []
                for row in rows:
                    song = Song(
                        id=row["song_id"],
                        name=row["song_name"],
                        artists=row["artists"],
                        duration=row["duration"],
                        cover_url=row["cover_url"],
                        audio_url=row["audio_url"],
                    )
                    platform = row["platform"]
                    result.append((song, platform))

                return result
            except Exception as e:
                logger.error(f"获取用户歌单失败: {e}")
                return []

    async def has_song(self, user_id: str, song_id: str, platform: str) -> bool:
        """
        检查歌曲是否在歌单中
        :param user_id: 用户ID
        :param song_id: 歌曲ID
        :param platform: 平台名称
        :return: 是否存在
        """
        async with self._lock:
            try:
                cursor = self._conn.cursor()
                cursor.execute(
                    """
                    SELECT COUNT(*) as count FROM playlist
                    WHERE user_id = ? AND song_id = ? AND platform = ?
                """,
                    (user_id, song_id, platform),
                )

                row = cursor.fetchone()
                return row["count"] > 0
            except Exception as e:
                logger.error(f"检查歌曲是否在歌单中失败: {e}")
                return False

    async def get_count(self, user_id: str) -> int:
        """
        获取用户歌单数量
        :param user_id: 用户ID
        :return: 歌曲数量
        """
        async with self._lock:
            try:
                cursor = self._conn.cursor()
                cursor.execute(
                    """
                    SELECT COUNT(*) as count FROM playlist
                    WHERE user_id = ?
                """,
                    (user_id,),
                )

                row = cursor.fetchone()
                return row["count"]
            except Exception as e:
                logger.error(f"获取歌单数量失败: {e}")
                return 0

    async def is_empty(self, user_id: str) -> bool:
        """
        检查用户歌单是否为空
        :param user_id: 用户ID
        :return: 是否为空
        """
        async with self._lock:
            try:
                cursor = self._conn.cursor()
                cursor.execute(
                    """
                    SELECT 1 FROM playlist WHERE user_id = ? LIMIT 1
                """,
                    (user_id,),
                )

                row = cursor.fetchone()
                return row is None
            except Exception as e:
                logger.error(f"检查歌单是否为空失败: {e}")
                return True  # 出错时默认返回空

    async def clear(self, user_id: str) -> bool:
        """
        清空用户歌单
        :param user_id: 用户ID
        :return: 是否清空成功
        """
        async with self._lock:
            try:
                cursor = self._conn.cursor()
                cursor.execute(
                    """
                    DELETE FROM playlist WHERE user_id = ?
                """,
                    (user_id,),
                )
                self._conn.commit()
                logger.debug(f"用户 {user_id} 清空了歌单")
                return True
            except Exception as e:
                logger.error(f"清空歌单失败: {e}")
                return False
