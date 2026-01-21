
import json
from abc import ABC, abstractmethod
from typing import ClassVar

import aiohttp

from astrbot.api import logger

from ..config import PluginConfig
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

    def __init__(self, config: PluginConfig):
        self.cfg = config
        self.session = aiohttp.ClientSession(proxy=self.cfg.http_proxy)

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
    async def fetch_songs(
        self, keyword: str, limit: int, extra: str | None = None
    ) -> list[Song]:
        """
        搜索歌曲
        :param keyword: 搜索关键字
        :param limit: 搜索数量
        :param extra: 额外参数
        """
        raise NotImplementedError

    # ---------- 可复用方法 ----------
    async def fetch_extra(self, song: Song) -> Song:
        """默认获取额外信息的实现"""
        url = f"https://api.qijieya.cn/meting/?type=song&id={song.id}"

        result = await self._request(url)

        if result and isinstance(result, list) and len(result) > 0:
            data = result[0]
            if not song.audio_url:
                song.audio_url = data.get("url")
            if not song.cover_url:
                song.cover_url = data.get("pic")
            if not song.lyrics:
                song.lyrics = data.get("lrc")
        return song

    async def fetch_comments(self, song: Song) -> Song:
        """
        默认获取热门评论的实现
        """
        if song.comments:
            return song

        try:
            result = await self._request(
                url=f"https://music.163.com/weapi/v1/resource/hotcomments/R_SO_4_{song.id}?csrf_token=",
                method="POST",
                data={
                    "params": self.cfg.enc_params,
                    "encSecKey": self.cfg.enc_sec_key,
                },
            )
        except Exception as e:
            logger.warning(f"{self.__class__.__name__} fetch_comments 失败: {e}")
            return song

        comments = result.get("hotComments") if isinstance(result, dict) else []

        if comments:
            song.comments = comments

        return song

    async def fetch_lyrics(self, song: Song):
        """
        默认获取歌词的实现
        """
        if song.lyrics:
            return song
        url = f"https://api.qijieya.cn/meting/?server=netease&type=lrc&id={song.id}"
        try:
            result = await self._request(url)
            lyrics = result.get("lyric") if isinstance(result, dict) else str(result)
            song.lyrics = lyrics
            return song
        except Exception as e:
            logger.warning(f"{self.__class__.__name__} fetch_lyrics 失败: {e}")
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
    ):
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
        try:
            resp_text = await resp.text()

            if resp.status != 200:
                logger.warning(f"HTTP 请求返回 {resp.status}: {resp_text[:200]}")
                return None

            if not resp_text.strip():
                logger.warning("HTTP 响应为空")
                return None

            try:
                return json.loads(resp_text)
            except json.JSONDecodeError:
                return resp_text


        except Exception as e:
            logger.warning(f"解析响应失败: {e}")
            return None


