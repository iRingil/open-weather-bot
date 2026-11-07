"""Bare-metal high performance aiohttp client."""

import asyncio
import socket
from collections.abc import Mapping
from enum import StrEnum
from http import HTTPStatus
from typing import cast

import aiohttp
import orjson

__all__: tuple[str, ...] = ("HttpClient", "HttpClientError", "HttpMethod", "JsonValue", "QueryParams")

type JsonValue = dict[str, JsonValue] | list[JsonValue] | str | int | float | bool | None
type QueryParams = Mapping[str, str | int | float]


class HttpMethod(StrEnum):
    """Available HTTP methods for HttpClient."""

    GET = "GET"
    POST = "POST"


class HttpClientError(Exception):
    """HTTP request failed with a non-2xx status code."""

    __slots__: tuple[str, ...] = ("body", "status", "url")

    def __init__(self, status: int, url: str, body: bytes) -> None:
        """
        Initialize the error with response details.

        :param status: HTTP status code.
        :param url: Requested URL.
        :param body: Raw response body.
        """
        self.status: int = status
        self.url: str = url
        self.body: bytes = body
        super().__init__(f"HTTP {status} for {url}")


class HttpClient:
    """High-performance wrapper around aiohttp.ClientSession with lazy initialization."""

    __slots__: tuple[str, ...] = ("_connect_timeout", "_max_retries", "_pool_limit", "_request_timeout", "_session")

    _RETRYABLE_METHODS: frozenset[HttpMethod] = frozenset({HttpMethod.GET})

    def __init__(
        self,
        pool_limit: int = 100,
        request_timeout: float = 30.0,
        connect_timeout: float = 5.0,
        max_retries: int = 2,
    ) -> None:
        """
        Initialize the client settings.

        :param pool_limit: TCP connection pool size.
        :param request_timeout: Total request timeout.
        :param connect_timeout: Timeout for establishing the TCP connection.
        :param max_retries: Retries for GET, on a dropped connection, timeout, or 5xx response.
        """
        self._pool_limit: int = pool_limit
        self._request_timeout: float | int = request_timeout
        self._connect_timeout: float | int = connect_timeout
        self._max_retries: int = max_retries
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """
        Get or create the aiohttp.ClientSession within the current event loop.

        :return: Active aiohttp.ClientSession instance.
        """
        existing: aiohttp.ClientSession | None = self._session
        if existing is not None and not existing.closed:
            return existing
        connector: aiohttp.TCPConnector = aiohttp.TCPConnector(
            limit=self._pool_limit, ttl_dns_cache=300, family=socket.AF_INET, enable_cleanup_closed=True
        )
        timeout: aiohttp.ClientTimeout = aiohttp.ClientTimeout(
            total=self._request_timeout, connect=self._connect_timeout
        )
        new_session: aiohttp.ClientSession = aiohttp.ClientSession(connector=connector, timeout=timeout)
        self._session = new_session
        return new_session

    async def close(self) -> None:
        """
        Close the underlying session if it exists.

        :return: None
        """
        if self._session is not None and not self._session.closed:
            await self._session.close()

    async def _send(
        self,
        method: HttpMethod,
        url: str,
        *,
        params: QueryParams | None,
        json: JsonValue,
        data: str | bytes | None,
    ) -> JsonValue:
        """
        Sends one HTTP request and parses its JSON response.

        :param method: HTTP method.
        :param url: Full URL.
        :param params: Query string parameters.
        :param json: JSON request body.
        :param data: Raw request body.
        :return: Parsed JSON response.
        :raise HttpClientError: if the response status is not 2xx.
        """
        session: aiohttp.ClientSession = await self._get_session()
        async with session.request(method=method, url=url, params=params, json=json, data=data) as response:
            raw: bytes = await response.read()
            if not response.ok:
                raise HttpClientError(status=response.status, url=url, body=raw)
            parsed: JsonValue = cast("JsonValue", orjson.loads(raw))
            return parsed

    async def _request(
        self,
        method: HttpMethod,
        url: str,
        *,
        params: QueryParams | None = None,
        json: JsonValue = None,
        data: str | bytes | None = None,
    ) -> JsonValue:
        """
        Execute a raw HTTP request and return parsed JSON.

        GET retries after a dropped connection, a timeout, or a 5xx response - the VPS this bot
        runs on doesn't always have a stable link, and none of those failures mean the server
        acted on the request. POST never retries here: a lost response to a request the exchange
        did receive could otherwise duplicate an order.

        :param method: HTTP method.
        :param url: Full URL.
        :param params: Query string parameters.
        :param json: JSON request body.
        :param data: Raw request body.
        :return: Parsed JSON response.
        """
        retries: int = self._max_retries if method in self._RETRYABLE_METHODS else 0
        for attempt in range(retries + 1):
            try:
                return await self._send(method=method, url=url, params=params, json=json, data=data)
            except (TimeoutError, aiohttp.ClientConnectionError):
                if attempt == retries:
                    raise
                await asyncio.sleep(0.5 * 2.0**attempt)
            except HttpClientError as e:
                if e.status < HTTPStatus.INTERNAL_SERVER_ERROR or attempt == retries:
                    raise
                await asyncio.sleep(0.5 * 2.0**attempt)
        raise AssertionError("unreachable")  # pragma: no cover

    async def get(self, url: str, params: QueryParams | None = None) -> JsonValue:
        """
        Alias for GET request.

        :param url: Full URL.
        :param params: Query string parameters.
        :return: Parsed JSON response.
        """
        return await self._request(method=HttpMethod.GET, url=url, params=params)

    async def post(self, url: str, json: JsonValue = None, data: str | bytes | None = None) -> JsonValue:
        """
        Alias for POST request.

        :param url: Full URL.
        :param json: JSON request body.
        :param data: Raw request body.
        :return: Parsed JSON response.
        """
        return await self._request(method=HttpMethod.POST, url=url, json=json, data=data)
