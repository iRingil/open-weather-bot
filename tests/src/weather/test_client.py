"""
Unit tests for src/weather/client.py (WeatherAPI).

HttpClient and Database are autospecced - no network or database. Loguru output is captured
through a temporary list sink to check the API key never reaches the log.
"""

import asyncio
from typing import Any, Iterator
from unittest.mock import AsyncMock, MagicMock, create_autospec

import aiohttp
import pytest
from loguru import logger
from pydantic import SecretStr

import weather.client as client_module
from core.db.data_types import Units
from core.db.repository import Database
from core.http_client import HttpClient, HttpClientError
from weather.client import WeatherAPI
from weather.data_types import CityData, CurrentWeatherData, ForecastData

__all__: tuple = ()

_TOKEN: str = "secret-api-key"


@pytest.fixture(name="http")
def http_fixture() -> MagicMock:
    """
    An autospecced HttpClient whose get() returns None unless a test sets otherwise.

    :return: The mocked HttpClient.
    """
    mock: MagicMock = create_autospec(spec=HttpClient, instance=True)
    mock.get = AsyncMock(return_value=None)
    return mock


@pytest.fixture(name="db")
def db_fixture() -> MagicMock:
    """
    An autospecced Database.

    :return: The mocked Database.
    """
    mock: MagicMock = create_autospec(spec=Database, instance=True)
    mock.increase_api_counter = AsyncMock(return_value=None)
    return mock


@pytest.fixture(name="api")
def api_fixture(http: MagicMock, db: MagicMock) -> WeatherAPI:
    """
    A WeatherAPI over the mocked dependencies.

    :param http: The mocked HttpClient.
    :param db: The mocked Database.
    :return: WeatherAPI instance.
    """
    return WeatherAPI(http_client=http, token=SecretStr(_TOKEN), db=db)


@pytest.fixture(name="log_messages")
def log_messages_fixture() -> Iterator[list[str]]:
    """
    Collects every loguru message emitted during the test.

    :return: The list the messages are appended to.
    """
    messages: list[str] = []
    sink_id: int = logger.add(sink=lambda msg: messages.append(str(msg)), level="DEBUG")
    yield messages
    logger.remove(sink_id)


def _get_kwargs(http: MagicMock) -> dict[str, Any]:
    """
    Returns the keyword arguments of the last HttpClient.get call.

    :param http: The mocked HttpClient.
    :return: Keyword arguments.
    """
    kwargs: dict[str, Any] = http.get.await_args.kwargs
    return dict(kwargs)


class TestNormalizeCityName:
    """Tests WeatherAPI.normalize_city_name."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Kyiv", "Kyiv"),
            ("  New   York!! ", "New York"),
            ("Ростов-на-Дону 123", "Ростов-на-Дону"),
            ("<script>", "script"),
            ("123 !!", ""),
            ("a" * 100, "a" * 72),
        ],
    )
    def test_keeps_letters_hyphens_and_single_spaces(self, raw: str, expected: str) -> None:
        """
        Only letters, hyphens and single spaces of the first 72 characters are kept.

        :param raw: Raw input.
        :param expected: Expected normalized name.
        :return: None
        """
        assert WeatherAPI.normalize_city_name(raw_city_name=raw) == expected


class TestSearchCities:
    """Tests WeatherAPI.search_cities."""

    async def test_empty_query_makes_no_request(self, api: WeatherAPI, http: MagicMock, db: MagicMock) -> None:
        """
        A name with nothing left after normalization isn't sent to the API at all.

        :param api: WeatherAPI fixture.
        :param http: The mocked HttpClient.
        :param db: The mocked Database.
        :return: None
        """
        assert await api.search_cities(city_name="123", lang="en") == []
        http.get.assert_not_awaited()
        db.increase_api_counter.assert_not_awaited()

    async def test_sends_query_and_parses_cities(self, api: WeatherAPI, http: MagicMock, db: MagicMock) -> None:
        """
        The normalized name, the limit and the key are sent; malformed items are skipped.

        :param api: WeatherAPI fixture.
        :param http: The mocked HttpClient.
        :param db: The mocked Database.
        :return: None
        """
        http.get.return_value = [{"name": "Kyiv", "country": "UA", "lat": 1, "lon": 2}, {"name": "broken"}]
        cities: list[CityData] = await api.search_cities(city_name=" Kyiv! ", lang="en")
        assert cities == [CityData(name="Kyiv", full_name="Kyiv, UA", latitude=1.0, longitude=2.0)]
        assert _get_kwargs(http) == {
            "url": "https://api.openweathermap.org/geo/1.0/direct",
            "params": {"q": "Kyiv", "limit": 5, "appid": _TOKEN},
        }
        db.increase_api_counter.assert_awaited_once_with()

    async def test_non_list_response_gives_no_cities(self, api: WeatherAPI, http: MagicMock) -> None:
        """
        An unexpected response shape gives an empty list.

        :param api: WeatherAPI fixture.
        :param http: The mocked HttpClient.
        :return: None
        """
        http.get.return_value = {"cod": "400"}
        assert await api.search_cities(city_name="Kyiv", lang="en") == []


class TestReverseGeocode:
    """Tests WeatherAPI.reverse_geocode."""

    async def test_sends_coordinates(self, api: WeatherAPI, http: MagicMock) -> None:
        """
        The coordinates and the limit are sent to the reverse geocoding endpoint.

        :param api: WeatherAPI fixture.
        :param http: The mocked HttpClient.
        :return: None
        """
        http.get.return_value = [{"name": "Kyiv", "country": "UA", "lat": 1, "lon": 2}]
        cities: list[CityData] = await api.reverse_geocode(latitude=50.4, longitude=30.5, lang="en")
        assert len(cities) == 1
        assert _get_kwargs(http) == {
            "url": "https://api.openweathermap.org/geo/1.0/reverse",
            "params": {"lat": 50.4, "lon": 30.5, "limit": 5, "appid": _TOKEN},
        }


class TestGetCurrentWeather:
    """Tests WeatherAPI.get_current_weather."""

    async def test_sends_params_and_parses(self, api: WeatherAPI, http: MagicMock) -> None:
        """
        Coordinates, language and units are sent; a dict response is parsed.

        :param api: WeatherAPI fixture.
        :param http: The mocked HttpClient.
        :return: None
        """
        http.get.return_value = {
            "weather": [{"id": 800, "description": "clear"}],
            "main": {"temp": 1, "feels_like": 1, "pressure": 1000, "humidity": 50},
            "wind": {"speed": 1},
            "dt": 0,
            "sys": {"sunrise": 0, "sunset": 0},
            "timezone": 0,
        }
        data: CurrentWeatherData | None = await api.get_current_weather(
            latitude=1.5, longitude=2.5, lang="ru", units=Units.IMPERIAL
        )
        assert data is not None and data.description == "clear"
        assert _get_kwargs(http) == {
            "url": "https://api.openweathermap.org/data/2.5/weather",
            "params": {"lat": 1.5, "lon": 2.5, "lang": "ru", "units": "imperial", "appid": _TOKEN},
        }

    async def test_non_dict_response_gives_none(self, api: WeatherAPI, http: MagicMock) -> None:
        """
        A failed request (None) gives None.

        :param api: WeatherAPI fixture.
        :param http: The mocked HttpClient.
        :return: None
        """
        http.get.return_value = None
        assert await api.get_current_weather(latitude=1, longitude=2, lang="en", units=Units.METRIC) is None


class TestGetForecast:
    """Tests WeatherAPI.get_forecast."""

    async def test_sends_params_and_parses(self, api: WeatherAPI, http: MagicMock) -> None:
        """
        Coordinates, units and the step count are sent (no language); a dict response is parsed.

        :param api: WeatherAPI fixture.
        :param http: The mocked HttpClient.
        :return: None
        """
        http.get.return_value = {
            "city": {"timezone": 0},
            "list": [{"dt": 0, "weather": [{"icon": "01d"}], "main": {"temp": 1}, "wind": {"speed": 1}}],
        }
        forecast: ForecastData | None = await api.get_forecast(latitude=1, longitude=2, units=Units.METRIC)
        assert forecast is not None and len(forecast.points) == 1
        assert _get_kwargs(http) == {
            "url": "https://api.openweathermap.org/data/2.5/forecast",
            "params": {"lat": 1, "lon": 2, "units": "metric", "cnt": 8, "appid": _TOKEN},
        }

    async def test_non_dict_response_gives_none(self, api: WeatherAPI, http: MagicMock) -> None:
        """
        A list response gives None.

        :param api: WeatherAPI fixture.
        :param http: The mocked HttpClient.
        :return: None
        """
        http.get.return_value = []
        assert await api.get_forecast(latitude=1, longitude=2, units=Units.METRIC) is None


class TestRequestErrors:
    """Tests WeatherAPI._request error handling, through the public methods."""

    @pytest.mark.parametrize(
        "exc",
        [
            HttpClientError(status=401, url=f"https://x?appid={_TOKEN}", body=b'{"message": "Invalid API key"}'),
            aiohttp.ClientConnectionError("connection reset"),
            asyncio.TimeoutError(),
        ],
    )
    async def test_errors_give_none_are_counted_and_hide_the_key(
        self, api: WeatherAPI, http: MagicMock, db: MagicMock, log_messages: list[str], exc: Exception
    ) -> None:
        """
        A failed request gives None, is still counted, and is logged without the API key.

        :param api: WeatherAPI fixture.
        :param http: The mocked HttpClient.
        :param db: The mocked Database.
        :param log_messages: Captured log messages.
        :param exc: The exception HttpClient.get raises.
        :return: None
        """
        http.get.side_effect = exc
        assert await api.get_forecast(latitude=1, longitude=2, units=Units.METRIC) is None
        db.increase_api_counter.assert_awaited_once_with()
        assert log_messages
        assert all(_TOKEN not in message for message in log_messages)

    async def test_http_error_logs_status_and_body(
        self, api: WeatherAPI, http: MagicMock, log_messages: list[str]
    ) -> None:
        """
        An HTTP error is logged with its status and (truncated) body.

        :param api: WeatherAPI fixture.
        :param http: The mocked HttpClient.
        :param log_messages: Captured log messages.
        :return: None
        """
        http.get.side_effect = HttpClientError(status=429, url="https://x", body=b"too many")
        await api.search_cities(city_name="Kyiv", lang="en")
        assert any("HTTP 429" in message and "too many" in message for message in log_messages)


class TestRateLimit:
    """Tests WeatherAPI._wait_for_slot spacing of requests."""

    async def test_second_request_waits_for_the_interval(
        self, api: WeatherAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """
        A request 0.25s after the previous one sleeps the rest of the 60/55s interval; a later one doesn't sleep.

        :param api: WeatherAPI fixture.
        :param monkeypatch: pytest's monkeypatch fixture.
        :return: None
        """
        clock: list[float] = [100.0]
        sleeps: list[float] = []

        async def fake_sleep(delay: float) -> None:
            """
            Records the delay and advances the fake clock.

            :param delay: Requested delay.
            :return: None
            """
            sleeps.append(delay)
            clock[0] += delay

        monkeypatch.setattr(client_module, "monotonic", lambda: clock[0])
        monkeypatch.setattr(client_module, "sleep", fake_sleep)
        await api.get_forecast(latitude=1, longitude=2, units=Units.METRIC)
        clock[0] += 0.25
        await api.get_forecast(latitude=1, longitude=2, units=Units.METRIC)
        clock[0] += 5
        await api.get_forecast(latitude=1, longitude=2, units=Units.METRIC)
        assert sleeps == [pytest.approx(60 / 55 - 0.25)]
