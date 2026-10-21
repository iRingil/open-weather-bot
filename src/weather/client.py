"""Client for the OpenWeatherMap geocoding, current weather and forecast APIs."""

from asyncio import Lock, TimeoutError as AsyncTimeoutError, sleep
from time import monotonic
from typing import Any

from aiohttp import ClientError
from loguru import logger
from pydantic import SecretStr

from core.db.data_types import Units
from core.db.repository import Database
from core.http_client import HttpClient, HttpClientError
from weather.data_types import CityData, CurrentWeatherData, ForecastData
from weather.parser import WeatherParser

__all__: tuple[str] = ("WeatherAPI",)


class WeatherAPI:
    """
    Client for the OpenWeatherMap APIs.

    Every request is counted in the database (the admin statistics show the monthly usage) and
    spaced at least _MIN_REQUEST_INTERVAL apart: at most 55 calls per minute, a margin below the free
    plan's limit of 60 however many users a scheduled update covers.

    :cvar _GEOCODING_API_URL: Base URL of the geocoding API.
    :cvar _CURRENT_WEATHER_API_URL: URL of the current weather API.
    :cvar _FORECAST_API_URL: URL of the 5 day / 3 hour forecast API.
    :cvar _MIN_REQUEST_INTERVAL: Minimum time between two requests, in seconds.
    :cvar _CITIES_LIMIT: Maximum number of cities returned by a city search.
    :cvar _FORECAST_STEPS: Number of 3-hour forecast steps requested (8 = 24 hours).
    :cvar _MAX_CITY_NAME_LENGTH: Maximum city name length accepted from the user.
    """

    _GEOCODING_API_URL: str = "https://api.openweathermap.org/geo/1.0"
    _CURRENT_WEATHER_API_URL: str = "https://api.openweathermap.org/data/2.5/weather"
    _FORECAST_API_URL: str = "https://api.openweathermap.org/data/2.5/forecast"
    _MIN_REQUEST_INTERVAL: float = 60 / 55
    _CITIES_LIMIT: int = 5
    _FORECAST_STEPS: int = 8
    _MAX_CITY_NAME_LENGTH: int = 72

    def __init__(self, http_client: HttpClient, token: SecretStr, db: Database) -> None:
        """
        Initializes the client.

        :param http_client: Shared HTTP client.
        :param token: OpenWeatherMap API key.
        :param db: Database, to count the requests made.
        """
        self._http: HttpClient = http_client
        self._token: SecretStr = token
        self._db: Database = db
        self._parser: WeatherParser = WeatherParser()
        self._lock: Lock = Lock()
        self._last_request: float = 0.0

    @classmethod
    def normalize_city_name(cls, raw_city_name: str) -> str:
        """
        Keeps only letters, hyphens and single spaces of a city name typed by the user.

        :param raw_city_name: City name as typed by the user.
        :return: Normalized city name.
        """
        processed: str = ""
        for char in raw_city_name[: cls._MAX_CITY_NAME_LENGTH]:
            if char.isalpha() or char == "-":
                processed += char
            elif char.isspace() and processed and not processed[-1].isspace():
                processed += " "
        return processed.strip()

    async def _wait_for_slot(self) -> None:
        """
        Sleeps until at least _MIN_REQUEST_INTERVAL has passed since the previous request.

        Must be called with self._lock held.

        :return: None
        """
        delay: float = self._last_request + self._MIN_REQUEST_INTERVAL - monotonic()
        if delay > 0:
            await sleep(delay)
        self._last_request = monotonic()

    async def _request(self, url: str, params: dict[str, Any]) -> Any:
        """
        Makes one rate-limited, counted request to the OpenWeatherMap API.

        :param url: API URL.
        :param params: Query parameters, without the API key.
        :return: Parsed JSON response, or None if the request failed.
        """
        async with self._lock:
            await self._wait_for_slot()
        try:
            return await self._http.get(url=url, params={**params, "appid": self._token.get_secret_value()})
        except HttpClientError as exc:
            # The URL is left out: its query string carries the API key.
            logger.error(f"OpenWeatherMap API returned HTTP {exc.status}: {exc.body[:200]!r}")
        except (ClientError, AsyncTimeoutError) as exc:
            logger.error(f"OpenWeatherMap API request failed: {repr(exc)}")
        finally:
            await self._db.increase_api_counter()
        return None

    def _parse_cities(self, raw_data: Any, lang: str) -> list[CityData]:
        """
        Parses a geocoding API response.

        :param raw_data: Raw geocoding API response.
        :param lang: ISO 639-1 user language code.
        :return: Parsed cities, malformed items skipped.
        """
        if not isinstance(raw_data, list):
            return []
        cities: list[CityData] = []
        for raw_city in raw_data:
            city: CityData | None = self._parser.parse_city(raw_data=raw_city, lang=lang)
            if city is not None:
                cities.append(city)
        return cities

    async def search_cities(self, city_name: str, lang: str) -> list[CityData]:
        """
        Finds cities by name.

        :param city_name: City name as typed by the user.
        :param lang: ISO 639-1 user language code.
        :return: Found cities (possibly none).
        """
        query: str = self.normalize_city_name(raw_city_name=city_name)
        if not query:
            return []
        raw_data: Any = await self._request(
            url=f"{self._GEOCODING_API_URL}/direct", params={"q": query, "limit": self._CITIES_LIMIT}
        )
        return self._parse_cities(raw_data=raw_data, lang=lang)

    async def reverse_geocode(self, latitude: float, longitude: float, lang: str) -> list[CityData]:
        """
        Finds cities near the given coordinates.

        :param latitude: Latitude.
        :param longitude: Longitude.
        :param lang: ISO 639-1 user language code.
        :return: Found cities (possibly none).
        """
        raw_data: Any = await self._request(
            url=f"{self._GEOCODING_API_URL}/reverse",
            params={"lat": latitude, "lon": longitude, "limit": self._CITIES_LIMIT},
        )
        return self._parse_cities(raw_data=raw_data, lang=lang)

    async def get_current_weather(
        self, latitude: float, longitude: float, lang: str, units: Units
    ) -> CurrentWeatherData | None:
        """
        Gets the current weather at a location.

        :param latitude: Latitude.
        :param longitude: Longitude.
        :param lang: ISO 639-1 language code of the weather description.
        :param units: Measurement units.
        :return: Current weather, or None if it couldn't be obtained.
        """
        raw_data: Any = await self._request(
            url=self._CURRENT_WEATHER_API_URL,
            params={"lat": latitude, "lon": longitude, "lang": lang, "units": units.value},
        )
        return self._parser.parse_current_weather(raw_data=raw_data) if isinstance(raw_data, dict) else None

    async def get_forecast(self, latitude: float, longitude: float, units: Units) -> ForecastData | None:
        """
        Gets the 24-hour weather forecast at a location.

        The forecast is language-independent (icons and numbers only), so callers can share one
        response between users of different languages.

        :param latitude: Latitude.
        :param longitude: Longitude.
        :param units: Measurement units.
        :return: Weather forecast, or None if it couldn't be obtained.
        """
        raw_data: Any = await self._request(
            url=self._FORECAST_API_URL,
            params={"lat": latitude, "lon": longitude, "units": units.value, "cnt": self._FORECAST_STEPS},
        )
        return self._parser.parse_forecast(raw_data=raw_data) if isinstance(raw_data, dict) else None
