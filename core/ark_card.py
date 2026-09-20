import json
from typing import Any

import aiohttp

from astrbot.api import logger

from .config import PluginConfig
from .model import Song
from .platform import BaseMusicPlayer


class ArkCard:
    """Fetch signed music cards from configurable Ark-compatible services."""

    API_URL = "https://apii.xianyuw.cn/api/v1/qq-musicArk"
    FORMAT_MAP = {
        "qq": "qq",
        "txqq": "qq",
        "netease": "netease",
        "netease_nodejs": "netease",
        "kugou": "kugou",
        "bilibili": "bilibili",
    }
    REQUIRED_FIELDS = {"app", "meta", "prompt", "view"}

    def __init__(self, config: PluginConfig):
        self.key = config.ark_key
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=config.timeout),
            proxy=config.http_proxy,
        )

    async def close(self) -> None:
        await self.session.close()

    async def _resolve_cover_url(self, cover_url: str) -> str:
        """Resolve a cover URL to its final HTTP redirect target.

        Args:
            cover_url: Original cover image URL.

        Returns:
            The final redirected URL, or the original URL when resolution fails.
        """
        try:
            async with self.session.get(
                cover_url, allow_redirects=True
            ) as cover_response:
                cover_response.raise_for_status()
                return str(cover_response.url)
        except (aiohttp.ClientError, TimeoutError) as exc:
            logger.warning(
                f"Ark card cover redirect failed ({type(exc).__name__}); "
                "using the original URL"
            )
            return cover_url

    async def fetch(self, player: BaseMusicPlayer, song: Song) -> dict[str, Any] | None:
        """Fetch a signed Ark music card.

        Args:
            player: Music player that produced the song.
            song: Song data used to build the card.

        Returns:
            The signed card payload, or None when the request fails.
        """
        if not song.audio_url or not song.cover_url:
            logger.warning(f"Ark card is missing required song data: {song.name}")
            return None
        singer = song.artists or song.author or "Unknown artist"

        source = (song.source or player.platform.name).lower()
        card_format = self.FORMAT_MAP.get(source)
        if card_format is None:
            logger.warning(f"Ark card does not support music source: {source}")
            return None

        cover_url = await self._resolve_cover_url(song.cover_url)

        params = {
            "key": self.key,
            "url": song.audio_url,
            "song": song.name,
            "singer": singer,
            "cover": cover_url,
            "jump": song.audio_url,
            "format": card_format,
        }
        try:
            async with self.session.get(self.API_URL, params=params) as response:
                response.raise_for_status()
                result = await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, json.JSONDecodeError) as exc:
            logger.warning(f"Ark card request failed: {type(exc).__name__}")
            return None

        data = result.get("data") if isinstance(result, dict) else None
        if (
            not isinstance(result, dict)
            or result.get("code") != 200
            or not isinstance(data, dict)
            or not self.REQUIRED_FIELDS.issubset(data)
        ):
            logger.warning("Ark card returned an invalid payload")
            return None
        return data
