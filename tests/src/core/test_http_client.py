"""
Unit tests for src/core/http_client.py (HttpClient).

aiohttp.ClientSession and aiohttp.TCPConnector are replaced with fakes (see the fake_session
fixture) - never a real socket. The fake session queues one scripted outcome (a response or an
exception) per request() call, letting each test script exactly the sequence HttpClient should
see. asyncio.sleep is also patched to a no-op, so retry backoff doesn't slow the suite down.
"""

import asyncio
from typing import Self

import aiohttp
import pytest

from core.http_client import HttpClient, HttpClientError, HttpMethod

__all__: tuple = ()


class _FakeResponse:
    """A minimal async context manager standing in for aiohttp.ClientResponse."""

    def __init__(self, status: int, body: bytes) -> None:
        """
        Builds a fake response with the given status and raw body.

        :param status: HTTP status code to report.
        :param body: Raw response body that read() returns.
        """
        self.status: int = status
        self.ok: bool = status < 400
        self._body: bytes = body

    async def read(self) -> bytes:
        """
        Returns the body this response was configured with.

        :return: The configured raw body.
        """
        return self._body

    async def __aenter__(self) -> Self:
        """
        Enters the fake response's async context, mirroring aiohttp.ClientResponse.

        :return: Self.
        """
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        """
        Exits the fake response's async context; there is nothing to clean up.

        :param exc_info: Unused exception info from the with-block.
        :return: None
        """


class _FakeSession:
    """A minimal stand-in for aiohttp.ClientSession, queueing one scripted outcome per call."""

    def __init__(self) -> None:
        """Starts open, unrecorded, and with no queued outcomes or construction history."""
        self.closed: bool = False
        self.close_calls: int = 0
        self.calls: list[tuple[HttpMethod, str, dict]] = []
        self.construct_calls: list[dict] = []
        self._outcomes: list[_FakeResponse | BaseException] = []

    def queue(self, *outcomes: "_FakeResponse | BaseException") -> None:
        """
        Schedules the outcomes returned/raised by successive request() calls, in order.

        :param outcomes: A _FakeResponse to return, or an exception instance to raise.
        :return: None
        """
        self._outcomes.extend(outcomes)

    def request(self, method: HttpMethod, url: str, **kwargs: object) -> _FakeResponse:
        """
        Records the call, then returns or raises the next queued outcome.

        :param method: HTTP method passed by HttpClient.
        :param url: Request URL passed by HttpClient.
        :param kwargs: Any extra aiohttp kwargs passed by HttpClient.
        :return: The next queued _FakeResponse.
        """
        self.calls.append((method, url, kwargs))
        outcome: _FakeResponse | BaseException = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    async def close(self) -> None:
        """
        Marks the session closed, mirroring aiohttp.ClientSession.close.

        :return: None
        """
        self.closed = True
        self.close_calls += 1


@pytest.fixture(name="fake_session")
def fake_session_fixture(monkeypatch: pytest.MonkeyPatch) -> _FakeSession:
    """
    Replaces aiohttp.ClientSession/TCPConnector so HttpClient never touches a real socket.

    :param monkeypatch: pytest fixture used to patch aiohttp and asyncio.sleep.
    :return: The _FakeSession instance HttpClient._get_session will construct and reuse.
    """
    session: _FakeSession = _FakeSession()

    def _construct_session(**kwargs: object) -> _FakeSession:
        """
        Stands in for aiohttp.ClientSession(...), recording the kwargs it was constructed with.

        :param kwargs: The connector/timeout kwargs HttpClient._get_session constructs it with.
        :return: The shared, freshly "opened" _FakeSession.
        """
        session.construct_calls.append(kwargs)
        session.closed = False
        return session

    monkeypatch.setattr(target=aiohttp, name="ClientSession", value=_construct_session)
    monkeypatch.setattr(target=aiohttp, name="TCPConnector", value=lambda **_kwargs: object())
    return session


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Replaces asyncio.sleep with a no-op, so retry backoff doesn't slow the test suite down.

    :param monkeypatch: pytest fixture used to patch asyncio.sleep.
    :return: None
    """

    async def _instant_sleep(_delay: float) -> None:
        """
        Stands in for asyncio.sleep(...), returning immediately instead of waiting.

        :param _delay: The backoff delay HttpClient would otherwise have waited out.
        :return: None
        """
        return None

    monkeypatch.setattr(target=asyncio, name="sleep", value=_instant_sleep)


class TestGetSession:
    """Tests for HttpClient's lazy, cached session creation (exercised via get())."""

    async def test_creates_the_session_lazily(self, fake_session: _FakeSession) -> None:
        """
        No session is constructed until the first request is made.

        :param fake_session: The fake aiohttp session fixture.
        :return: None
        """
        client: HttpClient = HttpClient()
        assert fake_session.construct_calls == []
        fake_session.queue(_FakeResponse(status=200, body=b"{}"))
        await client.get(url="http://x")
        assert len(fake_session.construct_calls) == 1

    async def test_reuses_the_session_across_calls(self, fake_session: _FakeSession) -> None:
        """
        A second call reuses the already-open session instead of constructing another.

        :param fake_session: The fake aiohttp session fixture.
        :return: None
        """
        client: HttpClient = HttpClient()
        fake_session.queue(_FakeResponse(status=200, body=b"{}"), _FakeResponse(status=200, body=b"{}"))
        await client.get(url="http://x")
        await client.get(url="http://x")
        assert len(fake_session.construct_calls) == 1

    async def test_recreates_the_session_once_closed(self, fake_session: _FakeSession) -> None:
        """
        A closed session is replaced with a freshly constructed one on the next request.

        :param fake_session: The fake aiohttp session fixture.
        :return: None
        """
        client: HttpClient = HttpClient()
        fake_session.queue(_FakeResponse(status=200, body=b"{}"))
        await client.get(url="http://x")
        fake_session.closed = True
        fake_session.queue(_FakeResponse(status=200, body=b"{}"))
        await client.get(url="http://x")
        assert len(fake_session.construct_calls) == 2

    async def test_passes_total_and_connect_timeouts_to_the_session(self, fake_session: _FakeSession) -> None:
        """
        The constructor's request/connect timeouts land on the session's ClientTimeout.

        :param fake_session: The fake aiohttp session fixture.
        :return: None
        """
        client: HttpClient = HttpClient(request_timeout=30.0, connect_timeout=5.0)
        fake_session.queue(_FakeResponse(status=200, body=b"{}"))
        await client.get(url="http://x")
        timeout: aiohttp.ClientTimeout = fake_session.construct_calls[0]["timeout"]
        assert timeout.total == 30.0
        assert timeout.connect == 5.0


class TestSuccessfulRequests:
    """Tests that a 2xx response is parsed and dispatched with the right HTTP method."""

    async def test_get_returns_parsed_json_on_2xx(self, fake_session: _FakeSession) -> None:
        """
        A 2xx GET response body is parsed as JSON and returned as-is.

        :param fake_session: The fake aiohttp session fixture.
        :return: None
        """
        client: HttpClient = HttpClient()
        fake_session.queue(_FakeResponse(status=200, body=b'{"a": 1}'))
        result: object = await client.get(url="http://x")
        assert result == {"a": 1}

    async def test_get_sends_http_method_get_and_kwargs(self, fake_session: _FakeSession) -> None:
        """
        get() dispatches HttpMethod.GET and forwards extra kwargs untouched.

        :param fake_session: The fake aiohttp session fixture.
        :return: None
        """
        client: HttpClient = HttpClient()
        fake_session.queue(_FakeResponse(status=200, body=b"{}"))
        await client.get(url="http://x", params={"q": "1"})
        method, url, kwargs = fake_session.calls[0]
        assert method == HttpMethod.GET
        assert url == "http://x"
        assert kwargs == {"params": {"q": "1"}}

    async def test_post_sends_http_method_post(self, fake_session: _FakeSession) -> None:
        """
        post() dispatches HttpMethod.POST.

        :param fake_session: The fake aiohttp session fixture.
        :return: None
        """
        client: HttpClient = HttpClient()
        fake_session.queue(_FakeResponse(status=200, body=b"{}"))
        await client.post(url="http://x", data="body")
        method, _url, _kwargs = fake_session.calls[0]
        assert method == HttpMethod.POST


class TestHttpClientErrorOnBadStatus:
    """Tests that a non-2xx response raises HttpClientError with the response details attached."""

    async def test_raises_with_status_url_and_body(self, fake_session: _FakeSession) -> None:
        """
        404 raises HttpClientError carrying the status, URL, and raw body.

        :param fake_session: The fake aiohttp session fixture.
        :return: None
        """
        client: HttpClient = HttpClient()
        fake_session.queue(_FakeResponse(status=404, body=b"not found"))
        with pytest.raises(expected_exception=HttpClientError) as exc_info:
            await client.get(url="http://x/missing")
        error: HttpClientError = exc_info.value
        assert error.status == 404
        assert error.url == "http://x/missing"
        assert error.body == b"not found"
        assert str(error) == "HTTP 404 for http://x/missing"


class TestRetryPolicy:
    """
    Tests HttpClient's retry rules: GET retries transient failures, POST never does.

    A lost POST response could otherwise duplicate an order the exchange already received, so
    only the idempotent GET is safe to retry.
    """

    async def test_get_retries_after_a_dropped_connection_and_succeeds(self, fake_session: _FakeSession) -> None:
        """
        A ClientConnectionError on the first attempt is retried and the second attempt succeeds.

        :param fake_session: The fake aiohttp session fixture.
        :return: None
        """
        client: HttpClient = HttpClient(max_retries=2)
        fake_session.queue(aiohttp.ClientConnectionError("dropped"), _FakeResponse(status=200, body=b'{"ok": true}'))
        result: object = await client.get(url="http://x")
        assert result == {"ok": True}
        assert len(fake_session.calls) == 2

    async def test_get_retries_after_a_timeout_and_succeeds(self, fake_session: _FakeSession) -> None:
        """
        A TimeoutError on the first attempt is retried and the second attempt succeeds.

        :param fake_session: The fake aiohttp session fixture.
        :return: None
        """
        client: HttpClient = HttpClient(max_retries=2)
        fake_session.queue(TimeoutError(), _FakeResponse(status=200, body=b"{}"))
        await client.get(url="http://x")
        assert len(fake_session.calls) == 2

    async def test_get_retries_after_a_5xx_and_succeeds(self, fake_session: _FakeSession) -> None:
        """
        A 503 on the first attempt is retried and the second attempt succeeds.

        :param fake_session: The fake aiohttp session fixture.
        :return: None
        """
        client: HttpClient = HttpClient(max_retries=2)
        fake_session.queue(_FakeResponse(status=503, body=b"unavailable"), _FakeResponse(status=200, body=b"{}"))
        await client.get(url="http://x")
        assert len(fake_session.calls) == 2

    async def test_get_does_not_retry_a_4xx(self, fake_session: _FakeSession) -> None:
        """
        A 404 is not a server error, so it's raised on the first attempt with no retry.

        :param fake_session: The fake aiohttp session fixture.
        :return: None
        """
        client: HttpClient = HttpClient(max_retries=2)
        fake_session.queue(_FakeResponse(status=404, body=b"missing"))
        with pytest.raises(expected_exception=HttpClientError):
            await client.get(url="http://x")
        assert len(fake_session.calls) == 1

    async def test_get_raises_after_exhausting_retries_on_connection_errors(self, fake_session: _FakeSession) -> None:
        """
        Once every retry also fails, the last connection error propagates to the caller.

        :param fake_session: The fake aiohttp session fixture.
        :return: None
        """
        client: HttpClient = HttpClient(max_retries=2)
        fake_session.queue(
            aiohttp.ClientConnectionError("1"),
            aiohttp.ClientConnectionError("2"),
            aiohttp.ClientConnectionError("3"),
        )
        with pytest.raises(expected_exception=aiohttp.ClientConnectionError):
            await client.get(url="http://x")
        assert len(fake_session.calls) == 3

    async def test_get_raises_after_exhausting_retries_on_5xx(self, fake_session: _FakeSession) -> None:
        """
        Once every retry also returns a 5xx, the last HttpClientError propagates to the caller.

        :param fake_session: The fake aiohttp session fixture.
        :return: None
        """
        client: HttpClient = HttpClient(max_retries=1)
        fake_session.queue(_FakeResponse(status=500, body=b"e1"), _FakeResponse(status=502, body=b"e2"))
        with pytest.raises(expected_exception=HttpClientError) as exc_info:
            await client.get(url="http://x")
        assert exc_info.value.status == 502
        assert len(fake_session.calls) == 2

    async def test_post_never_retries_on_connection_error(self, fake_session: _FakeSession) -> None:
        """
        POST raises immediately on a dropped connection, with no retry attempt.

        :param fake_session: The fake aiohttp session fixture.
        :return: None
        """
        client: HttpClient = HttpClient(max_retries=2)
        fake_session.queue(aiohttp.ClientConnectionError("dropped"))
        with pytest.raises(expected_exception=aiohttp.ClientConnectionError):
            await client.post(url="http://x")
        assert len(fake_session.calls) == 1

    async def test_post_never_retries_on_5xx(self, fake_session: _FakeSession) -> None:
        """
        POST raises immediately on a 5xx response, with no retry attempt.

        :param fake_session: The fake aiohttp session fixture.
        :return: None
        """
        client: HttpClient = HttpClient(max_retries=2)
        fake_session.queue(_FakeResponse(status=500, body=b"boom"))
        with pytest.raises(expected_exception=HttpClientError):
            await client.post(url="http://x")
        assert len(fake_session.calls) == 1


class TestClose:
    """Tests for HttpClient.close's idempotent, no-op-when-unused shutdown behavior."""

    async def test_close_is_a_no_op_without_a_session(self, fake_session: _FakeSession) -> None:
        """
        Closing a client that never made a request never constructs or closes a session.

        :param fake_session: The fake aiohttp session fixture.
        :return: None
        """
        client: HttpClient = HttpClient()
        await client.close()
        assert fake_session.construct_calls == []
        assert fake_session.close_calls == 0

    async def test_close_closes_an_open_session(self, fake_session: _FakeSession) -> None:
        """
        Closing a client with an open session closes the underlying aiohttp session.

        :param fake_session: The fake aiohttp session fixture.
        :return: None
        """
        client: HttpClient = HttpClient()
        fake_session.queue(_FakeResponse(status=200, body=b"{}"))
        await client.get(url="http://x")
        await client.close()
        assert fake_session.close_calls == 1

    async def test_close_is_idempotent_on_an_already_closed_session(self, fake_session: _FakeSession) -> None:
        """
        Closing an already-closed client doesn't call close() on the session again.

        :param fake_session: The fake aiohttp session fixture.
        :return: None
        """
        client: HttpClient = HttpClient()
        fake_session.queue(_FakeResponse(status=200, body=b"{}"))
        await client.get(url="http://x")
        await client.close()
        await client.close()
        assert fake_session.close_calls == 1
