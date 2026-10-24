import asyncio
import gzip
import json
import urllib.request
import uuid
from pathlib import Path
from typing import Any, ClassVar

import aiofiles

from astrbot.api import logger

from ..config import PluginConfig
from ..model import Platform, Song
from .base import BaseMusicPlayer


class QQMusicOfficial(BaseMusicPlayer):
    """QQ Music search and playback integration."""

    platform = Platform(
        name="qqmusic",
        display_name="QQ音乐",
    )

    API_URL = "https://u.y.qq.com/cgi-bin/musicu.fcg"
    DOWNLOAD_HEADERS: ClassVar[dict[str, str]] = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/153.0.0.0 Safari/537.36 Edg/153.0.0.0"
        ),
        "Referer": "https://y.qq.com/",
    }
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
        cookie = (self.platform_cfg.cookies or "").strip()
        values = self._cookie_values(cookie)
        if values.get("qqmusic_key") or values.get("qm_keyst"):
            return cookie
        return ""

    async def download_cover(self, url: str) -> bytes | None:
        """Download a QQ Music cover with urllib.

        Args:
            url: Cover image URL.

        Returns:
            Image bytes, or None if the request fails.
        """
        request = urllib.request.Request(url, headers=self.DOWNLOAD_HEADERS)
        proxy = self.platform_cfg.proxy or None
        proxy_handler = {"http": proxy, "https": proxy} if proxy else {}
        opener = urllib.request.build_opener(urllib.request.ProxyHandler(proxy_handler))
        try:
            response = await asyncio.to_thread(opener.open, request, timeout=20)
            try:
                if response.status != 200:
                    logger.warning(f"QQ Music cover returned HTTP {response.status}")
                    return None
                return await asyncio.to_thread(response.read)
            finally:
                response.close()
        except Exception as exc:
            logger.warning(f"QQ Music cover download failed: {exc}")
            return None

    async def download_audio(self, url: str) -> Path | None:
        """Download QQ Music audio with urllib.

        Args:
            url: Audio URL.

        Returns:
            Path to the downloaded file, or None if the request fails.
        """
        self.cfg.temp_dir.mkdir(parents=True, exist_ok=True)
        file_path = self.cfg.temp_dir / f"{uuid.uuid4().hex}.mp3"
        request = urllib.request.Request(url, headers=self.DOWNLOAD_HEADERS)
        proxy = self.platform_cfg.proxy or None
        proxy_handler = {"http": proxy, "https": proxy} if proxy else {}
        opener = urllib.request.build_opener(urllib.request.ProxyHandler(proxy_handler))
        try:
            response = await asyncio.to_thread(opener.open, request, timeout=30)
            try:
                if response.status != 200:
                    logger.warning(f"QQ Music audio returned HTTP {response.status}")
                    return None
                async with aiofiles.open(file_path, "wb") as file:
                    while chunk := await asyncio.to_thread(response.read, 64 * 1024):
                        await file.write(chunk)
            finally:
                response.close()
            logger.debug(f"QQ Music audio downloaded to: {file_path}")
            return file_path
        except Exception as exc:
            file_path.unlink(missing_ok=True)
            logger.error(f"QQ Music audio download failed: {exc}")
            return None

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
            proxy = self.platform_cfg.proxy or None
            proxy_handler = {"http": proxy, "https": proxy} if proxy else {}
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler(proxy_handler)
            )
            response = await asyncio.to_thread(opener.open, request, timeout=15)
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
        configured_uin = (self.platform_cfg.uin or "").strip()
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

    async def fetch_extra(self, song: Song) -> Song:
        """Resolve a QQ Music audio URL using the song's official song MID.

        Args:
            song: Song returned by the QQ Music search API.

        Returns:
            The song with an audio URL when QQ Music provides one.
        """
        if song.audio_url or not song.note:
            return song

        configured_uin = (self.platform_cfg.uin or "").strip()
        if not configured_uin:
            logger.warning("QQ Music UIN is not configured; cannot resolve audio")
            return song
        try:
            uin = int(configured_uin)
        except ValueError:
            logger.warning("QQ Music UIN must be numeric; cannot resolve audio")
            return song

        cookie = self._get_cookie()
        body = {
            "comm": {
                "uin": uin,
                "format": "json",
                "ct": 24,
                "cv": 0,
            },
            "req_0": {
                "module": "vkey.GetVkeyServer",
                "method": "CgiGetVkey",
                "param": {
                    "filename": [f"M500{song.note}{song.note}.mp3"],
                    "guid": "10000",
                    "songmid": [song.note],
                    "songtype": [0],
                    "uin": configured_uin,
                    "loginflag": 1,
                    "platform": "20",
                },
            },
        }
        data = await self._post_musicu(body, cookie)
        request_data = data.get("req_0") if data else None
        response_data = (
            request_data.get("data") if isinstance(request_data, dict) else None
        )
        if not isinstance(response_data, dict):
            response_data = {}
        servers = response_data.get("sip") or []
        url_info = response_data.get("midurlinfo") or []
        if (
            servers
            and isinstance(url_info, list)
            and url_info
            and isinstance(url_info[0], dict)
            and url_info[0].get("purl")
        ):
            song.audio_url = servers[0] + url_info[0]["purl"]
        else:
            logger.warning(f"QQ Music did not return an audio URL for song {song.note}")
        return song
