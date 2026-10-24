import asyncio
import hashlib
import time
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import ClassVar
from urllib.parse import urljoin, urlparse

import aiofiles
import aiohttp
from astrbot.api import logger

from ..config import PluginConfig
from ..model import Platform, Song
from .base import BaseMusicPlayer


class NekoMusic(BaseMusicPlayer):
    """Neko Music API adapter for search and media URL resolution."""

    platform: ClassVar[Platform] = Platform(
        name="neko",
        display_name="Neko 云音乐",
    )
    DEFAULT_BASE_URL = "https://music.nekocore.cn"
    CLIENT_NAME = "NekoMusic-pc+1.9.3"
    NONCE_BATCH_SIZE = 8
    MAX_POW_DIFFICULTY = 24
    MAX_POW_ATTEMPTS = 1 << (MAX_POW_DIFFICULTY + 3)
    HEADERS: ClassVar[dict[str, str]] = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "X-Neko-Client": CLIENT_NAME,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }

    def __init__(self, config: PluginConfig):
        super().__init__(config)
        self.base_url = (self.platform_cfg.base_url or self.DEFAULT_BASE_URL).rstrip(
            "/"
        )
        self._nonce_pools = {"read": [], "write": []}
        self._nonce_expiry: dict[str, float | None] = {"read": None, "write": None}
        self._nonce_lock = asyncio.Lock()

    def _api_headers(self) -> dict[str, str]:
        """Build headers required by the Neko API client contract."""
        headers = dict(self.HEADERS)
        headers["Origin"] = self.base_url
        headers["Referer"] = f"{self.base_url}/"
        return headers

    @staticmethod
    def _solve_challenge(seed: str, difficulty: int, max_attempts: int) -> str:
        """Find a SHA-256 proof for a server-issued replay challenge.

        Args:
            seed: Random challenge seed returned by the API.
            difficulty: Required number of leading zero bits.
            max_attempts: Upper bound on counters to test.

        Returns:
            The decimal counter that satisfies the challenge.

        Raises:
            RuntimeError: If no proof is found within the work budget.
        """
        target = 1 << (256 - difficulty) if difficulty else 1 << 256
        for counter in range(max_attempts):
            digest = hashlib.sha256(f"{seed}:{counter}".encode()).digest()
            if int.from_bytes(digest, "big") < target:
                return str(counter)
        raise RuntimeError("Neko API replay challenge exceeded the work budget")

    async def _fetch_nonce_batch(self, nonce_type: str) -> None:
        """Exchange a bounded proof-of-work challenge for one-use nonces."""
        count = self.NONCE_BATCH_SIZE
        requested = {"read": count if nonce_type == "read" else 0}
        requested["write"] = count if nonce_type == "write" else 0
        session = self._get_session()
        proxy = self.platform_cfg.proxy or None

        for challenge_attempt in range(2):
            async with session.get(
                f"{self.base_url}/api/replay/challenge",
                params=requested,
                headers=self._api_headers(),
                proxy=proxy,
                timeout=15,
            ) as response:
                if response.status != 200:
                    raise RuntimeError(
                        f"Neko API challenge returned HTTP {response.status}"
                    )
                challenge_body = await response.json(content_type=None)

            challenge_data = (
                challenge_body.get("data") if isinstance(challenge_body, dict) else None
            )
            if not isinstance(challenge_data, dict) or not challenge_body.get(
                "success"
            ):
                raise RuntimeError("Neko API returned an invalid replay challenge")
            if challenge_data.get("algorithm") != "sha256-leading-zero-bits":
                if challenge_attempt == 0:
                    continue
                raise RuntimeError(
                    "Neko API returned an unsupported challenge algorithm"
                )

            seed = challenge_data.get("seed")
            challenge = challenge_data.get("challenge")
            difficulty = challenge_data.get("difficulty")
            if (
                not isinstance(seed, str)
                or not isinstance(challenge, str)
                or not isinstance(difficulty, int)
                or isinstance(difficulty, bool)
            ):
                raise TypeError("Neko API returned invalid replay challenge fields")
            if difficulty < 0 or difficulty > self.MAX_POW_DIFFICULTY:
                raise RuntimeError(
                    f"Neko API challenge difficulty {difficulty} exceeds client capacity"
                )

            proof = await asyncio.to_thread(
                self._solve_challenge,
                seed,
                difficulty,
                self.MAX_POW_ATTEMPTS,
            )
            async with session.get(
                f"{self.base_url}/api/replay/nonce",
                params={**requested, "challenge": challenge, "proof": proof},
                headers=self._api_headers(),
                proxy=proxy,
                timeout=15,
            ) as response:
                if response.status == 409 and challenge_attempt == 0:
                    continue
                if response.status != 200:
                    raise RuntimeError(
                        f"Neko API nonce exchange returned HTTP {response.status}"
                    )
                nonce_body = await response.json(content_type=None)

            nonce_data = (
                nonce_body.get("data") if isinstance(nonce_body, dict) else None
            )
            nonce_lists = (
                nonce_data.get("nonces") if isinstance(nonce_data, dict) else None
            )
            values = (
                nonce_lists.get(nonce_type) if isinstance(nonce_lists, dict) else None
            )
            if (
                not isinstance(values, list)
                or len(values) < count
                or any(
                    not isinstance(value, str) or not value for value in values[:count]
                )
                or not nonce_body.get("success")
            ):
                raise RuntimeError("Neko API returned an invalid nonce batch")

            expires_in = nonce_data.get("expiresIn")
            self._nonce_expiry[nonce_type] = (
                time.monotonic() + expires_in
                if isinstance(expires_in, (int, float)) and expires_in > 0
                else None
            )
            self._nonce_pools[nonce_type] = values[:count]
            return

        raise RuntimeError("Neko API rejected the replay challenge")

    async def _get_api_nonce(self, method: str) -> str:
        """Return an unused nonce matching the HTTP method."""
        nonce_type = "read" if method.upper() in {"GET", "HEAD"} else "write"
        async with self._nonce_lock:
            expiry = self._nonce_expiry[nonce_type]
            if expiry is not None and time.monotonic() >= expiry:
                self._nonce_pools[nonce_type].clear()
            if not self._nonce_pools[nonce_type]:
                await self._fetch_nonce_batch(nonce_type)
            return self._nonce_pools[nonce_type].pop()

    async def _request_api(self, method: str, endpoint: str, **kwargs):
        """Send an API request with a fresh nonce and one conflict retry."""
        session = self._get_session()
        proxy = self.platform_cfg.proxy or None
        headers = self._api_headers()
        headers.update(kwargs.pop("headers", {}))

        for attempt in range(2):
            request_headers = dict(headers)
            request_headers["X-Neko-Nonce"] = await self._get_api_nonce(method)
            async with session.request(
                method,
                f"{self.base_url}{endpoint}",
                headers=request_headers,
                proxy=proxy,
                timeout=15,
                **kwargs,
            ) as response:
                if response.status == 409 and attempt == 0:
                    nonce_type = (
                        "read" if method.upper() in {"GET", "HEAD"} else "write"
                    )
                    async with self._nonce_lock:
                        self._nonce_pools[nonce_type].clear()
                        self._nonce_expiry[nonce_type] = None
                    continue
                if response.status != 200:
                    body = (await response.text())[:200]
                    logger.warning(
                        f"Neko API {method} {endpoint} returned HTTP "
                        f"{response.status}: {body}"
                    )
                    return None
                try:
                    return await response.json(content_type=None)
                except ValueError as exc:
                    logger.warning(f"Neko API returned invalid JSON: {exc}")
                    return None
        return None

    async def fetch_songs(
        self,
        keyword: str,
        limit: int,
        extra: str | None = None,
    ) -> list[Song]:
        """Search songs with the Neko Music API.

        Args:
            keyword: Song or artist search text.
            limit: Maximum number of results to return.
            extra: Unused platform-specific command context.

        Returns:
            Matching Neko Music songs.
        """
        del extra
        result = await self._request_api(
            "POST",
            "/api/music/search",
            json={"query": keyword},
        )
        songs_data = result.get("results") if isinstance(result, Mapping) else None
        if not isinstance(result, Mapping) or not result.get("success"):
            logger.warning("Neko Music search returned an unsuccessful response")
            return []
        if not isinstance(songs_data, list):
            logger.warning("Neko Music search returned an invalid result list")
            return []

        songs = []
        for item in songs_data[:limit]:
            if not isinstance(item, Mapping) or item.get("id") is None:
                continue
            song_id = str(item["id"])
            artists = item.get("artist", item.get("singer", item.get("ar")))
            if isinstance(artists, list):
                artists = "、".join(
                    artist.get("name", "")
                    if isinstance(artist, Mapping)
                    else str(artist)
                    for artist in artists
                )
            elif isinstance(artists, Mapping):
                artists = artists.get("name")
            album = item.get("album", item.get("al"))
            if isinstance(album, Mapping):
                album = album.get("name")
            if not isinstance(album, str):
                album = None
            duration = item.get("duration")
            if isinstance(duration, (int, float)) and 0 < duration <= 14400:
                duration = int(duration * 1000)
            songs.append(
                Song(
                    id=song_id,
                    source=self.platform.name,
                    name=item.get("name", item.get("title")),
                    artists=str(artists) if artists else None,
                    duration=int(duration)
                    if isinstance(duration, (int, float))
                    else None,
                    cover_url=f"{self.base_url}/api/music/cover/{song_id}",
                    note=album,
                )
            )
        return songs

    async def fetch_extra(self, song: Song) -> Song:
        """Resolve the Neko API media pointer to a downloadable URL.

        Args:
            song: Song returned by the Neko search API.

        Returns:
            The song with its direct audio URL when available.
        """
        if song.audio_url:
            return song
        result = await self._request_api("GET", f"/api/music/file/{song.id}")
        data = result.get("data") if isinstance(result, Mapping) else None
        media_url = data.get("url") if isinstance(data, Mapping) else None
        if (
            isinstance(result, Mapping)
            and result.get("success")
            and isinstance(media_url, str)
        ):
            song.audio_url = urljoin(f"{self.base_url}/", media_url)
        else:
            logger.warning(f"Neko Music did not return an audio URL for song {song.id}")
        return song

    async def download_cover(self, url: str) -> bytes | None:
        """Download a Neko cover using the platform proxy and client headers.

        Args:
            url: Cover image URL.

        Returns:
            Image bytes, or None if the request fails.
        """
        try:
            async with self._get_session().get(
                url,
                headers=self._api_headers(),
                proxy=self.platform_cfg.proxy or None,
                timeout=15,
            ) as response:
                if response.status != 200:
                    return None
                return await response.read()
        except (TimeoutError, aiohttp.ClientError, OSError) as exc:
            logger.warning(f"Neko Music cover download failed: {exc}")
            return None

    async def download_audio(self, url: str) -> Path | None:
        """Download Neko media with required client headers.

        Args:
            url: Direct media URL resolved by the Neko API.

        Returns:
            Path to the downloaded audio, or None if the request fails.
        """
        suffix = Path(urlparse(url).path).suffix.lower()
        if suffix not in {".mp3", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wav"}:
            suffix = ".mp3"
        self.cfg.temp_dir.mkdir(parents=True, exist_ok=True)
        file_path = self.cfg.temp_dir / f"{uuid.uuid4().hex}{suffix}"
        try:
            async with self._get_session().get(
                url,
                headers=self._api_headers(),
                proxy=self.platform_cfg.proxy or None,
                timeout=120,
            ) as response:
                if response.status != 200:
                    logger.warning(
                        f"Neko Music audio download returned HTTP {response.status}"
                    )
                    return None
                async with aiofiles.open(file_path, "wb") as file:
                    async for chunk in response.content.iter_chunked(64 * 1024):
                        await file.write(chunk)
            return file_path
        except (TimeoutError, aiohttp.ClientError, OSError) as exc:
            file_path.unlink(missing_ok=True)
            logger.error(f"Neko Music audio download failed: {exc}")
            return None

    async def fetch_comments(self, song: Song) -> Song:
        """Return the song unchanged because this source has no comment API.

        Args:
            song: Song returned by the Neko search API.

        Returns:
            The original song.
        """
        return song

    async def fetch_lyrics(self, song: Song) -> Song:
        """Return the song unchanged because this source has no lyrics API.

        Args:
            song: Song returned by the Neko search API.

        Returns:
            The original song.
        """
        return song
