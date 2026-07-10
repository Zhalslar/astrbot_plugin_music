import io
import re

from PIL import Image, ImageDraw, ImageFont

from .config import PluginConfig


class LyricsTheme:
    image_width: int = 1000
    font_size: int = 30
    line_spacing: int = 20
    horizontal_padding: int = 80
    vertical_padding: int = 50
    top_color: tuple[int, int, int] = (255, 250, 240)
    bottom_color: tuple[int, int, int] = (235, 255, 247)
    text_color: tuple[int, int, int] = (70, 70, 70)

    def load_font(self, font_path: str) -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(font_path, self.font_size)


class LyricsRenderer:
    def __init__(
        self,
        config: PluginConfig,
        theme: LyricsTheme | None = None,
    ):
        self.cfg = config
        self.theme = theme or LyricsTheme()
        self.font_path = config.font_path
        self.font = self.theme.load_font(str(self.font_path))

    def draw_lyrics(
        self,
        lyrics: str,
        image_width: int | None = None,
        line_spacing: int | None = None,
        top_color: tuple[int, int, int] | None = None,
        bottom_color: tuple[int, int, int] | None = None,
        text_color: tuple[int, int, int] | None = None,
    ) -> bytes:
        theme = self.theme
        image_width = image_width if image_width is not None else theme.image_width
        line_spacing = line_spacing if line_spacing is not None else theme.line_spacing
        top_color = top_color or theme.top_color
        bottom_color = bottom_color or theme.bottom_color
        text_color = text_color or theme.text_color

        lines = lyrics.splitlines()
        cleaned_lines = []
        for line in lines:
            cleaned = re.sub(r"\[\d{2}:\d{2}(?:\.\d{2,3})?\]", "", line)
            cleaned_lines.append(cleaned if cleaned != "" else "")

        dummy_img = Image.new("RGB", (image_width, 1))
        draw = ImageDraw.Draw(dummy_img)
        line_heights = []
        max_line_width = 0
        for line in cleaned_lines:
            text = line if line.strip() else "　"
            bbox = draw.textbbox((0, 0), text, font=self.font)
            line_heights.append(bbox[3])
            max_line_width = max(max_line_width, bbox[2] - bbox[0])

        image_width = int(
            max(image_width, max_line_width + theme.horizontal_padding * 2)
        )
        total_height = int(
            sum(line_heights)
            + line_spacing * (len(cleaned_lines) - 1)
            + theme.vertical_padding * 2
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

        y = theme.vertical_padding
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
