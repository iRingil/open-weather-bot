"""Typed data structures parsed from OpenWeatherMap API responses."""

from datetime import datetime
from typing import NamedTuple

__all__: tuple[str, ...] = ("CityData", "CurrentWeatherData", "ForecastData", "ForecastPoint")


class CityData(NamedTuple):
    """
    A city found by the OpenWeatherMap geocoding API.

    :param name: City name, localized to the user's language if OpenWeatherMap knows it.
    :param full_name: City name with its state (if any) and country, e.g. "Kyiv, UA".
    :param latitude: City latitude.
    :param longitude: City longitude.
    """

    name: str
    full_name: str
    latitude: float
    longitude: float


class CurrentWeatherData(NamedTuple):
    """
    Current weather at a location.

    Temperatures and wind speeds are in the units the data was requested in (metric or imperial);
    visibility, precipitation and pressure are always metric, as OpenWeatherMap returns them.

    :param temp: Temperature.
    :param feels_like: Perceived temperature.
    :param weather_code: OpenWeatherMap weather condition code.
    :param description: Weather condition description, in the requested language.
    :param wind_speed: Wind speed.
    :param gust: Wind gust speed, or None if not reported.
    :param humidity: Relative humidity, in percent.
    :param pressure: Atmospheric pressure, in hPa.
    :param visibility: Visibility in meters, or None if not reported.
    :param precipitation: Precipitation over the last hour in millimeters, or None if there was none.
    :param time: Time of the measurement, in the location's local time.
    :param sunrise: Sunrise time, in the location's local time.
    :param sunset: Sunset time, in the location's local time.
    """

    temp: int
    feels_like: int
    weather_code: int
    description: str
    wind_speed: int
    gust: int | None
    humidity: int
    pressure: int
    visibility: int | None
    precipitation: float | None
    time: datetime
    sunrise: datetime
    sunset: datetime


class ForecastPoint(NamedTuple):
    """
    One 3-hour step of the weather forecast.

    :param time: Local time of the step at the forecast location, as "HH:MM".
    :param icon: OpenWeatherMap weather icon code, e.g. "01d".
    :param temp: Temperature, in the requested units.
    :param wind_speed: Wind speed, in the requested units.
    """

    time: str
    icon: str
    temp: int
    wind_speed: int


class ForecastData(NamedTuple):
    """
    Weather forecast for the next 24 hours.

    :param points: Forecast steps, 3 hours apart.
    """

    points: tuple[ForecastPoint, ...]
