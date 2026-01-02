
import io
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


class MusicRenderer:
    def __init__(self, config: dict,  font_path: Path):
        self.config = config
        self.font_path = font_path

    def draw_lyrics(
        self,
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
        font = ImageFont.truetype(self.font_path, font_size)

        # 计算总高度
        dummy_img = Image.new("RGB", (image_width, 1))
        draw = ImageDraw.Draw(dummy_img)
        line_heights = [
            draw.textbbox((0, 0), line if line.strip() else "　", font=font)[3]
            for line in cleaned_lines
        ]
        total_height = int(
            sum(line_heights) + line_spacing * (len(cleaned_lines) - 1) + 100
        )

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
            draw.text(
                ((image_width - text_width) / 2, y), text, font=font, fill=text_color
            )
            y += line_height + line_spacing

        # 输出到字节流
        img_bytes = io.BytesIO()
        img.save(img_bytes, format="JPEG")
        img_bytes.seek(0)
        return img_bytes.getvalue()
