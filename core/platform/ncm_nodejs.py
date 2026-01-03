from typing import ClassVar

from astrbot.api import logger

from ..model import Platform, Song
from .base import BaseMusicPlayer


class NetEaseMusicNodeJS(BaseMusicPlayer):
    """
    网易云音乐 NodeJS API
    """

    platform: ClassVar[Platform] = Platform(
        name="ncmnj", display_name="网易云NodeJS版", keywords=["nj"]
    )

    def __init__(self, config: dict):
        super().__init__(config)
        self.base_url = config["nodejs_base_url"]

    async def fetch_songs(self, keyword: str, limit: int = 5) -> list[Song]:
        result = await self._request(
            url=f"{self.base_url}/search",
            method="POST",
            data={"keywords": keyword, "limit": limit, "type": 1, "offset": 0},
        )

        songs = result.get("result", {}).get("songs", [])[:limit]

        return [
            Song(
                id=s.get("id"),
                name=s.get("name"),
                artists="、".join(a["name"] for a in s["artists"]),
                duration=s.get("duration"),
            )
            for s in songs
        ]

    async def fetch_comments(self, song: Song) -> Song:
        result = await self._request(
            url=f"{self.base_url}/comment/hot",
            method="POST",
            data={"id": song.id, "type": 0},
        )
        if comments := result.get("hotComments"):
            song.comments = comments
        return song

    async def fetch_lyrics(self, song: Song) -> Song:
        result = await self._request(f"{self.base_url}/lyric?id={song.id}")
        lyric = result.get("lrc", {}).get("lyric")
        if lyric:
            song.lyrics = lyric
        return song

    async def fetch_extra(self, song: Song) -> Song:
        try:
            result = await self._request(
                url=f"{self.base_url}/song/url?id={song.id}",
                method="GET",
            )
            if not isinstance(result, dict):
                return song
        except Exception as e:
            logger.warning(f"{self.__class__.__name__} fetch_extra 失败: {e}")
            return song

        # NodeJS API 返回结构示例:
        # { "data": [ { "url": "...", ... } ] }
        data = result.get("data")
        if not data:
            return song

        info = data[0]
        audio_url = info.get("url")
        if audio_url and song.audio_url is None:
            song.audio_url = audio_url

        return song
