"""Parses raw OpenWeatherMap API responses into typed data."""

from datetime import datetime, timedelta, timezone
from typing import Any

from loguru import logger

from weather.data_types import CityData, CurrentWeatherData, ForecastData, ForecastPoint

__all__: tuple[str] = ("WeatherParser",)

_PARSE_ERRORS: tuple[type[Exception], ...] = (KeyError, IndexError, TypeError, ValueError)


class WeatherParser:
    """Parses raw OpenWeatherMap API responses into typed data."""

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

    @staticmethod
    def parse_current_weather(raw_data: dict[str, Any]) -> CurrentWeatherData | None:
        """
        Parses a current weather API response.

        :param raw_data: Raw current weather API response.
        :return: Parsed current weather, or None if the data is malformed.
        """
        try:
            city_tz: timezone = timezone(timedelta(seconds=raw_data["timezone"]))
            wind: dict[str, Any] = raw_data["wind"]
            precipitation_data: dict[str, Any] = raw_data.get("snow") or raw_data.get("rain") or {}
            precipitation: float | None = precipitation_data.get("1h")
            visibility: int | None = raw_data.get("visibility")
            return CurrentWeatherData(
                temp=round(raw_data["main"]["temp"]),
                feels_like=round(raw_data["main"]["feels_like"]),
                weather_code=raw_data["weather"][0]["id"],
                description=raw_data["weather"][0]["description"],
                wind_speed=round(wind["speed"]),
                gust=round(wind["gust"]) if wind.get("gust") else None,
                humidity=raw_data["main"]["humidity"],
                pressure=raw_data["main"]["pressure"],
                visibility=visibility or None,
                precipitation=precipitation or None,
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
