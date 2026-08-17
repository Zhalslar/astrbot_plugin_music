import json
from typing import Any

import aiohttp

from astrbot.api import logger

from .config import PluginConfig
from .model import Song
from .platform import BaseMusicPlayer


class CZCard:
    """Fetch signed CZ music cards with a reusable HTTP session."""

    API_URL = "https://api.czcn.xyz/api/qqyykp"
    FORMAT_MAP = {
        "163": "163",
        "netease": "163",
        "netease_nodejs": "163",
        "qq": "qq",
        "txqq": "qq",
        "kugou": "kugou",
        "kuwo": "kuwo",
        "migu": "migu",
    }
    REQUIRED_FIELDS = {"app", "meta", "prompt", "view"}

    def __init__(self, config: PluginConfig):
        self.ckey = config.cz_ckey
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=config.timeout),
            proxy=config.http_proxy,
        )

    async def close(self) -> None:
        await self.session.close()

    async def fetch(self, player: BaseMusicPlayer, song: Song) -> dict[str, Any] | None:
        """Fetch a signed music card.

        Args:
            player: Music player that produced the song.
            song: Song data used to build the card.

        Returns:
            The signed card payload, or None when the request fails.
        """
        if not song.audio_url or not song.cover_url:
            song = await player.fetch_extra(song)
        if not song.audio_url:
            logger.warning(f"CZ card is missing an audio URL: {song.name}")
            return None

        source = song.source or player.platform.name
        card_format = self.FORMAT_MAP.get(source)
        if card_format is None:
            logger.warning(f"CZ card does not support music source: {source}")
            return None

        if card_format == "163":
            jump_url = f"https://music.163.com/song?id={song.id}"
        elif card_format == "qq":
            jump_url = f"https://y.qq.com/n/ryqq/songDetail/{song.id}"
        else:
            jump_url = song.audio_url

        try:
            cover_url = song.cover_url or ""
            if cover_url:
                async with self.session.get(
                    cover_url, allow_redirects=True
                ) as response:
                    response.raise_for_status()
                    cover_url = str(response.url)

            params = {
                "type": card_format,
                "url": jump_url,
                "audio": song.audio_url,
                "title": song.name,
                "desc": song.artists,
                "image": cover_url,
            }
            if self.ckey:
                params["ckey"] = self.ckey

            async with self.session.get(self.API_URL, params=params) as response:
                response.raise_for_status()
                data = await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, json.JSONDecodeError) as exc:
            logger.warning(f"CZ card request failed: {type(exc).__name__}")
            return None

        if not isinstance(data, dict) or not self.REQUIRED_FIELDS.issubset(data):
            logger.warning("CZ card returned an invalid payload")
            return None
        return data
