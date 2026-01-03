from typing import ClassVar

from ..model import Platform, Song
from .base import BaseMusicPlayer


class NetEaseMusic(BaseMusicPlayer):
    """
    网易云音乐（Web API）
    """
    platform: ClassVar[Platform] = Platform(name="ncm", display_name="网易云音乐", keywords=["网易"],)
    def __init__(self, config: dict):
        super().__init__(config)

    async def fetch_songs(self, keyword: str, limit=5) -> list[Song]:
        result = await self._request(
            url="http://music.163.com/api/search/get/web",
            method="POST",
            data={"s": keyword, "limit": limit, "type": 1, "offset": 0},
            cookies={"appver": "2.0.2"},
        )

        songs = result["result"]["songs"][:limit]

        return [
            Song(
                id=s.get("id"),
                name=s.get("name"),
                artists="、".join(a["name"] for a in s["artists"]),
                duration=s.get("duration"),
            )
            for s in songs
        ]

