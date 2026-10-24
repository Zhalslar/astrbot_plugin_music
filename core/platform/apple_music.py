from typing import ClassVar
from urllib.parse import urlencode

from astrbot.api import logger

from ..config import PluginConfig
from ..model import Platform, Song
from .base import BaseMusicPlayer


class AppleMusic(BaseMusicPlayer):
    """Search Apple's public iTunes catalog and return its official previews."""

    platform: ClassVar[Platform] = Platform(
        name="apple_music",
        display_name="Apple Music",
    )
    SEARCH_URL = "https://itunes.apple.com/search"
    FALLBACK_REGIONS = ("US", "JP", "HK", "TW", "GB", "SG")

    def __init__(self, config: PluginConfig):
        super().__init__(config)
        self.region = (self.platform_cfg.region or "US").strip().upper()

    async def fetch_songs(
        self,
        keyword: str,
        limit: int,
        extra: str | None = None,
    ) -> list[Song]:
        """Search for tracks that have an official Apple preview.

        Args:
            keyword: Song or artist search text.
            limit: Maximum number of songs to return.
            extra: Unused platform-specific command context.

        Returns:
            Matching songs with official preview URLs.
        """
        del extra
        limit = max(1, limit)
        regions = dict.fromkeys((self.region, *self.FALLBACK_REGIONS))
        for region in regions:
            params = urlencode(
                {
                    "term": keyword,
                    "media": "music",
                    "entity": "song",
                    "limit": max(1, min(limit, 25)),
                    "country": region,
                }
            )
            try:
                result = await self._request(f"{self.SEARCH_URL}?{params}")
            except Exception as exc:
                logger.debug(f"Apple Music search in {region} failed: {exc}")
                continue

            tracks = result.get("results") if isinstance(result, dict) else None
            if not isinstance(tracks, list):
                continue

            songs = []
            for track in tracks:
                if not isinstance(track, dict) or not track.get("previewUrl"):
                    continue
                artwork = track.get("artworkUrl100") or ""
                artwork = artwork.replace("100x100bb", "300x300bb").replace(
                    "100x100", "300x300"
                )
                songs.append(
                    Song(
                        id=str(track.get("trackId") or track.get("collectionId") or ""),
                        source=self.platform.name,
                        name=track.get("trackName"),
                        artists=track.get("artistName"),
                        duration=track.get("trackTimeMillis"),
                        cover_url=artwork or None,
                        audio_url=track["previewUrl"],
                        note=track.get("collectionName"),
                    )
                )
                if len(songs) >= limit:
                    break

            if songs:
                return songs
        return []
