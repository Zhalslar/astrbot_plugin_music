import uuid
from pathlib import Path

import aiofiles
import aiohttp

from astrbot.api import logger

from .config import PluginConfig


class Downloader:
    """下载器"""

    def __init__(self, config: PluginConfig):
        self.cfg = config
        self.songs_dir = self.cfg.songs_dir
        self.session = aiohttp.ClientSession(proxy=self.cfg.http_proxy)

    async def close(self):
        await self.session.close()

    async def download_image(self, url: str, close_ssl: bool = True) -> bytes | None:
        """下载图片"""
        url = url.replace("https://", "http://") if close_ssl else url
        try:
            async with self.session.get(url) as response:
                img_bytes = await response.read()
                return img_bytes
        except Exception as e:
            logger.error(f"图片下载失败: {e}")

    async def download_song(self, url: str) -> Path | None:
        """下载歌曲，返回保存路径"""
        self.songs_dir.mkdir(parents=True, exist_ok=True)
        song_uuid = uuid.uuid4().hex
        file_path = self.songs_dir / f"{song_uuid}.mp3"
        try:
            async with self.session.get(url) as response:
                if response.status != 200:
                    logger.error(f"歌曲下载失败，HTTP 状态码：{response.status}")
                    return None
                # 流式写入
                async with aiofiles.open(file_path, "wb") as f:
                    async for chunk in response.content.iter_chunked(1024):
                        await f.write(chunk)

            logger.debug(f"歌曲下载完成，保存在：{file_path}")
            return file_path

        except Exception as e:
            logger.error(f"歌曲下载失败，错误信息：{e}")
            return None
