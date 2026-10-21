"""
Unit tests for src/weather/formatter.py (WeatherFormatter).

Pure functions - dates are formatted by the real Babel locale data.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from core.db.data_types import Units
from weather.data_types import CurrentWeatherData
from weather.formatter import WeatherFormatter

__all__: tuple = ()

_TZ: timezone = timezone(timedelta(hours=3))


def _current(**overrides: Any) -> CurrentWeatherData:
    """
    Builds current weather data.

    :param overrides: Fields to replace.
    :return: CurrentWeatherData instance.
    """
    data: CurrentWeatherData = CurrentWeatherData(
        temp=20,
        feels_like=19,
        weather_code=800,
        description="clear sky",
        wind_speed=3,
        gust=7,
        humidity=50,
        pressure=1013,
        visibility=10000,
        precipitation=2.54,
        time=datetime(2026, 10, 21, 14, 5, tzinfo=_TZ),
        sunrise=datetime(2026, 10, 21, 7, 2, tzinfo=_TZ),
        sunset=datetime(2026, 10, 21, 18, 9, tzinfo=_TZ),
    )
    return data._replace(**overrides)


class TestGetWeatherEmoji:
    """Tests WeatherFormatter.get_weather_emoji."""

    @pytest.mark.parametrize(
        ("code", "emoji"),
        [
            (800, "☀"),
            (801, "🌤"),
            (802, "☁"),
            (803, "🌥"),
            (804, "🌥"),
            (502, "🌦"),
            (521, "🌧"),
            (300, "🌧"),
            (211, "⛈"),
            (511, "🌨"),
            (601, "🌨"),
            (741, "🌫"),
            (999, "🌀"),
        ],
    )
    def test_maps_codes(self, code: int, emoji: str) -> None:
        """
        Each condition code group gets its emoji, unknown codes the default one.

        :param code: Weather condition code.
        :param emoji: Expected emoji.
        :return: None
        """
        assert WeatherFormatter.get_weather_emoji(weather_code=code) == emoji


class TestCalculateDewPoint:
    """Tests WeatherFormatter.calculate_dew_point."""

    def test_metric(self) -> None:
        """
        20°C at 50% humidity gives a 9°C dew point.

        :return: None
        """
        assert WeatherFormatter.calculate_dew_point(temp=20, humidity=50, units=Units.METRIC) == 9

    def test_imperial_is_computed_in_celsius_and_converted_back(self) -> None:
        """
        68°F (20°C) at 50% humidity gives 49°F (9.3°C), not the formula applied to °F directly.

        :return: None
        """
        assert WeatherFormatter.calculate_dew_point(temp=68, humidity=50, units=Units.IMPERIAL) == 49

    def test_saturated_air_dew_point_equals_temperature(self) -> None:
        """
        At 100% humidity the dew point equals the temperature.

        :return: None
        """
        assert WeatherFormatter.calculate_dew_point(temp=15, humidity=100, units=Units.METRIC) == 15

    def test_zero_humidity_does_not_crash(self) -> None:
        """
        0% humidity (log(0)) is clamped instead of raising.

        :return: None
        """
        assert isinstance(WeatherFormatter.calculate_dew_point(temp=15, humidity=0, units=Units.METRIC), int)


class TestFormatTime:
    """Tests WeatherFormatter.format_time."""

    @pytest.mark.parametrize(
        ("lang", "expected"),
        [("en", "21 Oct 14:05"), ("ru", "21 окт. 14:05"), ("uk", "21 жовт. 14:05"), ("zz", "21 Oct 14:05")],
    )
    def test_localized_month_and_local_time(self, lang: str, expected: str) -> None:
        """
        The month name follows the language, the time stays in the location's own timezone, and an
        unknown language falls back to English.

        :param lang: Language code.
        :param expected: Expected formatted time.
        :return: None
        """
        assert WeatherFormatter.format_time(time=_current().time, lang=lang) == expected

    def test_invalid_locale_string_falls_back(self) -> None:
        """
        A malformed language code (ValueError in Babel) also falls back to English.

        :return: None
        """
        assert WeatherFormatter.format_time(time=_current().time, lang="e!") == "21 Oct 14:05"


class TestBuildContext:
    """Tests WeatherFormatter.build_context."""

    def test_metric(self) -> None:
        """
        Metric values pass through; visibility is converted from meters to kilometers.

        :return: None
        """
        ctx: dict[str, Any] = WeatherFormatter.build_context(
            data=_current(), units=Units.METRIC, city="Kyiv", lang="en"
        )
        assert ctx == {
            "city": "Kyiv",
            "time": "21 Oct 14:05",
            "emoji": "☀",
            "description": "clear sky",
            "precipitation": 2.54,
            "temp": 20,
            "feels_like": 19,
            "humidity": 50,
            "dew_point": 9,
            "wind_speed": 3,
            "gust": 7,
            "pressure": 1013,
            "visibility": 10.0,
            "sunrise": "07:02",
            "sunset": "18:09",
            "temp_unit": "°C",
            "wind_unit": "m/s",
            "precip_unit": "mm",
            "vis_unit": "km",
        }

    def test_imperial_converts_precipitation_and_visibility(self) -> None:
        """
        Imperial precipitation is converted from mm to inches and visibility from meters to miles.

        :return: None
        """
        ctx: dict[str, Any] = WeatherFormatter.build_context(
            data=_current(temp=68), units=Units.IMPERIAL, city="Kyiv", lang="en"
        )
        assert ctx["precipitation"] == 0.1
        assert ctx["visibility"] == 6.2
        assert (ctx["temp_unit"], ctx["wind_unit"], ctx["precip_unit"], ctx["vis_unit"]) == ("°F", "mph", "in", "mi")

    def test_missing_precipitation_and_visibility(self) -> None:
        """
        No precipitation and no visibility stay None.

        :return: None
        """
        ctx: dict[str, Any] = WeatherFormatter.build_context(
            data=_current(precipitation=None, visibility=None), units=Units.METRIC, city="Kyiv", lang="en"
        )
        assert ctx["precipitation"] is None and ctx["visibility"] is None
