"""
Unit tests for src/weather/image.py (ForecastImage).

Draws real images with the real bundled font and icons, then inspects them with Pillow.
"""

from io import BytesIO
from typing import cast

import pytest
from PIL import Image

from core.db.data_types import Units
from weather.data_types import ForecastData, ForecastPoint
from weather.image import ForecastImage

__all__: tuple = ()


def _rgb(image: Image.Image, xy: tuple[int, int]) -> tuple[int, ...]:
    """
    Returns the RGB part of one pixel.

    :param image: Image to read.
    :param xy: Pixel coordinates.
    :return: (R, G, B).
    """
    return cast(tuple[int, ...], image.getpixel(xy))[:3]


def _colors(image: Image.Image) -> set[tuple[int, ...]]:
    """
    Returns every RGB color present in an image.

    :param image: Image to read.
    :return: Set of (R, G, B).
    """
    colors = cast(list[tuple[int, tuple[int, ...]]], image.getcolors(maxcolors=100_000))
    return {color[1][:3] for color in colors}


@pytest.fixture(name="renderer", scope="module")
def renderer_fixture() -> ForecastImage:
    """
    One renderer for the module - loading fonts and icons is the expensive part.

    :return: ForecastImage instance.
    """
    return ForecastImage()


def _forecast(count: int = 8, icon: str = "01d", temp: int = 10, wind: int = 5) -> ForecastData:
    """
    Builds a forecast of identical steps.

    :param count: Number of steps.
    :param icon: Icon code of every step.
    :param temp: Temperature of every step.
    :param wind: Wind speed of every step.
    :return: ForecastData instance.
    """
    return ForecastData(
        points=tuple(ForecastPoint(time=f"{i * 3:02}:00", icon=icon, temp=temp, wind_speed=wind) for i in range(count))
    )


def _open(png: bytes) -> Image.Image:
    """
    Decodes a PNG.

    :param png: PNG bytes.
    :return: Decoded image.
    """
    image: Image.Image = Image.open(BytesIO(png))
    image.load()
    return image


class TestTempColors:
    """Tests ForecastImage.get_temp_colors against the old bot's thresholds."""

    @pytest.mark.parametrize(
        ("temp", "colors"),
        [
            (50, ("#2b0001", "#ffffff")),
            (49, ("#6b1527", "#ffffff")),
            (40, ("#6b1527", "#ffffff")),
            (39, ("#b73466", "#ffffff")),
            (30, ("#b73466", "#ffffff")),
            (29, ("#db6c54", "#ffffff")),
            (25, ("#db6c54", "#ffffff")),
            (24, ("#e09f41", "#000000")),
            (20, ("#e09f41", "#000000")),
            (19, ("#e1ce39", "#000000")),
            (15, ("#e1ce39", "#000000")),
            (14, ("#b8db41", "#000000")),
            (10, ("#b8db41", "#000000")),
            (9, ("#5ac84b", "#000000")),
            (5, ("#5ac84b", "#000000")),
            (4, ("#4db094", "#000000")),
            (0, ("#4db094", "#000000")),
            (-1, ("#4178be", "#ffffff")),
            (-5, ("#4178be", "#ffffff")),
            (-6, ("#5751ac", "#ffffff")),
            (-10, ("#5751ac", "#ffffff")),
            (-11, ("#291e6a", "#ffffff")),
            (-15, ("#291e6a", "#ffffff")),
            (-16, ("#8e108e", "#ffffff")),
            (-20, ("#8e108e", "#ffffff")),
            (-21, ("#f3a5f3", "#000000")),
            (-30, ("#f3a5f3", "#000000")),
            (-31, ("#e3e3e3", "#000000")),
        ],
    )
    def test_boundaries(self, temp: int, colors: tuple[str, str]) -> None:
        """
        Each band's edges get that band's column and text colors.

        :param temp: Temperature in °C.
        :param colors: Expected (column color, text color).
        :return: None
        """
        assert ForecastImage.get_temp_colors(temp_celsius=temp) == colors


class TestWindColors:
    """Tests ForecastImage.get_wind_colors against the old bot's thresholds."""

    @pytest.mark.parametrize(
        ("speed", "colors"),
        [
            (0, ("#5a5673", "#ffffff")),
            (9, ("#5a5673", "#ffffff")),
            (10, ("#5258ab", "#ffffff")),
            (20, ("#4083b8", "#ffffff")),
            (30, ("#4ea98f", "#ffffff")),
            (39, ("#4ea98f", "#ffffff")),
            (40, ("#4abe47", "#000000")),
            (50, ("#8ec94b", "#000000")),
            (60, ("#cad63e", "#000000")),
            (70, ("#d8bf3d", "#000000")),
            (80, ("#d69b44", "#000000")),
            (99, ("#d5784c", "#000000")),
            (100, ("#c7466f", "#ffffff")),
            (110, ("#a3355b", "#ffffff")),
            (120, ("#901c4f", "#ffffff")),
            (139, ("#631a1b", "#ffffff")),
            (140, ("#2b0001", "#ffffff")),
            (-1, ("#5a5673", "#ffffff")),
        ],
    )
    def test_boundaries(self, speed: int, colors: tuple[str, str]) -> None:
        """
        Each band's edges get that band's bar and text colors; a negative speed falls into the lowest band.

        :param speed: Wind speed in m/s.
        :param colors: Expected (bar color, text color).
        :return: None
        """
        assert ForecastImage.get_wind_colors(speed=speed) == colors


class TestDraw:
    """Tests ForecastImage.draw."""

    @pytest.mark.parametrize("units", [Units.METRIC, Units.IMPERIAL])
    def test_returns_png_of_fixed_size(self, renderer: ForecastImage, units: Units) -> None:
        """
        The result is a 799x199 PNG in both unit systems.

        :param renderer: ForecastImage fixture.
        :param units: Measurement units.
        :return: None
        """
        png: bytes = renderer.draw(forecast=_forecast(), units=units)
        image: Image.Image = _open(png=png)
        assert (image.format, image.size) == ("PNG", (799, 199))

    def test_column_colors_follow_temperature_and_units(self, renderer: ForecastImage) -> None:
        """
        68°F is painted like 20°C, and the wind bar like 2 m/s (5 mph).

        :param renderer: ForecastImage fixture.
        :return: None
        """
        image: Image.Image = _open(png=renderer.draw(forecast=_forecast(temp=68, wind=5), units=Units.IMPERIAL))
        assert _rgb(image, (2, 2)) == (0xE0, 0x9F, 0x41)
        assert _rgb(image, (2, 195)) == (0x5A, 0x56, 0x73)
        assert _rgb(image, (99, 2)) == (0x26, 0x26, 0x26)  # Gap between columns

    def test_unknown_icon_and_short_forecast(self, renderer: ForecastImage) -> None:
        """
        An icon code without a file is skipped and fewer than 8 steps leave the rest background.

        :param renderer: ForecastImage fixture.
        :return: None
        """
        image: Image.Image = _open(png=renderer.draw(forecast=_forecast(count=3, icon="99x"), units=Units.METRIC))
        assert image.size == (799, 199)
        assert _rgb(image, (750, 100)) == (0x26, 0x26, 0x26)

    def test_extra_points_are_ignored(self, renderer: ForecastImage) -> None:
        """
        Steps beyond the 8 that fit are not drawn (and don't fail).

        :param renderer: ForecastImage fixture.
        :return: None
        """
        assert _open(png=renderer.draw(forecast=_forecast(count=12), units=Units.METRIC)).size == (799, 199)

    def test_white_icons_on_dark_columns(self, renderer: ForecastImage) -> None:
        """
        On a dark column (white text) the icon is drawn white, on a light one black.

        :param renderer: ForecastImage fixture.
        :return: None
        """
        dark: Image.Image = _open(png=renderer.draw(forecast=_forecast(temp=45), units=Units.METRIC))
        light: Image.Image = _open(png=renderer.draw(forecast=_forecast(temp=10), units=Units.METRIC))
        icon_area: tuple[int, int, int, int] = (17, 50, 82, 115)
        dark_colors: set[tuple[int, ...]] = _colors(dark.crop(icon_area))
        light_colors: set[tuple[int, ...]] = _colors(light.crop(icon_area))
        assert (255, 255, 255) in dark_colors
        assert (0, 0, 0) in light_colors
