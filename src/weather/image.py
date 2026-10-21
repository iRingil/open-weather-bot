"""Draws the weather forecast image."""

from io import BytesIO
from pathlib import Path
from threading import Lock

from PIL import Image, ImageDraw, ImageFont

from core.db.data_types import Units
from weather.data_types import ForecastData

__all__: tuple[str] = ("ForecastImage",)

_ASSETS_DIR: Path = Path(__file__).resolve().parent / "assets"

# (lower bound in °C, column color, text color), checked from the top down
_TEMP_COLORS: tuple[tuple[int, str, str], ...] = (
    (50, "#2b0001", "#ffffff"),
    (40, "#6b1527", "#ffffff"),
    (30, "#b73466", "#ffffff"),
    (25, "#db6c54", "#ffffff"),
    (20, "#e09f41", "#000000"),
    (15, "#e1ce39", "#000000"),
    (10, "#b8db41", "#000000"),
    (5, "#5ac84b", "#000000"),
    (0, "#4db094", "#000000"),
    (-5, "#4178be", "#ffffff"),
    (-10, "#5751ac", "#ffffff"),
    (-15, "#291e6a", "#ffffff"),
    (-20, "#8e108e", "#ffffff"),
    (-30, "#f3a5f3", "#000000"),
)
_TEMP_COLOR_BELOW_ALL: tuple[str, str] = ("#e3e3e3", "#000000")

# (lower bound in m/s, column color, text color), checked from the top down
_WIND_COLORS: tuple[tuple[int, str, str], ...] = (
    (140, "#2b0001", "#ffffff"),
    (130, "#631a1b", "#ffffff"),
    (120, "#901c4f", "#ffffff"),
    (110, "#a3355b", "#ffffff"),
    (100, "#c7466f", "#ffffff"),
    (90, "#d5784c", "#000000"),
    (80, "#d69b44", "#000000"),
    (70, "#d8bf3d", "#000000"),
    (60, "#cad63e", "#000000"),
    (50, "#8ec94b", "#000000"),
    (40, "#4abe47", "#000000"),
    (30, "#4ea98f", "#ffffff"),
    (20, "#4083b8", "#ffffff"),
    (10, "#5258ab", "#ffffff"),
    (0, "#5a5673", "#ffffff"),
)


class ForecastImage:
    """
    Draws the weather forecast image: one column per forecast step with time, icon, temperature
    and a wind speed bar.

    Fonts and icons are loaded once, at construction. draw() is meant to run in a worker thread
    (asyncio.to_thread); a lock keeps concurrent calls from sharing Pillow's font objects at once.

    :cvar _WIDTH: Image width, in pixels.
    :cvar _HEIGHT: Image height, in pixels.
    :cvar _COLUMN_STEP: Horizontal distance between two columns, in pixels.
    :cvar _COLUMN_WIDTH: Width of one column, in pixels.
    :cvar _BACKGROUND: Background color (visible between the columns).
    :cvar _WHITE: Text color that turns the black icons white for contrast.
    """

    _WIDTH: int = 799
    _HEIGHT: int = 199
    _COLUMN_STEP: int = 100
    _COLUMN_WIDTH: int = 99
    _BACKGROUND: str = "#262626"
    _WHITE: str = "#ffffff"

    def __init__(self, assets_dir: Path = _ASSETS_DIR) -> None:
        """
        Loads the fonts and weather icons.

        :param assets_dir: Folder holding font/Rubik-Bold.ttf and ico/*.png.
        """
        font_path: Path = assets_dir / "font" / "Rubik-Bold.ttf"
        self._font_big: ImageFont.FreeTypeFont = ImageFont.truetype(font=font_path, size=24)
        self._font_small: ImageFont.FreeTypeFont = ImageFont.truetype(font=font_path, size=18)
        self._icons: dict[str, Image.Image] = {}
        self._icons_white: dict[str, Image.Image] = {}
        for icon_path in sorted((assets_dir / "ico").glob("*.png")):
            with Image.open(fp=icon_path, formats=("PNG",)) as icon:
                black: Image.Image = icon.convert(mode="RGBA")
            white: Image.Image = Image.new(mode="RGBA", size=black.size, color=self._WHITE)
            white.putalpha(alpha=black.getchannel("A"))
            self._icons[icon_path.stem] = black
            self._icons_white[icon_path.stem] = white
        self._lock: Lock = Lock()

    @staticmethod
    def _to_celsius(temp: int, units: Units) -> int:
        """
        Converts a temperature to °C.

        :param temp: Temperature in the given units.
        :param units: Measurement units of temp.
        :return: Temperature in °C.
        """
        return temp if units == Units.METRIC else round((temp - 32) * 5 / 9)

    @staticmethod
    def _to_meters_per_second(speed: int, units: Units) -> int:
        """
        Converts a wind speed to m/s.

        :param speed: Wind speed in the given units.
        :param units: Measurement units of speed.
        :return: Wind speed in m/s.
        """
        return speed if units == Units.METRIC else round(speed / 2.237)

    @staticmethod
    def get_temp_colors(temp_celsius: int) -> tuple[str, str]:
        """
        Returns the column and text colors for a temperature.

        :param temp_celsius: Temperature, in °C.
        :return: (column color, text color).
        """
        for lower_bound, color, text_color in _TEMP_COLORS:
            if temp_celsius >= lower_bound:
                return color, text_color
        return _TEMP_COLOR_BELOW_ALL

    @staticmethod
    def get_wind_colors(speed: int) -> tuple[str, str]:
        """
        Returns the bar and text colors for a wind speed.

        :param speed: Wind speed, in m/s.
        :return: (bar color, text color).
        """
        for lower_bound, color, text_color in _WIND_COLORS:
            if speed >= lower_bound:
                return color, text_color
        return _WIND_COLORS[-1][1], _WIND_COLORS[-1][2]

    def _draw_centered(
        self, draw: ImageDraw.ImageDraw, pos: tuple[int, int], text: str, font: ImageFont.FreeTypeFont, color: str
    ) -> None:
        """
        Draws text horizontally centered within a column.

        :param draw: Drawing context.
        :param pos: (x of the column's left edge, y of the text's top).
        :param text: Text to draw.
        :param font: Font to draw with.
        :param color: Text color.
        :return: None
        """
        offset: int = round((self._COLUMN_WIDTH - draw.textlength(text=text, font=font)) / 2)
        draw.text(xy=(pos[0] + offset, pos[1]), text=text, font=font, fill=color)

    def draw(self, forecast: ForecastData, units: Units) -> bytes:
        """
        Draws the forecast image.

        :param forecast: Weather forecast.
        :param units: Measurement units of the forecast values.
        :return: The image, PNG-encoded.
        """
        temp_unit: str = "°C" if units == Units.METRIC else "°F"
        wind_unit: str = "m/s" if units == Units.METRIC else "mph"
        with self._lock:
            canvas: Image.Image = Image.new(mode="RGBA", size=(self._WIDTH, self._HEIGHT), color=self._BACKGROUND)
            draw: ImageDraw.ImageDraw = ImageDraw.Draw(im=canvas)
            for idx, point in enumerate(forecast.points[: self._WIDTH // self._COLUMN_STEP + 1]):
                pos_x: int = idx * self._COLUMN_STEP
                # Temperature column: time, icon, temperature
                color, text_color = self.get_temp_colors(temp_celsius=self._to_celsius(temp=point.temp, units=units))
                draw.rectangle(xy=(pos_x, 0, pos_x + self._COLUMN_WIDTH - 1, 163), fill=color)
                self._draw_centered(draw=draw, pos=(pos_x, 15), text=point.time, font=self._font_big, color=text_color)
                icons: dict[str, Image.Image] = self._icons_white if text_color == self._WHITE else self._icons
                icon_image: Image.Image | None = icons.get(point.icon)
                if icon_image is not None:
                    canvas.alpha_composite(im=icon_image, dest=(pos_x + 17, 50))
                self._draw_centered(
                    draw=draw, pos=(pos_x, 126), text=f"{point.temp}{temp_unit}", font=self._font_big, color=text_color
                )
                # Wind speed bar
                speed: int = self._to_meters_per_second(speed=point.wind_speed, units=units)
                color, text_color = self.get_wind_colors(speed=speed)
                draw.rectangle(xy=(pos_x, 165, pos_x + self._COLUMN_WIDTH - 1, 199), fill=color)
                self._draw_centered(
                    draw=draw,
                    pos=(pos_x, 173),
                    text=f"{point.wind_speed} {wind_unit}",
                    font=self._font_small,
                    color=text_color,
                )
            buffer: BytesIO = BytesIO()
            canvas.save(fp=buffer, format="PNG")
            canvas.close()
        return buffer.getvalue()
