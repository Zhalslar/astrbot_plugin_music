import asyncio
import gzip
import json
import urllib.request
from pathlib import Path
from typing import Any, ClassVar

from astrbot.api import logger

from ..config import PluginConfig
from ..model import Platform, Song
from .base import BaseMusicPlayer


class QQMusicOfficial(BaseMusicPlayer):
    """QQ Music search and playback integration."""

    platform = Platform(
        name="qqmusic",
        display_name="QQ音乐",
        keywords=["QQ点歌", "qq点歌", "qq音乐", "QQ音乐"],
    )

    API_URL = "https://u.y.qq.com/cgi-bin/musicu.fcg"
    HEADERS: ClassVar[dict[str, str]] = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/153.0.0.0 Safari/537.36 Edg/153.0.0.0"
        ),
        "Content-Type": "application/json",
        "Referer": "https://y.qq.com/",
        "Accept-Encoding": "gzip",
    }

    def __init__(self, config: PluginConfig):
        super().__init__(config)

    @staticmethod
    def hash33(value: str, seed: int = 5381) -> int:
        for char in value:
            seed += (seed << 5) + ord(char)
        return seed & 0x7FFFFFFF

    @staticmethod
    def _cookie_values(cookie: str) -> dict[str, str]:
        values: dict[str, str] = {}
        for item in cookie.split(";"):
            key, separator, value = item.strip().partition("=")
            if separator:
                values[key] = value
        return values

    @classmethod
    def get_gtk(cls, cookie: str) -> int:
        values = cls._cookie_values(cookie)
        return cls.hash33(
            values.get("qqmusic_key")
            or values.get("qm_keyst")
            or values.get("p_skey")
            or ""
        )

    def _get_cookie(self) -> str:
        cookie = (self.cfg.qqmusic_cookie or "").strip()
        if not cookie:
            cookie_file = (self.cfg.qqmusic_cookie_file or "").strip()
            if not cookie_file:
                return ""
            try:
                cookie = Path(cookie_file).read_text(encoding="utf-8").strip()
            except OSError as exc:
                logger.warning(f"Failed to read QQ Music cookie file: {exc}")
                return ""

        values = self._cookie_values(cookie)
        if values.get("qqmusic_key") or values.get("qm_keyst"):
            return cookie
        return ""

    @staticmethod
    def _get_response_song_list(data: dict[str, Any] | None) -> list[dict[str, Any]]:
        value: Any = data
        for key in ("req", "data", "body", "song", "list"):
            if not isinstance(value, dict):
                return []
            value = value.get(key)
        return value if isinstance(value, list) else []

    async def _post_musicu(
        self, body: dict[str, Any], cookie: str
    ) -> dict[str, Any] | None:
        headers = dict(self.HEADERS)
        if cookie:
            headers["Cookie"] = cookie

        request = urllib.request.Request(
            self.API_URL,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            response = await asyncio.to_thread(
                urllib.request.urlopen, request, timeout=15
            )
            try:
                if response.status != 200:
                    logger.warning(f"QQ Music API returned HTTP {response.status}")
                    return None
                raw = await asyncio.to_thread(response.read)
            finally:
                response.close()

            if response.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            result = json.loads(raw.decode("utf-8", "ignore"))
            return result if isinstance(result, dict) else None
        except Exception as exc:
            logger.warning(f"QQ Music API request failed: {exc}")
            return None

    async def fetch_songs(
        self, keyword: str, limit: int, extra: str | None = None
    ) -> list[Song]:
        """Search QQ Music with retries for transient empty responses.

        Args:
            keyword: Song or artist search text.
            limit: Maximum number of results to request.
            extra: Unused platform-specific command context.

        Returns:
            Matching QQ Music songs.
        """
        del extra
        cookie = self._get_cookie()
        configured_uin = (self.cfg.qqmusic_uin or "").strip()
        if not configured_uin:
            logger.warning("QQ Music UIN is not configured")
            return []
        body = {
            "comm": {
                "ct": "19",
                "cv": "1859",
                "uin": configured_uin,
                "g_tk": self.get_gtk(cookie),
            },
            "req": {
                "module": "music.search.SearchCgiService",
                "method": "DoSearchForQQMusicDesktop",
                "param": {
                    "num_per_page": limit,
                    "page_num": 1,
                    "query": keyword,
                    "search_type": 0,
                },
            },
        }

        data = None
        for attempt in range(4):
            data = await self._post_musicu(body, cookie)
            if self._get_response_song_list(data):
                break
            if attempt < 3:
                await asyncio.sleep(0.8 + 0.6 * attempt)

        songs: list[Song] = []
        for item in self._get_response_song_list(data):
            singers = "/".join(
                singer.get("name")
                for singer in item.get("singer", [])
                if singer.get("name")
            )
            album = item.get("album") or {}
            album_mid = album.get("mid") or ""
            cover_url = (
                f"https://y.gtimg.cn/music/photo_new/T002R300x300M000{album_mid}.jpg"
                if album_mid
                else None
            )
            interval = item.get("interval") or 0
            songs.append(
                Song(
                    id=str(item.get("id") or ""),
                    source=self.platform.name,
                    name=item.get("name"),
                    artists=singers,
                    duration=interval * 1000 if interval else None,
                    cover_url=cover_url,
                    audio_url=None,
                    note=item.get("mid") or "",
                )
            )
        return songs
