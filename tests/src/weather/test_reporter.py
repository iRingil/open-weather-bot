"""
Unit tests for src/weather/reporter.py (WeatherReporter).

WeatherAPI and ForecastImage are autospecced; captions are rendered by a real TgTemplater over the
project's own templates, in English (msgids are English, so no compiled catalogs are needed).
"""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, create_autospec

import pytest

from core.db.data_types import Units, UserSettings
from core.tg_templater import TgTemplater
from weather.client import WeatherAPI
from weather.data_types import CurrentWeatherData, ForecastData, ForecastPoint
from weather.image import ForecastImage
from weather.reporter import WeatherReport, WeatherReporter

__all__: tuple = ()

_SRC: Path = Path(__file__).resolve().parents[3] / "src"
_FORECAST: ForecastData = ForecastData(points=(ForecastPoint(time="00:00", icon="01d", temp=1, wind_speed=1),))
_CURRENT: CurrentWeatherData = CurrentWeatherData(
    temp=20,
    feels_like=19,
    weather_code=800,
    description="clear <sky>",
    wind_speed=3,
    gust=None,
    humidity=50,
    pressure=1013,
    visibility=None,
    precipitation=None,
    time=datetime(2026, 10, 21, 14, 5, tzinfo=timezone.utc),
    sunrise=datetime(2026, 10, 21, 7, 2, tzinfo=timezone.utc),
    sunset=datetime(2026, 10, 21, 18, 9, tzinfo=timezone.utc),
)
_SETTINGS: UserSettings = UserSettings(
    user_id=1, dialog_id=2, lang="en", city="Kyiv", latitude=50.4, longitude=30.5, units=Units.METRIC
)


@pytest.fixture(name="api")
def api_fixture() -> MagicMock:
    """
    An autospecced WeatherAPI returning a forecast and current weather.

    :return: The mocked WeatherAPI.
    """
    mock: MagicMock = create_autospec(spec=WeatherAPI, instance=True)
    mock.get_forecast = AsyncMock(return_value=_FORECAST)
    mock.get_current_weather = AsyncMock(return_value=_CURRENT)
    return mock


@pytest.fixture(name="image")
def image_fixture() -> MagicMock:
    """
    An autospecced ForecastImage returning fixed bytes.

    :return: The mocked ForecastImage.
    """
    mock: MagicMock = create_autospec(spec=ForecastImage, instance=True)
    mock.draw.return_value = b"png"
    return mock


@pytest.fixture(name="reporter")
def reporter_fixture(api: MagicMock, image: MagicMock) -> WeatherReporter:
    """
    A WeatherReporter over the mocks and a real TgTemplater.

    :param api: The mocked WeatherAPI.
    :param image: The mocked ForecastImage.
    :return: WeatherReporter instance.
    """
    tmpl: TgTemplater = TgTemplater(templates_dir=_SRC / "templates", locale_dir=_SRC / "locales")
    return WeatherReporter(api=api, image=image, tmpl=tmpl)


class TestForecastImage:
    """Tests WeatherReporter.forecast_image."""

    async def test_draws_the_forecast(self, reporter: WeatherReporter, api: MagicMock, image: MagicMock) -> None:
        """
        The forecast is requested for the location and units and drawn.

        :param reporter: WeatherReporter fixture.
        :param api: The mocked WeatherAPI.
        :param image: The mocked ForecastImage.
        :return: None
        """
        assert await reporter.forecast_image(latitude=1, longitude=2, units=Units.IMPERIAL) == b"png"
        api.get_forecast.assert_awaited_once_with(latitude=1, longitude=2, units=Units.IMPERIAL)
        image.draw.assert_called_once_with(forecast=_FORECAST, units=Units.IMPERIAL)

    async def test_no_forecast_no_image(self, reporter: WeatherReporter, api: MagicMock, image: MagicMock) -> None:
        """
        Without a forecast nothing is drawn.

        :param reporter: WeatherReporter fixture.
        :param api: The mocked WeatherAPI.
        :param image: The mocked ForecastImage.
        :return: None
        """
        api.get_forecast.return_value = None
        assert await reporter.forecast_image(latitude=1, longitude=2, units=Units.METRIC) is None
        image.draw.assert_not_called()


class TestCurrentWeather:
    """Tests WeatherReporter.current_weather."""

    async def test_passes_through(self, reporter: WeatherReporter, api: MagicMock) -> None:
        """
        The request is forwarded to the API as is.

        :param reporter: WeatherReporter fixture.
        :param api: The mocked WeatherAPI.
        :return: None
        """
        assert await reporter.current_weather(latitude=1, longitude=2, lang="ru", units=Units.METRIC) == _CURRENT
        api.get_current_weather.assert_awaited_once_with(latitude=1, longitude=2, lang="ru", units=Units.METRIC)


class TestCaption:
    """Tests WeatherReporter.caption."""

    async def test_renders_current_weather(self, reporter: WeatherReporter) -> None:
        """
        The caption shows the city, the escaped description and the values with their units.

        :param reporter: WeatherReporter fixture.
        :return: None
        """
        caption: str = await reporter.caption(current=_CURRENT, city="Kyiv & Co", units=Units.METRIC, lang="en")
        assert caption.startswith("<b>Kyiv &amp; Co, 21 Oct 14:05</b>\n☀ clear &lt;sky&gt;\n")
        assert "🌡 <b>20°C</b>, feels like <b>19°C</b>" in caption
        assert "gusts to" not in caption and "Visibility" not in caption
        assert caption.endswith("🌅 Sunrise: <b>07:02</b>  🌇 Sunset: <b>18:09</b>")

    async def test_failed_template_without_current_weather(self, reporter: WeatherReporter) -> None:
        """
        Without current weather the "failed" caption with the city name is shown.

        :param reporter: WeatherReporter fixture.
        :return: None
        """
        caption: str = await reporter.caption(current=None, city="Kyiv", units=Units.METRIC, lang="en")
        assert caption == "<b>Kyiv</b>\n\n❌ Failed to obtain data about the current weather."

    async def test_caption_is_limited_to_1024_chars(self, api: MagicMock, image: MagicMock) -> None:
        """
        Both templates are rendered with Telegram's photo caption limit.

        :param api: The mocked WeatherAPI.
        :param image: The mocked ForecastImage.
        :return: None
        """
        tmpl: MagicMock = create_autospec(spec=TgTemplater, instance=True)
        tmpl.render = AsyncMock(return_value="x")
        reporter: WeatherReporter = WeatherReporter(api=api, image=image, tmpl=tmpl)
        await reporter.caption(current=None, city="Kyiv", units=Units.METRIC, lang="en")
        await reporter.caption(current=_CURRENT, city="Kyiv", units=Units.METRIC, lang="en")
        assert [call.kwargs["max_len"] for call in tmpl.render.await_args_list] == [1024, 1024]
        assert [call.kwargs["tmpl"] for call in tmpl.render.await_args_list] == [
            "weather/current_weather_failed.jinja2",
            "weather/current_weather.jinja2",
        ]


class TestReport:
    """Tests WeatherReporter.report."""

    async def test_composes_image_and_caption(self, reporter: WeatherReporter, api: MagicMock) -> None:
        """
        The report holds the drawn image and the caption for the user's own settings.

        :param reporter: WeatherReporter fixture.
        :param api: The mocked WeatherAPI.
        :return: None
        """
        report: WeatherReport = await reporter.report(settings=_SETTINGS)
        assert report.photo == b"png"
        assert report.caption.startswith("<b>Kyiv, ")
        api.get_forecast.assert_awaited_once_with(latitude=50.4, longitude=30.5, units=Units.METRIC)
        api.get_current_weather.assert_awaited_once_with(latitude=50.4, longitude=30.5, lang="en", units=Units.METRIC)

    async def test_without_forecast_photo_is_none(self, reporter: WeatherReporter, api: MagicMock) -> None:
        """
        A failed forecast leaves the photo empty while the caption is still built.

        :param reporter: WeatherReporter fixture.
        :param api: The mocked WeatherAPI.
        :return: None
        """
        api.get_forecast.return_value = None
        report: WeatherReport = await reporter.report(settings=_SETTINGS)
        assert report.photo is None and report.caption
