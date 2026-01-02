import json
from abc import ABC, abstractmethod
from typing import Any

import aiohttp


class MusicPlatform(ABC):
    """
    音乐平台抽象基类
    """

    def __init__(self, config: dict):
        self.config = config

    # ---------- 基础能力 ----------

    @abstractmethod
    async def fetch_data(self, keyword: str, limit: int = 5) -> list[dict[str, Any]]:
        """
        搜索歌曲

        返回统一结构:
        [
            {
                "id": str | int,
                "name": str,
                "artists": str,
                "duration": int
            }
        ]
        """
        raise NotImplementedError

    @abstractmethod
    async def fetch_comments(self, song_id: int) -> list:
        """获取热评"""
        raise NotImplementedError

    @abstractmethod
    async def fetch_lyrics(self, song_id: int) -> str:
        """获取歌词"""
        raise NotImplementedError

    @abstractmethod
    async def fetch_extra(self, song_id: str | int) -> dict[str, str]:
        """
        扩展信息（如播放链接 / 封面）

        推荐统一字段：
        {
            "title": str,
            "author": str,
            "cover_url": str,
            "audio_url": str
        }
        """
        raise NotImplementedError

    @abstractmethod
    async def close(self):
        """释放资源"""
        raise NotImplementedError




class BaseHttpPlatform(MusicPlatform):
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; WOW64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/55.0.2883.87 Safari/537.36"
        )
    }

    def __init__(self, config: dict):
        super().__init__(config)
        self.session = aiohttp.ClientSession()

    async def _request(
        self,
        url: str,
        *,
        method: str = "GET",
        data: dict | None = None,
        headers: dict | None = None,
        cookies: dict | None = None,
    ):
        headers = headers or self.HEADERS

        if method.upper() == "POST":
            async with self.session.post(
                url, data=data, headers=headers, cookies=cookies
            ) as resp:
                return await self._parse_response(resp)

        async with self.session.get(url, headers=headers, cookies=cookies) as resp:
            return await self._parse_response(resp)

    async def _parse_response(self, resp: aiohttp.ClientResponse):
        ct = resp.headers.get("Content-Type", "")
        if "application/json" in ct:
            return await resp.json()
        return json.loads(await resp.text())

    async def close(self):
        await self.session.close()
