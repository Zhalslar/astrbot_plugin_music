from typing import ClassVar

from ..model import Platform, Song
from .base import BaseMusicPlayer

"""
Txqq音乐聚合平台

支持的平台：
- qq: QQ 音乐
- netease: 网易云音乐
- kugou: 酷狗音乐
- kuwo: 酷我音乐
- baidu: 百度音乐
- 1ting: 一听音乐
- migu: 咪咕音乐
- lizhi: 荔枝FM
- qingting: 蜻蜓FM
- ximalaya: 喜马拉雅
- 5singyc: 5sing原创
- 5singfc: 5sing翻唱
- kg: 全民K歌

支持的过滤条件：
- name: 按歌曲名称搜索（默认）
- id: 按歌曲 ID 搜索
- url: 按音乐地址（URL）搜索
"""


class TXQQMusic(BaseMusicPlayer):
    """
    Txqq音乐聚合平台
    """

    platform: ClassVar[Platform] = Platform(
        name="txqq", display_name="TXQQ聚合平台", keywords=["tx"]
    )

    BASE_URL = "https://music.txqq.pro/"
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:146.0) "
            "Gecko/20100101 Firefox/146.0"
        ),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://music.txqq.pro",
        "Referer": "https://music.txqq.pro",
    }

    def __init__(self, config: dict):
        super().__init__(config)
        self.search_platform: str = (
            self.config["txqq_default_platform"].split("(", 1)[0].strip()
        )

    async def fetch_songs(
        self,
        keyword: str,
        limit: int = 5,
        filter: str = "name",
        platform: str | None = None,
        page: int = 1,
    ) -> list[Song]:
        """
        获取歌曲数据
        """
        result = await self._request(
            url=self.BASE_URL,
            method="POST",
            data={
                "input": keyword,
                "filter": filter,
                "type": self.search_platform,
                "page": page,
            },
            headers=self.HEADERS,
        )

        songs = []
        for s in result.get("data", []):
            songs.append(
                Song(
                    id=s.get("songid"),
                    name=s.get("title"),
                    artists=s.get("author"),
                    audio_url=s.get("url") or s.get("link"),
                    cover_url=s.get("pic"),
                    lyrics=s.get("lrc", ""),
                )
            )
        return songs[:limit]
