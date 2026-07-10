import io
import re

from PIL import Image, ImageDraw, ImageFont

from .config import PluginConfig


class LyricsRenderer:
    def __init__(self, config: PluginConfig):
        self.cfg = config
        self.font_path = config.font_path
        self.font = ImageFont.truetype(self.font_path, 30)

    def draw_lyrics(
        self,
        lyrics: str,
        image_width=1000,
        line_spacing=20,
        top_color=(255, 250, 240),
        bottom_color=(235, 255, 247),
        text_color=(70, 70, 70),
    ) -> bytes:
        """Render lyrics as a JPEG image with a vertical gradient background"""
        lines = lyrics.splitlines()
        cleaned_lines = []
        for line in lines:
            cleaned = re.sub(r"\[\d{2}:\d{2}(?:\.\d{2,3})?\]", "", line)
            cleaned_lines.append(cleaned if cleaned != "" else "")

        dummy_img = Image.new("RGB", (image_width, 1))
        draw = ImageDraw.Draw(dummy_img)
        horizontal_padding = 80
        line_heights = []
        max_line_width = 0
        for line in cleaned_lines:
            text = line if line.strip() else "　"
            bbox = draw.textbbox((0, 0), text, font=self.font)
            line_heights.append(bbox[3])
            max_line_width = max(max_line_width, bbox[2] - bbox[0])

        image_width = int(max(image_width, max_line_width + horizontal_padding * 2))
        total_height = int(
            sum(line_heights) + line_spacing * (len(cleaned_lines) - 1) + 100
        )

        img = Image.new("RGB", (image_width, total_height))
        for y in range(total_height):
            ratio = y / total_height
            r = int(top_color[0] * (1 - ratio) + bottom_color[0] * ratio)
            g = int(top_color[1] * (1 - ratio) + bottom_color[1] * ratio)
            b = int(top_color[2] * (1 - ratio) + bottom_color[2] * ratio)
            for x in range(image_width):
                img.putpixel((x, y), (r, g, b))

        draw = ImageDraw.Draw(img)

        y = 50
        for line, line_height in zip(cleaned_lines, line_heights):
            text = line if line.strip() else "　"
            bbox = draw.textbbox((0, 0), text, font=self.font)
            text_width = bbox[2] - bbox[0]
            draw.text(
                ((image_width - text_width) / 2, y),
                text,
                font=self.font,
                fill=text_color,
            )
            y += line_height + line_spacing

        img_bytes = io.BytesIO()
        img.save(img_bytes, format="JPEG")
        img_bytes.seek(0)
        return img_bytes.getvalue()
