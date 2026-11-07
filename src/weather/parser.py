"""Parses raw OpenWeatherMap API responses into typed data."""

from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import ClassVar, cast

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from core.http_client import JsonValue
from weather.data_types import CityData, CurrentWeatherData, ForecastData, ForecastPoint

__all__: tuple[str] = ("WeatherParser",)

# A malformed response, or a value out of range (NaN, Infinity, a huge timestamp)
_PARSE_ERRORS: tuple[type[Exception], ...] = (ValidationError, ValueError, OverflowError, OSError)


class _Response(BaseModel):
    """Base of the response models: strict types, unknown fields ignored."""

    model_config: ClassVar[ConfigDict] = ConfigDict(strict=True, frozen=True)


class _City(_Response):
    """One item of a geocoding API response."""

    name: str
    country: str
    lat: float
    lon: float
    state: str | None = None
    local_names: dict[str, str] | None = None


class _Condition(_Response):
    """A weather condition of a current weather or forecast response."""

    id: int = 0
    description: str = ""
    icon: str = ""


class _Main(_Response):
    """The "main" block of a current weather response."""

    temp: float
    feels_like: float
    humidity: int
    pressure: int


class _Wind(_Response):
    """The "wind" block of a current weather response; a malformed gust is dropped, not rejected."""

    speed: float
    gust: object = None


class _Sun(_Response):
    """The "sys" block of a current weather response."""

    sunrise: int
    sunset: int


class _CurrentWeather(_Response):
    """A current weather API response; malformed optional fields are dropped, not rejected."""

    timezone: int
    dt: int
    main: _Main
    weather: list[_Condition] = Field(min_length=1)
    wind: _Wind
    sys: _Sun
    visibility: object = None
    rain: object = None
    snow: object = None


class _StepMain(_Response):
    """The "main" block of a forecast step."""

    temp: float


class _StepWind(_Response):
    """The "wind" block of a forecast step."""

    speed: float


class _Step(_Response):
    """One 3-hour step of a forecast response."""

    dt: int
    weather: list[_Condition] = Field(min_length=1)
    main: _StepMain
    wind: _StepWind


class _ForecastCity(_Response):
    """The "city" block of a forecast response."""

    timezone: int


class _Forecast(_Response):
    """A 5 day / 3-hour forecast API response."""

    city: _ForecastCity
    steps: list[_Step] = Field(alias="list")


class WeatherParser:
    """
    Parses raw OpenWeatherMap API responses into typed data.

    A response missing (or holding a malformed) required field is rejected as a whole. Optional
    fields - wind gusts, visibility and precipitation - are dropped on their own instead.
    """

    @staticmethod
    def _optional_number(value: object) -> float | None:
        """
        Validates the value of an optional numeric field.

        :param value: Raw value, possibly missing (None) or malformed.
        :return: The value if it is a positive finite number, otherwise None.
        """
        if isinstance(value, bool) or not isinstance(value, int | float) or not isfinite(value) or value <= 0:
            return None
        return value

    @classmethod
    def _precipitation(cls, raw: _CurrentWeather) -> float | None:
        """
        Extracts the precipitation over the last hour - snow if reported, otherwise rain.

        :param raw: Validated current weather response.
        :return: Precipitation in millimeters, or None if there was none, or it is malformed.
        """
        block: object = raw.snow or raw.rain
        if not isinstance(block, dict):
            return None
        # basedpyright needs the cast: isinstance(..., dict) only gives dict[Unknown, Unknown]
        # noinspection PyUnnecessaryCast
        return cls._optional_number(cast("dict[str, object]", block).get("1h"))

    @staticmethod
    def parse_city(raw_data: JsonValue, lang: str) -> CityData | None:
        """
        Parses one city from a geocoding API response.

        :param raw_data: One raw item of the geocoding API response.
        :param lang: ISO 639-1 user language code, to pick the city's local name.
        :return: Parsed city, or None if the data is malformed.
        """
        try:
            raw: _City = _City.model_validate(raw_data)
        except _PARSE_ERRORS as exc:
            logger.error(f"Error when parsing city data: {exc!r}")
            return None
        name: str = (raw.local_names or {}).get(lang) or raw.name
        return CityData(
            name=name,
            full_name=f"{name}, {raw.state}, {raw.country}" if raw.state else f"{name}, {raw.country}",
            latitude=round(raw.lat, 6),
            longitude=round(raw.lon, 6),
        )

    @classmethod
    def parse_current_weather(cls, raw_data: JsonValue) -> CurrentWeatherData | None:
        """
        Parses a current weather API response.

        :param raw_data: Raw current weather API response.
        :return: Parsed current weather, or None if the data is malformed.
        """
        try:
            raw: _CurrentWeather = _CurrentWeather.model_validate(raw_data)
            city_tz: timezone = timezone(timedelta(seconds=raw.timezone))
            gust: float | None = cls._optional_number(raw.wind.gust)
            visibility: float | None = cls._optional_number(raw.visibility)
            return CurrentWeatherData(
                temp=round(raw.main.temp),
                feels_like=round(raw.main.feels_like),
                weather_code=raw.weather[0].id,
                description=raw.weather[0].description,
                wind_speed=round(raw.wind.speed),
                gust=round(gust) if gust else None,
                humidity=raw.main.humidity,
                pressure=raw.main.pressure,
                visibility=round(visibility) if visibility else None,
                precipitation=cls._precipitation(raw=raw),
                time=datetime.fromtimestamp(raw.dt, tz=city_tz),
                sunrise=datetime.fromtimestamp(raw.sys.sunrise, tz=city_tz),
                sunset=datetime.fromtimestamp(raw.sys.sunset, tz=city_tz),
            )
        except _PARSE_ERRORS as exc:
            logger.error(f"Error when parsing current weather data: {exc!r}")
        return None

    @staticmethod
    def parse_forecast(raw_data: JsonValue) -> ForecastData | None:
        """
        Parses a 5 day / 3-hour forecast API response.

        Times are converted to the forecast location's local time (city.timezone of the response),
        not the server's.

        :param raw_data: Raw forecast API response.
        :return: Parsed forecast, or None if the data is malformed or empty.
        """
        try:
            raw: _Forecast = _Forecast.model_validate(raw_data)
            city_tz: timezone = timezone(timedelta(seconds=raw.city.timezone))
            points: tuple[ForecastPoint, ...] = tuple(
                ForecastPoint(
                    time=datetime.fromtimestamp(step.dt, tz=city_tz).strftime("%H:%M"),
                    icon=step.weather[0].icon,
                    temp=round(step.main.temp),
                    wind_speed=round(step.wind.speed),
                )
                for step in raw.steps
            )
        except _PARSE_ERRORS as exc:
            logger.error(f"Error when parsing weather forecast data: {exc!r}")
            return None
        return ForecastData(points=points) if points else None
