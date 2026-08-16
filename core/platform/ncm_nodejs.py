from typing import ClassVar

from astrbot.api import logger

from ..config import PluginConfig
from ..model import Platform, Song
from .base import BaseMusicPlayer


class NetEaseMusicNodeJS(BaseMusicPlayer):
    """
    网易云音乐 NodeJS API
    """

    platform: ClassVar[Platform] = Platform(
        name="netease_nodejs",
        display_name="网易云NodeJS版",
        keywords=["nj点歌", "网易nj"],
    )

    def __init__(self, config: PluginConfig):
        super().__init__(config)

    async def fetch_songs(self, keyword: str, limit: int = 5, extra=None) -> list[Song]:
        result = await self._request(
            url=f"{self.cfg.nodejs_base_url}/search",
            method="POST",
            data={"keywords": keyword, "limit": limit, "type": 1, "offset": 0},
        )
        if (
            not isinstance(result, dict)
            or "result" not in result
            or "songs" not in result["result"]
        ):
            logger.error(f"返回了意料之外数据：{result}")
            return []

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
        if song.comments:
            return song
        result = await self._request(
            url=f"{self.cfg.nodejs_base_url}/comment/hot",
            method="POST",
            data={"id": song.id, "type": 0},
        )
        if not isinstance(result, dict) or "hotComments" not in result:
            logger.error(f"返回了意料之外数据：{result}")
            return song
        if comments := result.get("hotComments"):
            song.comments = comments
        return song

    async def fetch_lyrics(self, song: Song) -> Song:
        if song.lyrics:
            return song
        result = await self._request(f"{self.cfg.nodejs_base_url}/lyric?id={song.id}")
        if not isinstance(result, dict) or "lrc" not in result:
            logger.error(f"返回了意料之外数据：{result}")
            return song
        lyric = result["lrc"].get("lyric")
        if lyric:
            song.lyrics = lyric
        return song

    async def fetch_extra(self, song: Song) -> Song:
        """快速解析音频 + 补封面，并行执行。"""
        import asyncio
        import time

        async def _resolve_audio():
            # 1. meting API 快速获取（通常 <2秒）
            try:
                url = f"https://api.qijieya.cn/meting/?type=song&id={song.id}&_t={time.time()}"
                result = await self._request(url)
                if result and isinstance(result, list) and len(result) > 0:
                    data = result[0]
                    u = data.get("url")
                    if u:
                        song.audio_url = u
                        logger.debug(f"meting 补全完成: {song.name}")
                        return
            except Exception as e:
                logger.debug(f"meting 补全失败: {e}")
            # 2. 回落 NodeJS /song/url
            try:
                result = await self._request(
                    url=f"{self.cfg.nodejs_base_url}/song/url?id={song.id}&_t={time.time()}",
                    method="GET",
                )
                if isinstance(result, dict):
                    data = result.get("data")
                    if data:
                        audio_url = data[0].get("url")
                        if audio_url:
                            song.audio_url = audio_url
            except Exception as e:
                logger.warning(f"song/url 回落失败: {e}")

        async def _fetch_cover():
            if song.cover_url:
                return
            try:
                detail = await self._request(
                    url=f"{self.cfg.nodejs_base_url}/song/detail?ids={song.id}&_t={time.time()}",
                    method="GET",
                )
                if isinstance(detail, dict) and detail.get("songs"):
                    info = detail["songs"][0]
                    al = info.get("al", {})
                    if al.get("picUrl"):
                        song.cover_url = al["picUrl"]
            except Exception as e:
                logger.debug(f"song/detail 获取封面失败: {e}")

        await asyncio.gather(_resolve_audio(), _fetch_cover())
        return song
