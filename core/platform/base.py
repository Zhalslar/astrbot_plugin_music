import json
from abc import ABC, abstractmethod
from typing import ClassVar

import aiohttp

from astrbot.api import logger

from ..model import Platform, Song


class BaseMusicPlayer(ABC):
    """
    全功能音乐平台基类 + HTTP 支持
    子类必须实现：
    - platform: 平台信息（包含名称和显示名称)
    - fetch_songs: 获取歌曲列表
    """

    _registry: ClassVar[list[type["BaseMusicPlayer"]]] = []
    """ 存储所有已注册的 MusicPlatform 类 """

    platform: ClassVar[Platform]
    """ 平台信息（包含名称和显示名称） """

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; WOW64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/55.0.2883.87 Safari/537.36"
        )
    }

    def __init__(self, config: dict):
        self.config = config
        self.proxy = config["proxy"] or None
        self.session = aiohttp.ClientSession(proxy=self.proxy)

    def __init_subclass__(cls, **kwargs):
        """自动注册子类到 _registry"""
        super().__init_subclass__(**kwargs)
        if ABC not in cls.__bases__:  # 跳过抽象类
            BaseMusicPlayer._registry.append(cls)

    @classmethod
    def get_all_subclass(cls) -> list[type["BaseMusicPlayer"]]:
        """获取所有已注册的 Parser 类"""
        return cls._registry

    # ---------- 子类必须实现 ----------

    @abstractmethod
    async def fetch_songs(self, keyword: str, **kwargs) -> list[Song]:
        """搜索歌曲"""
        raise NotImplementedError

    # ---------- 可复用方法 ----------

    async def fetch_extra(self, song: Song) -> Song:
        url = f"https://www.hhlqilongzhu.cn/api/dg_wyymusic.php?id={song.id}&br=7&type=json"
        try:
            async with self.session.get(url) as resp:
                result = await resp.json(content_type=None)
                if not isinstance(result, dict):
                    return song
        except Exception as e:
            logger.warning(f"NetEaseMusic fetch_extra 失败: {e}")
            return song

        # 自己映射 JSON -> Song 属性
        mapping = {
            "title": "title",
            "singer": "author",
            "cover": "cover_url",
            "music_url": "audio_url",
        }
        for json_key, attr in mapping.items():
            value = result.get(json_key)
            if value and getattr(song, attr) is None:
                setattr(song, attr, value)

        return song

    async def fetch_comments(self, song: Song) -> Song:
        """
        默认获取热门评论的实现（如果配置了 enc_params 和 enc_sec_key）
        子类可覆盖以适配不同平台
        """
        if not (self.config.get("enc_params") and self.config.get("enc_sec_key")):
            return song

        try:
            result = await self._request(
                url=f"https://music.163.com/weapi/v1/resource/hotcomments/R_SO_4_{song.id}?csrf_token=",
                method="POST",
                data={
                    "params": self.config["enc_params"],
                    "encSecKey": self.config["enc_sec_key"],
                },
            )
        except Exception as e:
            logger.warning(f"{self.__class__.__name__} fetch_comments 失败: {e}")
            return song

        if comments := result.get("hotComments"):
            song.comments = comments

        return song

    async def fetch_lyrics(self, song: Song) -> Song:
        """默认返回占位歌词，子类可覆盖"""
        return song

    async def close(self):
        """释放 session"""
        if not self.session.closed:
            await self.session.close()

    # ---------- 内部 HTTP 方法 ----------

    async def _request(
        self,
        url: str,
        *,
        method: str = "GET",
        data: dict | None = None,
        headers: dict | None = None,
        cookies: dict | None = None,
        ssl: bool = True,
    ) -> dict:
        headers = headers or self.HEADERS

        if method.upper() == "POST":
            async with self.session.post(
                url, data=data, headers=headers, cookies=cookies, ssl=ssl
            ) as resp:
                return await self._parse_response(resp)

        async with self.session.get(
            url, headers=headers, cookies=cookies, ssl=ssl
        ) as resp:
            return await self._parse_response(resp)

    async def _parse_response(self, resp: aiohttp.ClientResponse):
        """
        解析 HTTP 响应为 JSON 或文本
        """
        try:
            resp_text = await resp.text()
            if resp.status != 200:
                logger.warning(f"HTTP 请求返回 {resp.status}: {resp_text[:200]}")
                return {}

            if not resp_text.strip():  # 空字符串直接返回空 dict
                logger.warning("HTTP 响应为空")
                return {}

            content_type = resp.headers.get("Content-Type", "")
            if "application/json" in content_type:
                return await resp.json(content_type=None)

            # 尝试解析 JSON
            try:
                return json.loads(resp_text)
            except json.JSONDecodeError:
                logger.warning(f"HTTP 响应非 JSON: {resp_text}")
                return {}
        except Exception as e:
            logger.warning(f"解析响应失败: {e}")
            return {}
