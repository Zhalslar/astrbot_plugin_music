import asyncio
import sqlite3
from pathlib import Path
from typing import Optional

from astrbot.api import logger

from .model import Song


class PlaylistDatabase:
    """歌单数据库管理类"""

    def __init__(self, db_path: Path):
        """
        初始化数据库
        :param db_path: 数据库文件路径
        """
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
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
                self._conn = None

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
                cursor.execute("""
                    INSERT INTO playlist 
                    (user_id, song_id, song_name, artists, duration, cover_url, audio_url, platform)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id,
                    song.id,
                    song.name,
                    song.artists,
                    song.duration,
                    song.cover_url,
                    song.audio_url,
                    platform
                ))
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
                cursor.execute("""
                    DELETE FROM playlist 
                    WHERE user_id = ? AND song_id = ? AND platform = ?
                """, (user_id, song_id, platform))
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

    async def get_user_playlist(self, user_id: str, limit: int = 50) -> list[tuple[Song, str]]:
        """
        获取用户的歌单
        :param user_id: 用户ID
        :param limit: 返回数量限制
        :return: (歌曲, 平台名称) 元组列表
        """
        async with self._lock:
            try:
                cursor = self._conn.cursor()
                cursor.execute("""
                    SELECT song_id, song_name, artists, duration, cover_url, audio_url, platform
                    FROM playlist
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (user_id, limit))
                
                rows = cursor.fetchall()
                result = []
                for row in rows:
                    song = Song(
                        id=row["song_id"],
                        name=row["song_name"],
                        artists=row["artists"],
                        duration=row["duration"],
                        cover_url=row["cover_url"],
                        audio_url=row["audio_url"]
                    )
                    platform = row["platform"]
                    result.append((song, platform))
                
                return result
            except Exception as e:
                logger.error(f"获取用户歌单失败: {e}")
                return []

    async def is_song_in_playlist(self, user_id: str, song_id: str, platform: str) -> bool:
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
                cursor.execute("""
                    SELECT COUNT(*) as count FROM playlist
                    WHERE user_id = ? AND song_id = ? AND platform = ?
                """, (user_id, song_id, platform))
                
                row = cursor.fetchone()
                return row["count"] > 0
            except Exception as e:
                logger.error(f"检查歌曲是否在歌单中失败: {e}")
                return False

    async def get_playlist_count(self, user_id: str) -> int:
        """
        获取用户歌单数量
        :param user_id: 用户ID
        :return: 歌曲数量
        """
        async with self._lock:
            try:
                cursor = self._conn.cursor()
                cursor.execute("""
                    SELECT COUNT(*) as count FROM playlist
                    WHERE user_id = ?
                """, (user_id,))
                
                row = cursor.fetchone()
                return row["count"]
            except Exception as e:
                logger.error(f"获取歌单数量失败: {e}")
                return 0
