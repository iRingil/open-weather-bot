"""
Unit tests for src/weather/parser.py (WeatherParser).

Pure functions over dicts shaped like real OpenWeatherMap responses - no network, no mocks.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from weather.data_types import CityData, CurrentWeatherData, ForecastData
from weather.parser import WeatherParser

__all__: tuple = ()

_TS: int = 1_700_000_000  # 2023-11-14 22:13:20 UTC


def _current(**overrides: Any) -> dict[str, Any]:
    """
    Builds a current weather response.

    :param overrides: Top-level keys to replace (a value of None removes the key).
    :return: Raw response dict.
    """
    raw: dict[str, Any] = {
        "weather": [{"id": 500, "description": "light rain", "icon": "10d"}],
        "main": {"temp": 12.6, "feels_like": 11.4, "pressure": 1012, "humidity": 81},
        "visibility": 9000,
        "wind": {"speed": 4.4, "gust": 9.6},
        "rain": {"1h": 0.43},
        "dt": _TS,
        "sys": {"sunrise": _TS - 3600, "sunset": _TS + 3600},
        "timezone": 10800,
    }
    for key, value in overrides.items():
        if value is None:
            raw.pop(key, None)
        else:
            raw[key] = value
    return raw


class TestParseCity:
    """Tests WeatherParser.parse_city."""

    def test_uses_local_name_and_state(self) -> None:
        """
        The local name in the user's language wins, and the state goes into full_name.

        :return: None
        """
        raw: dict[str, Any] = {
            "name": "Kyiv",
            "local_names": {"ru": "Киев"},
            "state": "Kyiv City",
            "country": "UA",
            "lat": 50.4500336123,
            "lon": 30.5241361789,
        }
        city: CityData | None = WeatherParser.parse_city(raw_data=raw, lang="ru")
        assert city == CityData(name="Киев", full_name="Киев, Kyiv City, UA", latitude=50.450034, longitude=30.524136)

    def test_falls_back_to_name_without_local_names_or_state(self) -> None:
        """
        Without local_names (or without the user's language there) and state, the plain name is used.

        :return: None
        """
        raw: dict[str, Any] = {"name": "Kyiv", "country": "UA", "lat": 1, "lon": 2}
        assert WeatherParser.parse_city(raw_data=raw, lang="de") == CityData(
            name="Kyiv", full_name="Kyiv, UA", latitude=1.0, longitude=2.0
        )
        raw["local_names"] = {"en": "Kyiv"}
        city: CityData | None = WeatherParser.parse_city(raw_data=raw, lang="uk")
        assert city is not None and city.name == "Kyiv"

    @pytest.mark.parametrize("raw", [{"name": "X", "lat": 1, "lon": 2}, {"name": "X", "country": "UA", "lat": "a"}])
    def test_malformed_returns_none(self, raw: dict[str, Any]) -> None:
        """
        A missing key or a non-numeric coordinate gives None instead of raising.

        :param raw: Malformed raw city.
        :return: None
        """
        assert WeatherParser.parse_city(raw_data=raw, lang="en") is None


class TestParseCurrentWeather:
    """Tests WeatherParser.parse_current_weather."""

    def test_full_response(self) -> None:
        """
        Every field is parsed and rounded, times are in the city's own timezone.

        :return: None
        """
        data: CurrentWeatherData | None = WeatherParser.parse_current_weather(raw_data=_current())
        assert data is not None
        assert data.time.strftime("%H:%M") == "01:13"
        tz: timezone = timezone(timedelta(seconds=10800))
        assert data == CurrentWeatherData(
            temp=13,
            feels_like=11,
            weather_code=500,
            description="light rain",
            wind_speed=4,
            gust=10,
            humidity=81,
            pressure=1012,
            visibility=9000,
            precipitation=0.43,
            time=datetime.fromtimestamp(_TS, tz=tz),
            sunrise=datetime.fromtimestamp(_TS - 3600, tz=tz),
            sunset=datetime.fromtimestamp(_TS + 3600, tz=tz),
        )

    def test_snow_takes_precedence_over_rain(self) -> None:
        """
        Snow volume is reported when present.

        :return: None
        """
        data: CurrentWeatherData | None = WeatherParser.parse_current_weather(raw_data=_current(snow={"1h": 1.5}))
        assert data is not None and data.precipitation == 1.5

    def test_no_precipitation_gust_or_visibility(self) -> None:
        """
        Missing rain/snow, gust and visibility give None.

        :return: None
        """
        raw: dict[str, Any] = _current(rain=None, visibility=None, wind={"speed": 3})
        data: CurrentWeatherData | None = WeatherParser.parse_current_weather(raw_data=raw)
        assert data is not None
        assert (data.precipitation, data.gust, data.visibility) == (None, None, None)

    def test_zero_values_become_none(self) -> None:
        """
        Zero gust, visibility and precipitation are treated as absent.

        :return: None
        """
        raw: dict[str, Any] = _current(rain={"1h": 0}, visibility=0, wind={"speed": 3, "gust": 0})
        data: CurrentWeatherData | None = WeatherParser.parse_current_weather(raw_data=raw)
        assert data is not None
        assert (data.precipitation, data.gust, data.visibility) == (None, None, None)

    @pytest.mark.parametrize("raw", [_current(main=None), _current(weather=[]), _current(timezone="x")])
    def test_malformed_returns_none(self, raw: dict[str, Any]) -> None:
        """
        A missing key, an empty list or a bad type gives None instead of raising.

        :param raw: Malformed response.
        :return: None
        """
        assert WeatherParser.parse_current_weather(raw_data=raw) is None


class TestParseForecast:
    """Tests WeatherParser.parse_forecast."""

    def test_points_in_city_local_time(self) -> None:
        """
        Every step is parsed, with its time converted using the response's city.timezone.

        :return: None
        """
        raw: dict[str, Any] = {
            "city": {"timezone": -18000},
            "list": [
                {"dt": _TS + i * 10800, "weather": [{"icon": "01d"}], "main": {"temp": 1.6}, "wind": {"speed": 2.4}}
                for i in range(2)
            ],
        }
        forecast: ForecastData | None = WeatherParser.parse_forecast(raw_data=raw)
        assert forecast is not None
        assert [point.time for point in forecast.points] == ["17:13", "20:13"]
        assert forecast.points[0].icon == "01d"
        assert (forecast.points[0].temp, forecast.points[0].wind_speed) == (2, 2)

    def test_empty_list_returns_none(self) -> None:
        """
        A response without steps gives None.

        :return: None
        """
        assert WeatherParser.parse_forecast(raw_data={"city": {"timezone": 0}, "list": []}) is None

    @pytest.mark.parametrize("raw", [{"list": []}, {"city": {"timezone": 0}, "list": [{"dt": 1}]}])
    def test_malformed_returns_none(self, raw: dict[str, Any]) -> None:
        """
        A missing key gives None instead of raising.

        :param raw: Malformed response.
        :return: None
        """
        assert WeatherParser.parse_forecast(raw_data=raw) is None
