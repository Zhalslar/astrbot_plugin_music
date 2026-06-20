import asyncio
from io import BytesIO

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont

from astrbot import logger

from .config import PluginConfig
from .model import Song


class CardTheme:
    card_width: int = 220
    card_height: int = 278
    thumb_height: int = 220
    margin: int = 16
    corner_radius: int = 10
    font_size: int = 16
    card_bg: str = "#ffffff"
    canvas_bg: str = "#f5f5f5"
    title_color: str = "#000000"
    sub_text_color: str = "#666666"
    overlay_text_color: str = "#ffffff"
    gradient_height: int = 40
    gradient_max_alpha: int = 180

    def load_font(self, font_path: str) -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(font_path, self.font_size)


class CardRenderer:
    def __init__(
        self,
        config: PluginConfig,
        theme: CardTheme | None = None,
    ):
        self.cfg = config
        self.theme = theme or CardTheme()
        self.font = self.theme.load_font(str(self.cfg.font_path))

    def format_count(self, count: int) -> str:
        if count >= 10000:
            return f"{count / 10000:.1f}万"
        if count >= 1000:
            return f"{count / 1000:.1f}k"
        return str(count)

    async def draw_card(
        self,
        media: dict,
        index: int,
        cover_map: dict[str, Image.Image],
    ) -> Image.Image:
        try:
            theme = self.theme
            font = self.font

            card = Image.new(
                "RGBA",
                (theme.card_width, theme.card_height),
                theme.card_bg,
            )
            draw = ImageDraw.Draw(card)

            raw_url = str(media.get("cover") or media.get("pic") or "")

            pic_url = raw_url
            thumb = cover_map.get(pic_url) or Image.new(
                "RGB",
                (theme.card_width, theme.thumb_height),
                "#e5e5e5",
            )
            thumb = thumb.resize((theme.card_width, theme.thumb_height))
            card.paste(thumb, (0, 0))

            alpha_gradient = Image.new(
                "L",
                (theme.card_width, theme.gradient_height),
                color=0,
            )
            gradient_draw = ImageDraw.Draw(alpha_gradient)
            for y in range(theme.gradient_height):
                alpha = int(theme.gradient_max_alpha * (y / theme.gradient_height))
                gradient_draw.line([(0, y), (theme.card_width, y)], fill=alpha)

            overlay = Image.new(
                "RGBA",
                (theme.card_width, theme.gradient_height),
                color=(0, 0, 0, 255),
            )
            overlay.putalpha(alpha_gradient)
            card.paste(
                overlay,
                (0, theme.thumb_height - theme.gradient_height),
                overlay,
            )

            draw.text(
                (8, theme.thumb_height - 20),
                self.format_count(int(media.get("play", 0) or 0)),
                font=font,
                fill=theme.overlay_text_color,
            )
            draw.text(
                (theme.card_width - 40, theme.thumb_height - 20),
                str(media.get("duration") or "0:00"),
                font=font,
                fill=theme.overlay_text_color,
            )

            raw_title = BeautifulSoup(
                str(media.get("title") or ""),
                "html.parser",
            ).get_text()
            title = (
                raw_title[:18] + "\n" + raw_title[18:36] + "..."
                if len(raw_title) > 36
                else raw_title[:18] + "\n" + raw_title[18:]
            )
            draw.text(
                (8, theme.thumb_height + 8),
                title,
                font=font,
                fill=theme.title_color,
            )

            draw.text(
                (8, theme.card_height - 30),
                self._build_author_text(media),
                font=font,
                fill=theme.sub_text_color,
            )

            draw.text(
                (theme.card_width - 20, theme.card_height - 25),
                str(index),
                font=font,
                fill=theme.sub_text_color,
            )

            mask = Image.new("L", (theme.card_width, theme.card_height), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.rounded_rectangle(
                (0, 0, theme.card_width, theme.card_height),
                radius=theme.corner_radius,
                fill=255,
            )
            card.putalpha(mask)
            return card

        except Exception as exc:
            logger.error(f"render card failed: {exc}")
            return Image.new(
                "RGBA",
                (self.theme.card_width, self.theme.card_height),
                self.theme.card_bg,
            )

    async def render_list_image(
        self,
        video_list: list,
        cover_map: dict[str, Image.Image],
        jpeg_quality: int = 80,
    ) -> bytes:
        theme = self.theme
        tasks = [
            self.draw_card(video, index=i + 1, cover_map=cover_map)
            for i, video in enumerate(video_list)
        ]
        cards = await asyncio.gather(*tasks)

        rows: list[Image.Image] = []
        per_row = self.cfg.cards_per_row
        for i in range(0, len(cards), per_row):
            row_cards = cards[i : i + per_row]
            row_width = per_row * theme.card_width + (per_row + 1) * theme.margin
            row_img = Image.new(
                "RGBA",
                (row_width, theme.card_height + 2 * theme.margin),
                theme.canvas_bg,
            )
            for j, card in enumerate(row_cards):
                x = theme.margin + j * (theme.card_width + theme.margin)
                row_img.paste(card, (x, theme.margin), card)
            rows.append(row_img)

        total_width = rows[0].width
        total_height = sum(row.height for row in rows)

        canvas = Image.new(
            "RGBA",
            (total_width, total_height),
            theme.canvas_bg,
        )

        y_offset = 0
        for row in rows:
            canvas.paste(row, (0, y_offset), row)
            y_offset += row.height

        final_image = Image.new("RGB", canvas.size, theme.canvas_bg)
        final_image.paste(canvas, mask=canvas.split()[3])

        buffer = BytesIO()
        final_image.save(buffer, format="JPEG", quality=jpeg_quality)
        return buffer.getvalue()

    async def render_song_list_image(
        self,
        songs: list[Song],
        cover_map: dict[str, Image.Image],
        jpeg_quality: int = 80,
    ) -> bytes:
        song_list = [
            {
                "cover": song.cover_url,
                "title": song.name,
                "author": song.artists,
                "duration": self._format_duration(song.duration),
                "play": 0,
            }
            for song in songs
        ]
        return await self.render_list_image(
            song_list, cover_map, jpeg_quality=jpeg_quality
        )

    @staticmethod
    def _build_author_text(video: dict) -> str:
        return str(video.get("author") or "").strip() or "-"

    @staticmethod
    def _format_duration(duration_ms: int | None) -> str:
        if not duration_ms:
            return "0:00"
        duration = duration_ms // 1000
        minutes = duration // 60
        seconds = duration % 60
        return f"{minutes}:{seconds:02d}"
