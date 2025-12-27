"""Classes for working with data."""

from typing import NamedTuple

__all__: tuple[str, ...] = ("CityData", "CurrentWeatherData", "ForecastData", "User", "UserWeatherSettings")


class User(NamedTuple):
    """
    A class that describes a user.

    :param id: User id.
    :param dialog_id: Last dialogue message id.
    """

    id: int
    dialog_id: int


class UserWeatherSettings(NamedTuple):
    """
    A class that describes the user's weather settings.

    :param lang: ISO 639-1 user language code.
    :param city: Selected city name.
    :param latitude: Selected city latitude.
    :param longitude: Selected city longitude.
    :param units: Measurement units (metric or imperial).
    """

    lang: str
    city: str
    latitude: float
    longitude: float
    units: str


class CityData(NamedTuple):
    """
    A class describing city data.

    :param name: City name.
    :param full_name: Full city name with country and state (if available).
    :param latitude: City latitude.
    :param longitude: City longitude.
    """

    name: str
    full_name: str
    latitude: float
    longitude: float


class CurrentWeatherData(NamedTuple):
    """
    A class describing current weather data.

    :param temp: Temperature in Celsius.
    :param feels_like: Temperature that feels like in Celsius.
    :param weather_code: Weather condition code.
    :param weather_description: Description of weather condition.
    :param wind_speed: Wind speed in meters per second.
    :param gust: Wind gust in meters per second.
    :param humidity: Humidity in percent.
    :param pressure: Atmospheric pressure in millibars.
    :param visibility: Visibility in kilometers or None.
    :param precipitation: Precipitation in millimeters or None.
    :param time: Time of the measurement.
    :param sunrise: Sunrise time in UTC.
    :param sunset: Sunset time in UTC.
    """

    temp: int
    feels_like: int
    weather_code: int
    weather_description: str
    wind_speed: int
    gust: int | None
    humidity: int
    pressure: int
    visibility: float | None
    precipitation: float | None
    time: str
    sunrise: str
    sunset: str


class ForecastData(NamedTuple):
    """
    A class describing weather forecast data.

    :param time: List of times of the measurements.
    :param ico_code: List of weather condition codes.
    :param temp: List of temperatures in Celsius.
    :param wind_speed: List of wind speeds in meters per second.
    """

    time: list[str]
    ico_code: list[str]
    temp: list[str]
    wind_speed: list[str]
