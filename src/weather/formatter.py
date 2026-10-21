"""Turns weather data into the values shown in the current weather caption."""

from datetime import datetime
from math import log
from typing import Any

from babel.core import UnknownLocaleError
from babel.dates import format_datetime

from core.db.data_types import Units
from weather.data_types import CurrentWeatherData

__all__: tuple[str] = ("WeatherFormatter",)

# (weather condition codes, emoji), checked in order
_WEATHER_EMOJI: tuple[tuple[frozenset[int], str], ...] = (
    (frozenset({800}), "☀"),  # clear
    (frozenset({801}), "🌤"),  # few clouds
    (frozenset({803, 804}), "🌥"),  # broken / overcast clouds
    (frozenset({802}), "☁"),  # scattered clouds
    (frozenset({500, 501, 502, 503, 504}), "🌦"),  # rain
    (frozenset({300, 301, 302, 310, 311, 312, 313, 314, 321, 520, 521, 522, 531}), "🌧"),  # drizzle
    (frozenset({200, 201, 202, 210, 211, 212, 221, 230, 231, 232}), "⛈"),  # thunderstorm
    (frozenset({511, 600, 601, 602, 611, 612, 613, 615, 616, 620, 621, 622}), "🌨"),  # snow
    (frozenset({701, 711, 721, 731, 741, 751, 761, 762, 771, 781}), "🌫"),  # atmosphere
)
_DEFAULT_EMOJI: str = "🌀"


class WeatherFormatter:
    """
    Turns weather data into the values shown in the current weather caption.

    :cvar _MM_PER_INCH: Millimeters per inch.
    :cvar _METERS_PER_MILE: Meters per mile.
    :cvar _FALLBACK_LOCALE: Locale for dates when the user's language is unknown to Babel.
    """

    _MM_PER_INCH: float = 25.4
    _METERS_PER_MILE: float = 1609.344
    _FALLBACK_LOCALE: str = "en"

    @staticmethod
    def get_weather_emoji(weather_code: int) -> str:
        """
        Returns the emoji for an OpenWeatherMap weather condition code.

        :param weather_code: Weather condition code.
        :return: Matching emoji.
        """
        for codes, emoji in _WEATHER_EMOJI:
            if weather_code in codes:
                return emoji
        return _DEFAULT_EMOJI

    @staticmethod
    def calculate_dew_point(temp: int, humidity: int, units: Units) -> int:
        """
        Calculates the dew point (Magnus formula).

        :param temp: Temperature, in the given units.
        :param humidity: Relative humidity, in percent.
        :param units: Measurement units of temp and of the result.
        :return: Dew point, in the given units.
        """
        const_a: float = 17.27
        const_b: float = 237.7
        temp_celsius: float = temp if units == Units.METRIC else (temp - 32) * 5 / 9
        gamma: float = (const_a * temp_celsius) / (const_b + temp_celsius) + log(max(humidity, 1) / 100)
        dew_point: float = (const_b * gamma) / (const_a - gamma)
        return round(dew_point if units == Units.METRIC else dew_point * 9 / 5 + 32)

    @classmethod
    def format_time(cls, time: datetime, lang: str) -> str:
        """
        Formats the measurement time, e.g. "21 Oct 14:00", with the month name in the user's language.

        :param time: Time to format (already in the location's local time).
        :param lang: ISO 639-1 user language code.
        :return: Formatted time.
        """
        try:
            return format_datetime(datetime=time, format="d MMM HH:mm", locale=lang)
        except (UnknownLocaleError, ValueError):
            return format_datetime(datetime=time, format="d MMM HH:mm", locale=cls._FALLBACK_LOCALE)

    @classmethod
    def build_context(cls, data: CurrentWeatherData, units: Units, city: str, lang: str) -> dict[str, Any]:
        """
        Builds the template context of the current weather caption.

        :param data: Current weather.
        :param units: Measurement units data was requested in.
        :param city: City name to show.
        :param lang: ISO 639-1 user language code.
        :return: Template context.
        """
        metric: bool = units == Units.METRIC
        precipitation: float | None = None
        if data.precipitation:
            precipitation = round(data.precipitation if metric else data.precipitation / cls._MM_PER_INCH, 2)
        visibility: float | None = None
        if data.visibility:
            visibility = round(data.visibility / (1000 if metric else cls._METERS_PER_MILE), 1)
        return {
            "city": city,
            "time": cls.format_time(time=data.time, lang=lang),
            "emoji": cls.get_weather_emoji(weather_code=data.weather_code),
            "description": data.description,
            "precipitation": precipitation,
            "temp": data.temp,
            "feels_like": data.feels_like,
            "humidity": data.humidity,
            "dew_point": cls.calculate_dew_point(temp=data.temp, humidity=data.humidity, units=units),
            "wind_speed": data.wind_speed,
            "gust": data.gust,
            "pressure": data.pressure,
            "visibility": visibility,
            "sunrise": data.sunrise.strftime("%H:%M"),
            "sunset": data.sunset.strftime("%H:%M"),
            "temp_unit": "°C" if metric else "°F",
            "wind_unit": "m/s" if metric else "mph",
            "precip_unit": "mm" if metric else "in",
            "vis_unit": "km" if metric else "mi",
        }
