import base64
import time
from typing import Any, ClassVar

from astrbot.api import logger

from ..config import PluginConfig
from ..model import Platform, Song
from .base import BaseMusicPlayer


class SpotifyMusic(BaseMusicPlayer):
    platform: ClassVar[Platform] = Platform(
        name="spotify",
        display_name="Spotify",
        keywords=["spotify点歌", "spotify", "Spotify点歌", "Spotify"],
    )

    TOKEN_URL = "https://accounts.spotify.com/api/token"
    SEARCH_URL = "https://api.spotify.com/v1/search"

    def __init__(self, config: PluginConfig):
        super().__init__(config)
        self._access_token: str | None = None
        self._token_expires_at = 0.0

    def _has_credentials(self) -> bool:
        return bool(self.cfg.spotify_client_id and self.cfg.spotify_client_secret)

    def is_configured(self) -> bool:
        return self._has_credentials()

    async def _get_access_token(self) -> str | None:
        if not self._has_credentials():
            logger.warning("Spotify 凭证未配置，跳过 Spotify 点歌")
            return None

        now = time.time()
        if self._access_token and now < self._token_expires_at:
            return self._access_token

        basic_token = base64.b64encode(
            f"{self.cfg.spotify_client_id}:{self.cfg.spotify_client_secret}".encode(
                "utf-8"
            )
        ).decode("utf-8")
        headers = {
            "Authorization": f"Basic {basic_token}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        try:
            async with self.session.post(
                self.TOKEN_URL,
                data={"grant_type": "client_credentials"},
                headers=headers,
            ) as resp:
                result = await self._parse_response(resp)
        except Exception as e:
            logger.warning(f"Spotify token 获取失败: {e}")
            return None

        if not isinstance(result, dict) or "access_token" not in result:
            logger.warning(f"Spotify token 返回异常: {result}")
            return None

        expires_in = int(result.get("expires_in", 3600))
        self._access_token = result["access_token"]
        self._token_expires_at = now + max(expires_in - 60, 0)
        return self._access_token

    @staticmethod
    def _pick_cover(track: dict[str, Any]) -> str | None:
        images = track.get("album", {}).get("images") or []
        if not images:
            return None
        return images[0].get("url")

    @staticmethod
    def _map_track(track: dict[str, Any]) -> Song:
        artists = "/".join(
            artist.get("name", "未知歌手") for artist in track.get("artists", [])
        )
        external_url = (track.get("external_urls") or {}).get("spotify")
        return Song(
            id=track.get("id", ""),
            name=track.get("name"),
            artists=artists or None,
            duration=track.get("duration_ms"),
            cover_url=SpotifyMusic._pick_cover(track),
            audio_url=external_url,
            note="Spotify 外链，仅支持文本发送",
        )

    async def fetch_songs(
        self, keyword: str, limit: int, extra: str | None = None
    ) -> list[Song]:
        token = await self._get_access_token()
        if not token:
            return []

        headers = {"Authorization": f"Bearer {token}"}
        params = {
            "q": keyword,
            "type": "track",
            "limit": limit,
        }

        try:
            async with self.session.get(
                self.SEARCH_URL,
                params=params,
                headers=headers,
            ) as resp:
                result = await self._parse_response(resp)
        except Exception as e:
            logger.warning(f"Spotify 搜索失败: {e}")
            return []

        if not isinstance(result, dict):
            logger.warning(f"Spotify 搜索返回异常: {result}")
            return []

        items = result.get("tracks", {}).get("items", [])
        return [self._map_track(track) for track in items[:limit] if track.get("id")]

    async def fetch_extra(self, song: Song) -> Song:
        if song.audio_url:
            return song

        token = await self._get_access_token()
        if not token or not song.id:
            return song

        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with self.session.get(
                f"https://api.spotify.com/v1/tracks/{song.id}",
                headers=headers,
            ) as resp:
                result = await self._parse_response(resp)
        except Exception as e:
            logger.warning(f"Spotify 详情获取失败: {e}")
            return song

        if not isinstance(result, dict):
            return song

        mapped_song = self._map_track(result)
        song.audio_url = mapped_song.audio_url
        song.cover_url = song.cover_url or mapped_song.cover_url
        song.duration = song.duration or mapped_song.duration
        song.note = mapped_song.note
        return song

    async def fetch_comments(self, song: Song) -> Song:
        return song

    async def fetch_lyrics(self, song: Song):
        return song
