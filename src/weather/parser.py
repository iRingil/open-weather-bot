"""Parses raw OpenWeatherMap API responses into typed data."""

from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Any

from loguru import logger

from weather.data_types import CityData, CurrentWeatherData, ForecastData, ForecastPoint

__all__: tuple[str] = ("WeatherParser",)

# A missing key or list item, a wrong type, or a value out of range (NaN, Infinity, a huge timestamp)
_PARSE_ERRORS: tuple[type[Exception], ...] = (
    KeyError,
    IndexError,
    TypeError,
    AttributeError,
    ValueError,
    OverflowError,
    OSError,
)


class WeatherParser:
    """
    Parses raw OpenWeatherMap API responses into typed data.

    A response missing (or holding a malformed) required field is rejected as a whole. Optional
    fields - wind gusts, visibility and precipitation - are dropped on their own instead.
    """

    @staticmethod
    def _optional_number(value: Any) -> float | None:
        """
        Validates the value of an optional numeric field.

        :param value: Raw value, possibly missing (None) or malformed.
        :return: The value if it is a positive finite number, otherwise None.
        """
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value <= 0:
            return None
        return value

    @staticmethod
    def parse_city(raw_data: dict[str, Any], lang: str) -> CityData | None:
        """
        Parses one city from a geocoding API response.

        :param raw_data: One raw item of the geocoding API response.
        :param lang: ISO 639-1 user language code, to pick the city's local name.
        :return: Parsed city, or None if the data is malformed.
        """
        try:
            local_names: dict[str, str] = raw_data.get("local_names") or {}
            name: str = local_names.get(lang) or raw_data["name"]
            state: str | None = raw_data.get("state")
            country: str = raw_data["country"]
            return CityData(
                name=name,
                full_name=f"{name}, {state}, {country}" if state else f"{name}, {country}",
                latitude=round(float(raw_data["lat"]), 6),
                longitude=round(float(raw_data["lon"]), 6),
            )
        except _PARSE_ERRORS as exc:
            logger.error(f"Error when parsing city data: {repr(exc)}")
        return None

    @classmethod
    def parse_current_weather(cls, raw_data: dict[str, Any]) -> CurrentWeatherData | None:
        """
        Parses a current weather API response.

        :param raw_data: Raw current weather API response.
        :return: Parsed current weather, or None if the data is malformed.
        """
        try:
            city_tz: timezone = timezone(timedelta(seconds=raw_data["timezone"]))
            wind: dict[str, Any] = raw_data["wind"]
            gust: float | None = cls._optional_number(wind.get("gust"))
            visibility: float | None = cls._optional_number(raw_data.get("visibility"))
            precipitation_data: Any = raw_data.get("snow") or raw_data.get("rain")
            precipitation: float | None = (
                cls._optional_number(precipitation_data.get("1h")) if isinstance(precipitation_data, dict) else None
            )
            return CurrentWeatherData(
                temp=round(raw_data["main"]["temp"]),
                feels_like=round(raw_data["main"]["feels_like"]),
                weather_code=raw_data["weather"][0]["id"],
                description=raw_data["weather"][0]["description"],
                wind_speed=round(wind["speed"]),
                gust=round(gust) if gust else None,
                humidity=raw_data["main"]["humidity"],
                pressure=raw_data["main"]["pressure"],
                visibility=round(visibility) if visibility else None,
                precipitation=precipitation,
                time=datetime.fromtimestamp(raw_data["dt"], tz=city_tz),
                sunrise=datetime.fromtimestamp(raw_data["sys"]["sunrise"], tz=city_tz),
                sunset=datetime.fromtimestamp(raw_data["sys"]["sunset"], tz=city_tz),
            )
        except _PARSE_ERRORS as exc:
            logger.error(f"Error when parsing current weather data: {repr(exc)}")
        return None

    @staticmethod
    def parse_forecast(raw_data: dict[str, Any]) -> ForecastData | None:
        """
        Parses a 5 day / 3-hour forecast API response.

        Times are converted to the forecast location's local time (city.timezone of the response),
        not the server's.

        :param raw_data: Raw forecast API response.
        :return: Parsed forecast, or None if the data is malformed or empty.
        """
        try:
            city_tz: timezone = timezone(timedelta(seconds=raw_data["city"]["timezone"]))
            points: tuple[ForecastPoint, ...] = tuple(
                ForecastPoint(
                    time=datetime.fromtimestamp(item["dt"], tz=city_tz).strftime("%H:%M"),
                    icon=item["weather"][0]["icon"],
                    temp=round(item["main"]["temp"]),
                    wind_speed=round(item["wind"]["speed"]),
                )
                for item in raw_data["list"]
            )
        except _PARSE_ERRORS as exc:
            logger.error(f"Error when parsing weather forecast data: {repr(exc)}")
            return None
        return ForecastData(points=points) if points else None
