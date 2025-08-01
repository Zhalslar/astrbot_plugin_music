from pathlib import Path
import aiofiles
import aiohttp
from astrbot import logger

SAVED_SONGS_DIR = Path("data", "plugin_data", "astrbot_plugin_music", "songs")
SAVED_SONGS_DIR.mkdir(parents=True, exist_ok=True)

async def download_image(url: str) -> bytes | None:
    """下载图片"""
    url = url.replace("https://", "http://")
    try:
        async with aiohttp.ClientSession() as client:
            response = await client.get(url)
            img_bytes = await response.read()
            return img_bytes
    except Exception as e:
        logger.error(f"图片下载失败: {e}")

async def download_song(self, url: str, title: str) -> str | None:
    """下载歌曲"""
    file_path = str(SAVED_SONGS_DIR / f"{title}")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
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

def format_time(duration_ms):
    """格式化歌曲时长"""
    duration = duration_ms // 1000

    hours = duration // 3600
    minutes = (duration % 3600) // 60
    seconds = duration % 60

    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes:02d}:{seconds:02d}"
