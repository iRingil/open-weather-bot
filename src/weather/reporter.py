"""Builds the weather report a user sees: the forecast image and the current weather caption."""

from asyncio import to_thread
from typing import NamedTuple

from core.db.data_types import Units, UserSettings
from core.tg_templater import TgTemplater
from weather.client import WeatherAPI
from weather.data_types import CurrentWeatherData, ForecastData
from weather.formatter import WeatherFormatter
from weather.image import ForecastImage

__all__: tuple[str, ...] = ("WeatherReport", "WeatherReporter")


class WeatherReport(NamedTuple):
    """
    A ready-to-send weather report.

    :param photo: PNG forecast image, or None if the forecast couldn't be obtained.
    :param caption: Current weather caption (HTML).
    """

    photo: bytes | None
    caption: str


class WeatherReporter:
    """
    Builds weather reports.

    The forecast image depends only on the location and units, and the current weather only on the
    location, units and language - so these are separate steps a caller can share between users,
    while the caption (which also shows each user's own city name) is rendered per user.

    :cvar _tmpl_current_weather: Path to the current weather caption template.
    :cvar _tmpl_current_weather_failed: Path to the "current weather unavailable" caption template.
    :cvar _CAPTION_MAX_LEN: Telegram's limit on a photo caption length.
    """

    _tmpl_current_weather: str = "weather/current_weather.jinja2"
    _tmpl_current_weather_failed: str = "weather/current_weather_failed.jinja2"
    _CAPTION_MAX_LEN: int = 1024

    def __init__(self, api: WeatherAPI, image: ForecastImage, tmpl: TgTemplater) -> None:
        """
        Initializes the reporter.

        :param api: OpenWeatherMap API client.
        :param image: Forecast image renderer.
        :param tmpl: Template renderer.
        """
        self._api: WeatherAPI = api
        self._image: ForecastImage = image
        self._tmpl: TgTemplater = tmpl
        self._formatter: WeatherFormatter = WeatherFormatter()

    async def forecast_image(self, latitude: float, longitude: float, units: Units) -> bytes | None:
        """
        Gets the forecast and draws it.

        :param latitude: Latitude.
        :param longitude: Longitude.
        :param units: Measurement units.
        :return: PNG forecast image, or None if the forecast couldn't be obtained.
        """
        forecast: ForecastData | None = await self._api.get_forecast(
            latitude=latitude, longitude=longitude, units=units
        )
        if forecast is None:
            return None
        return await to_thread(self._image.draw, forecast=forecast, units=units)

    async def current_weather(
        self, latitude: float, longitude: float, lang: str, units: Units
    ) -> CurrentWeatherData | None:
        """
        Gets the current weather.

        :param latitude: Latitude.
        :param longitude: Longitude.
        :param lang: ISO 639-1 language code of the weather description.
        :param units: Measurement units.
        :return: Current weather, or None if it couldn't be obtained.
        """
        return await self._api.get_current_weather(latitude=latitude, longitude=longitude, lang=lang, units=units)

    async def caption(self, current: CurrentWeatherData | None, city: str, units: Units, lang: str) -> str:
        """
        Renders the current weather caption.

        :param current: Current weather, or None if it couldn't be obtained.
        :param city: City name to show.
        :param units: Measurement units of current.
        :param lang: ISO 639-1 user language code.
        :return: Caption (HTML).
        """
        if current is None:
            return await self._tmpl.render(
                tmpl=self._tmpl_current_weather_failed,
                locale=lang,
                data={"city": city},
                max_len=self._CAPTION_MAX_LEN,
            )
        return await self._tmpl.render(
            tmpl=self._tmpl_current_weather,
            locale=lang,
            data=self._formatter.build_context(data=current, units=units, city=city, lang=lang),
            max_len=self._CAPTION_MAX_LEN,
        )

    async def report(self, settings: UserSettings) -> WeatherReport:
        """
        Builds the full weather report for one user.

        :param settings: The user's weather settings.
        :return: Weather report.
        """
        photo: bytes | None = await self.forecast_image(
            latitude=settings.latitude, longitude=settings.longitude, units=settings.units
        )
        current: CurrentWeatherData | None = await self.current_weather(
            latitude=settings.latitude, longitude=settings.longitude, lang=settings.lang, units=settings.units
        )
        caption: str = await self.caption(current=current, city=settings.city, units=settings.units, lang=settings.lang)
        return WeatherReport(photo=photo, caption=caption)
