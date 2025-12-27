"""Module for getting weather information."""

from pathlib import Path

from aiogram.types import Location
from aiohttp import ClientSession

from tgbot.config import load_config, BOT_LOGO
from tgbot.middlewares.localization import i18n
from tgbot.misc.logger import logger
from tgbot.services.database import database
from tgbot.services.classes import CityData, CurrentWeatherData, ForecastData, UserWeatherSettings
from tgbot.services.formatter import FormatWeather
from tgbot.services.image import DrawWeatherImage
from tgbot.services.parser import ParseWeather

__all__: tuple[str, ...] = ("WeatherAPI", "weather")

_ = i18n.gettext  # Alias for gettext method


class WeatherAPI:
    """A class for working with the OpenWeatherMap API."""

    _GEOCODING_API_URL: str = "https://api.openweathermap.org/geo/1.0"
    _CURRENT_WEATHER_API_URL: str = "https://api.openweathermap.org/data/2.5/weather"
    _WEATHER_FORECAST_API_URL: str = "https://api.openweathermap.org/data/2.5/forecast"

    def __init__(self, token: str) -> None:
        """
        Gets OpenWeatherAPI token.

        :param token: OpenWeatherAPI token.
        """
        self._api_key: str = token
        self._formatter: FormatWeather = FormatWeather()
        self._parser: ParseWeather = ParseWeather()
        self._image: DrawWeatherImage = DrawWeatherImage()

    @staticmethod
    async def _get_response_from_api(api_url: str) -> list | dict | None:
        """
        Returns response from OpenWeatherMAp API.

        :param api_url: API url.
        :return: Raw API response or None in case of error.
        """
        async with ClientSession() as session:
            async with session.get(url=api_url) as response:
                await database.increase_api_counter()
                if response.status == 200:
                    result: list | dict = await response.json()
                    return result
                error: dict = await response.json()
                logger.error("Error when requesting WeatherGeocodeAPI: %s", error.get("message"))
                return None

    async def get_list_cities(self, city_name_or_location: str | Location, lang_code: str) -> list[CityData] | None:
        """
        Gets the list of cities from the OpenWeatherMap service and outputs them in formatted form.

        :param city_name_or_location: City name (string) or Location object.
        :param lang_code: ISO 639-1 user language code.
        :return: list of CityData objects or None.
        """
        if isinstance(city_name_or_location, Location):
            api_url: str = (
                f"{self._GEOCODING_API_URL}/reverse"
                f"?lat={city_name_or_location.latitude}&lon={city_name_or_location.longitude}"
                f"&limit=5&appid={self._api_key}"
            )
        else:
            api_url = (
                f"{self._GEOCODING_API_URL}/direct"
                f"?q={await self._formatter.correct_user_input(raw_city_name=city_name_or_location)}"
                f"&limit=5&appid={self._api_key}"
            )
        raw_city_data: list | dict | None = await self._get_response_from_api(api_url=api_url)
        if isinstance(raw_city_data, list):
            city_list: list[CityData] = []
            for raw_city in raw_city_data:
                city: CityData | None = await self._parser.parse_city_data(raw_data=raw_city, lang_code=lang_code)
                if city:
                    city_list.append(city)
            return city_list
        return None

    async def get_current_weather(self, user_id: int) -> str:
        """
        Gets current weather data from the OpenWeatherMap service and outputs them in formatted form.

        :param user_id: Telegram user ID.
        :return: Formatted string with a description of the current weather or an error message.
        """
        user_settings: UserWeatherSettings = await database.get_user_settings(user_id=user_id)
        api_url: str = (
            f"{self._CURRENT_WEATHER_API_URL}"
            f"?lat={user_settings.latitude}"
            f"&lon={user_settings.longitude}"
            f"&lang={user_settings.lang}"
            f"&units={user_settings.units}"
            f"&appid={self._api_key}"
        )
        raw_data: list | dict | None = await self._get_response_from_api(api_url=api_url)
        if isinstance(raw_data, dict):
            weather_data: CurrentWeatherData | None = await self._parser.parse_current_weather(raw_data=raw_data)
            if weather_data:
                current_weather: str = await self._formatter.format_current_weather(
                    weather_data=weather_data,
                    units=user_settings.units,
                    city=user_settings.city,
                    lang_code=user_settings.lang,
                )
                return current_weather
        current_weather = "❌ " + _("Failed to obtain data about the current weather.", locale=user_settings.lang)
        return current_weather

    async def get_weather_forecast(self, user_id: int) -> Path:
        """
        Returns the weather forecast data in the desired form.

        :param user_id: Telegram user ID.
        :return: Path to the generated weather forecast image or bot logo in case of error.
        """
        user_settings: UserWeatherSettings = await database.get_user_settings(user_id=user_id)
        api_url: str = (
            f"{self._WEATHER_FORECAST_API_URL}"
            f"?lat={user_settings.latitude}"
            f"&lon={user_settings.longitude}"
            f"&lang={user_settings.lang}"
            f"&units={user_settings.units}"
            "&cnt=8"
            f"&appid={self._api_key}"
        )
        raw_data: list | dict | None = await self._get_response_from_api(api_url=api_url)
        if isinstance(raw_data, dict):
            weather_forecast_data: ForecastData | None = await self._parser.parse_weather_forecast(
                raw_data=raw_data, units=user_settings.units
            )
            if weather_forecast_data:
                forecast_image: Path = self._image.draw_image(data=weather_forecast_data, user_id=user_id)
                return forecast_image
        forecast_image = BOT_LOGO
        return forecast_image


weather: WeatherAPI = WeatherAPI(token=load_config().weather_api.token)
