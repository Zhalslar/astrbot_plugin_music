import io
from pathlib import Path
import re
from PIL import Image, ImageDraw, ImageFont
import asyncio
import aiohttp
import aiofiles
from io import BytesIO
from bs4 import BeautifulSoup
import hashlib
from astrbot import logger
from .api import NetEaseMusicAPI


font_path = Path("data/plugins/astrbot_plugin_music/simhei.ttf")

def draw_lyrics(
    lyrics: str,
    image_width=1000,
    font_size=30,
    line_spacing=20,
    top_color=(255, 250, 240),  # 暖白色
    bottom_color=(235, 255, 247),
    text_color=(70, 70, 70),
) -> bytes:
    """
    渲染歌词为图片，背景为竖向渐变色，返回 JPEG 字节流。
    """
    # 清除时间戳但保留空白行
    lines = lyrics.splitlines()
    cleaned_lines = []
    for line in lines:
        cleaned = re.sub(r"\[\d{2}:\d{2}(?:\.\d{2,3})?\]", "", line)
        cleaned_lines.append(cleaned if cleaned != "" else "")

    # 加载字体
    font = ImageFont.truetype(font_path, font_size)

    # 计算总高度
    dummy_img = Image.new("RGB", (image_width, 1))
    draw = ImageDraw.Draw(dummy_img)
    line_heights = [
        draw.textbbox((0, 0), line if line.strip() else "　", font=font)[3]
        for line in cleaned_lines
    ]
    total_height = sum(line_heights) + line_spacing * (len(cleaned_lines) - 1) + 100

    # 创建渐变背景图像
    img = Image.new("RGB", (image_width, total_height))
    for y in range(total_height):
        ratio = y / total_height
        r = int(top_color[0] * (1 - ratio) + bottom_color[0] * ratio)
        g = int(top_color[1] * (1 - ratio) + bottom_color[1] * ratio)
        b = int(top_color[2] * (1 - ratio) + bottom_color[2] * ratio)
        for x in range(image_width):
            img.putpixel((x, y), (r, g, b))

    draw = ImageDraw.Draw(img)

    # 绘制歌词文本（居中）
    y = 50
    for line, line_height in zip(cleaned_lines, line_heights):
        text = line if line.strip() else "　"  # 全角空格占位
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        draw.text(((image_width - text_width) / 2, y), text, font=font, fill=text_color)
        y += line_height + line_spacing

    # 输出到字节流
    img_bytes = io.BytesIO()
    img.save(img_bytes, format="JPEG")
    img_bytes.seek(0)
    return img_bytes.getvalue()



class MusicCardRenderer:
    def __init__(
        self,
        font_path: Path,
        cache_dir: Path = Path("image_cache"),
        card_width: int = 300,
        card_height: int = 250,
        thumb_height: int = 168,
        margin: int = 16,
        corner_radius: int = 10,
        max_concurrency: int = 10,
    ):
        self.font_path = font_path
        self.cache_dir = cache_dir
        self.card_width = card_width
        self.card_height = card_height
        self.thumb_height = thumb_height
        self.margin = margin
        self.corner_radius = corner_radius
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_path(self, url: str) -> Path:
        # 生成唯一文件名
        name = hashlib.md5(url.encode()).hexdigest() + ".jpg"
        return self.cache_dir / name

    async def download_image(
        self, url: str, session: aiohttp.ClientSession
    ) -> Image.Image:
        cache_path = self._get_cache_path(url)
        if cache_path.exists():
            return Image.open(cache_path).convert("RGB")

        async with self.semaphore:
            async with session.get(url) as resp:
                if resp.status == 200:
                    img_bytes = await resp.read()
                    async with aiofiles.open(cache_path, "wb") as f:
                        await f.write(img_bytes)
                    return Image.open(BytesIO(img_bytes)).convert("RGB")
                raise ValueError(f"下载失败: {url}")

    def format_count(self, count: int) -> str:
        if count >= 10000:
            return f"{count / 10000:.1f}万"
        elif count >= 1000:
            return f"{count / 1000:.1f}千"
        return str(count)

    async def draw_card(
        self,
        video: dict,
        font: ImageFont.FreeTypeFont,
        session: aiohttp.ClientSession,
        index: int,
    ) -> Image.Image:
        try:
            card = Image.new("RGBA", (self.card_width, self.card_height), "#ffffff")
            draw = ImageDraw.Draw(card)

            # 封面
            raw_url = video.get("pic", "")
            pic_url = raw_url if raw_url.startswith("http") else ("https:" + raw_url)
            thumb = await self.download_image(pic_url, session)
            thumb = thumb.resize((self.card_width, self.thumb_height))
            card.paste(thumb, (0, 0))

            # 渐变黑图层
            gradient_height = 40
            alpha_gradient = Image.new("L", (self.card_width, gradient_height), color=0)
            for y in range(gradient_height):
                alpha = int(180 * (y / gradient_height))
                ImageDraw.Draw(alpha_gradient).line(
                    [(0, y), (self.card_width, y)], fill=alpha
                )
            overlay = Image.new(
                "RGBA", (self.card_width, gradient_height), color=(0, 0, 0, 255)
            )
            overlay.putalpha(alpha_gradient)
            card.paste(overlay, (0, self.thumb_height - 40), overlay)

            # 播放量
            draw.text(
                (8, self.thumb_height - 20),
                f"{self.format_count(video['play'])}",
                font=font,
                fill="#ffffff",
            )

            # 时长
            draw.text(
                (self.card_width - 40, self.thumb_height - 20),
                f"{video['duration']}",
                font=font,
                fill="#ffffff",
            )

            # 标题
            raw_title = BeautifulSoup(video["title"], "html.parser").get_text()
            title = (
                raw_title[:18] + "\n" + raw_title[18:36] + "..."
                if len(raw_title) > 36
                else raw_title[:18] + "\n" + raw_title[18:]
            )
            draw.text((8, self.thumb_height + 8), title, font=font, fill="#000000")

            # 作者
            draw.text(
                (8, self.thumb_height + 60),
                f"UP {video['author']}",
                font=font,
                fill="#666666",
            )

            # 序号
            draw.text(
                (
                    self.card_width - 30,
                    self.card_height - 20,
                ),
                str(index),
                font=font,
                fill="#666666",
            )

            # 创建圆角遮罩
            mask = Image.new("L", (self.card_width, self.card_height), 0)
            draw_mask = ImageDraw.Draw(mask)
            draw_mask.rounded_rectangle(
                (0, 0, self.card_width, self.card_height),
                radius=self.corner_radius,
                fill=255,
            )
            # 应用圆角遮罩
            card.putalpha(mask)

            return card
        except Exception as e:
            logger.error(f"[错误] 渲染卡片失败: {e}")
            # 返回空白卡片以避免中断整个流程
            return Image.new("RGBA", (self.card_width, self.card_height), "#ffffff")

    async def render_video_list_image(
        self, video_list: list, cards_per_row: int = 3, quality: int = 70
    ) -> bytes:
        font = ImageFont.truetype(self.font_path, 16)

        async with aiohttp.ClientSession() as session:
            tasks = [
                self.draw_card(video, font, session, index=i + 1)
                for i, video in enumerate(video_list)
            ]
            cards = await asyncio.gather(*tasks)

        # 拼接每一行（分层）
        rows = []
        for i in range(0, len(cards), cards_per_row):
            row_cards = cards[i : i + cards_per_row]
            row_width = (
                cards_per_row * self.card_width + (cards_per_row + 1) * self.margin
            )
            row_img = Image.new(
                "RGBA",
                (row_width, self.card_height + 2 * self.margin),
                color="#f5f5f5",
            )
            for j, card in enumerate(row_cards):
                x = self.margin + j * (self.card_width + self.margin)
                row_img.paste(card, (x, self.margin), card)
            rows.append(row_img)

        # 最终拼接所有行
        total_width = rows[0].width
        total_height = sum(r.height for r in rows)
        canvas = Image.new(
            "RGBA",
            (total_width, total_height),
            color="#f5f5f5",
        )

        y_offset = 0
        for row in rows:
            canvas.paste(row, (0, y_offset), row)
            y_offset += row.height

        # 异步保存 JPEG，降画质
        final_image = Image.new("RGB", canvas.size, "#f5f5f5")
        final_image.paste(canvas, mask=canvas.split()[3])

        buffer = BytesIO()
        final_image.save(buffer, format="JPEG", quality=quality)
        return buffer.getvalue()
