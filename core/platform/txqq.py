from typing import ClassVar

from astrbot.api import logger

from ..config import PluginConfig
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
        name="txqq",
        display_name="TXQQ聚合平台",
        keywords=[
            "qq",
            "酷狗",
            "酷我",
            "百度",
            "一听",
            "咪咕",
            "荔枝蜻蜓",
            "喜马拉雅",
            "5sing原创",
            "5sing翻唱",
            "全民K歌",
        ],
    )

    PLATFORM_MAP = {
        "qq": ["qq"],
        "kugou": ["酷狗"],
        "kuwo": ["酷我"],
        "baidu": ["百度"],
        "1ting": ["一听"],
        "migu": ["咪咕"],
        "lizhi": ["荔枝"],
        "qingting": ["蜻蜓"],
        "ximalaya": ["喜马拉雅"],
        "5singyc": ["5sing原创"],
        "5singfc": ["5sing翻唱"],
        "kg": ["全民k歌"],
    }

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

    def __init__(self, config: PluginConfig):
        super().__init__(config)
        self.search_platform: str = "qq"

    def _detect_platform(self, keyword: str) -> str:
        """
        从 keyword 中自动识别平台
        返回 platform_type
        """
        raw = keyword.lower()

        for ptype, keys in self.PLATFORM_MAP.items():
            for k in keys:
                if k.lower() in raw:
                    return ptype
        return self.search_platform

    async def fetch_songs(
        self,
        keyword: str,
        limit: int = 5,
        extra: str | None = None,
    ) -> list[Song]:
        """
        获取歌曲数据
        """
        platform_type = self._detect_platform(extra) if extra else self.search_platform
        result = await self._request(
            url=self.BASE_URL,
            method="POST",
            data={
                "input": keyword,
                "filter": "name",
                "type": platform_type,
                "page": 1,
            },
            headers=self.HEADERS,
        )
        if not isinstance(result, dict) or "data" not in result:
            logger.error(f"返回了意料之外的数据：{result}")
            return []
        songs = []
        for s in result["data"]:
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
