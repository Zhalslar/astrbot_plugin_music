from pathlib import Path

import aiofiles
import aiohttp

from astrbot.api import logger


class Downloader:
    """下载器"""

    def __init__(self, data_dir: Path):
        self.song_dir = data_dir / "songs"
        self.song_dir.mkdir(parents=True, exist_ok=True)
        self.session = aiohttp.ClientSession()

    async def close(self):
        await self.session.close()

    async def download_image(self, url: str, close_ssl: bool = True) -> bytes | None:
        """下载图片"""
        url = url.replace("https://", "http://") if close_ssl else url
        try:
            response = await self.session.get(url)
            img_bytes = await response.read()
            return img_bytes
        except Exception as e:
            logger.error(f"图片下载失败: {e}")

    async def download_song(self, url: str, title: str) -> str | None:
        """下载歌曲"""
        file_path = str(self.song_dir / f"{title}")
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    async with aiofiles.open(file_path, "wb") as f:
                        # 流式写入文件
                        while True:
                            chunk = await response.content.read(1024)
                            if not chunk:
                                break
                            await f.write(chunk)
                    logger.info(f"歌曲 {title} 下载完成，保存到 {file_path}")
                    return file_path
                else:
                    logger.error(f"歌曲下载失败，HTTP 状态码：{response.status}")
        except Exception as e:
            logger.error(f"歌曲下载失败，错误信息：{e}")
