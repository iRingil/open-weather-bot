"""Bare-metal high performance aiohttp client."""

import asyncio
import socket
from enum import StrEnum
from typing import Any

import aiohttp
import orjson

__all__: tuple[str, ...] = ("HttpMethod", "HttpClient", "HttpClientError")


class HttpMethod(StrEnum):
    """Available HTTP methods for HttpClient."""

    GET = "GET"
    POST = "POST"


class HttpClientError(Exception):
    """HTTP request failed with a non-2xx status code."""

    __slots__ = ("status", "url", "body")

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

    __slots__ = ("_pool_limit", "_request_timeout", "_connect_timeout", "_max_retries", "_session")

    _RETRYABLE_METHODS: frozenset[HttpMethod] = frozenset({HttpMethod.GET})

    def __init__(
        self,
        pool_limit: int = 100,
        request_timeout: float | int = 30.0,
        connect_timeout: float | int = 5.0,
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

    async def _request(self, method: HttpMethod, url: str, **kwargs: Any) -> Any:
        """
        Execute a raw HTTP request and return parsed JSON.

        GET retries after a dropped connection, a timeout, or a 5xx response - the VPS this bot
        runs on doesn't always have a stable link, and none of those failures mean the server
        acted on the request. POST never retries here: a lost response to a request the exchange
        did receive could otherwise duplicate an order.

        :param method: HTTP method.
        :param url: Full URL.
        :param kwargs: Arguments passed directly to aiohttp.
        :return: Parsed JSON response.
        """
        retries: int = self._max_retries if method in self._RETRYABLE_METHODS else 0
        for attempt in range(retries + 1):
            try:
                session: aiohttp.ClientSession = await self._get_session()
                async with session.request(method=method, url=url, **kwargs) as response:
                    raw: bytes = await response.read()
                    if not response.ok:
                        raise HttpClientError(status=response.status, url=url, body=raw)
                    return orjson.loads(raw)
            except (aiohttp.ClientConnectionError, asyncio.TimeoutError):
                if attempt == retries:
                    raise
                await asyncio.sleep(0.5 * 2**attempt)
            except HttpClientError as e:
                if e.status < 500 or attempt == retries:
                    raise
                await asyncio.sleep(0.5 * 2**attempt)
        raise AssertionError("unreachable")  # pragma: no cover

    async def get(self, url: str, **kwargs: Any) -> Any:
        """
        Alias for GET request.

        :param url: Full URL.
        :param kwargs: Arguments passed directly to aiohttp.
        :return: Parsed JSON response.
        """
        return await self._request(method=HttpMethod.GET, url=url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> Any:
        """
        Alias for POST request.

        :param url: Full URL.
        :param kwargs: Arguments passed directly to aiohttp.
        :return: Parsed JSON response.
        """
        return await self._request(method=HttpMethod.POST, url=url, **kwargs)
