from typing import ClassVar

from astrbot.api import logger

from ..config import PluginConfig
from ..model import Platform, Song
from .base import BaseMusicPlayer


class NetEaseMusic(BaseMusicPlayer):
    """
    网易云音乐（Web API）
    """

    platform: ClassVar[Platform] = Platform(
        name="netease",
        display_name="网易云音乐",
        keywords=["网易云", "网易点歌"],
    )

    def __init__(self, config: PluginConfig):
        super().__init__(config)

    async def fetch_songs(self, keyword: str, limit=5, extra=None) -> list[Song]:
        result = await self._request(
            url="http://music.163.com/api/search/get/web",
            method="POST",
            data={"s": keyword, "limit": limit, "type": 1, "offset": 0},
            cookies={"appver": "2.0.2"},
        )
        if (
            not isinstance(result, dict)
            or "result" not in result
            or "songs" not in result["result"]
        ):
            logger.error(f"返回了意料之外数据：{result}")
            return []

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
