"""
Unit tests for src/tgbot/misc/middlewares.py (AntiFloodMiddleware).

The middleware's only real dependency is time.monotonic - replaced here with _FakeClock, a
controllable stand-in tests advance explicitly, the same monkeypatch-a-time-source approach
tests/src/core/test_decorators.py uses for asyncio.sleep. The wrapped handler is a scripted async
spy (_HandlerSpy) rather than a mock, since it has no real external dependency of its own either.
"""

# pylint: disable=protected-access

from typing import Any

import pytest
from aiogram.types import TelegramObject

from tgbot.misc import middlewares
from tgbot.misc.middlewares import AntiFloodMiddleware

__all__: tuple = ()

# A bare TelegramObject stand-in - the middleware never inspects the event itself, only data.
_EVENT: TelegramObject = TelegramObject()


class _FakeClock:
    """A controllable stand-in for time.monotonic, advanced explicitly by tests."""

    def __init__(self, start: float = 0.0) -> None:
        """
        Sets the initial fake time.

        :param start: Time value returned before advance() is ever called.
        """
        self.now: float = start

    def __call__(self) -> float:
        """
        :return: The current fake time.
        """
        return self.now

    def advance(self, delta: float) -> None:
        """
        Moves the fake clock forward.

        :param delta: Seconds to add to the current fake time.
        :return: None
        """
        self.now += delta


class _HandlerSpy:
    """An async callable standing in for the wrapped handler, recording every call and returning a fixed result."""

    def __init__(self, result: Any = "handled") -> None:
        """
        Sets the value every call returns.

        :param result: Value __call__ returns every time it's invoked.
        """
        self._result: Any = result
        self.calls: list[tuple[Any, dict[str, Any]]] = []

    async def __call__(self, event: Any, data: dict[str, Any]) -> Any:
        """
        Records the call, then returns the scripted result.

        :param event: The event the middleware forwarded.
        :param data: The contextual data dict the middleware forwarded.
        :return: The scripted result.
        """
        self.calls.append((event, data))
        return self._result


class SimpleUser:
    """A minimal stand-in for aiogram.types.User - the middleware only ever reads .id off it."""

    # noinspection PyShadowingBuiltins
    def __init__(self, id: int) -> None:  # pylint: disable=redefined-builtin
        """
        :param id: The Telegram user ID the middleware keys its rate limit by.
        """
        self.id: int = id


def _user_data(user_id: int | None) -> dict[str, Any]:
    """
    Builds a data dict as the middleware would receive it from earlier middlewares.

    :param user_id: The value to put in "event_from_user" (only .id is ever read), or None to
        omit the key entirely, simulating an event with no resolvable user.
    :return: A data dict suitable for passing to AntiFloodMiddleware.__call__.
    """
    if user_id is None:
        return {}
    return {"event_from_user": SimpleUser(id=user_id)}


@pytest.fixture(name="clock")
def clock_fixture(monkeypatch: pytest.MonkeyPatch) -> _FakeClock:
    """
    Replaces middlewares.monotonic with a controllable fake clock starting at 0.0.

    :param monkeypatch: pytest fixture used to patch middlewares.monotonic.
    :return: The _FakeClock instance the middleware under test will read time from.
    """
    clock: _FakeClock = _FakeClock()
    monkeypatch.setattr(target=middlewares, name="monotonic", value=clock)
    return clock


@pytest.fixture(name="handler")
def handler_fixture() -> _HandlerSpy:
    """
    A fresh handler spy for each test.

    :return: A _HandlerSpy returning "handled" and recording every call.
    """
    return _HandlerSpy()


@pytest.fixture(name="middleware")
def middleware_fixture() -> AntiFloodMiddleware:
    """
    A fresh AntiFloodMiddleware instance, with its own empty per-user hit history.

    :return: The AntiFloodMiddleware instance under test.
    """
    return AntiFloodMiddleware()


class TestNoResolvableUser:
    """Tests the middleware's behavior when data has no "event_from_user" to key the rate limit by."""

    async def test_calls_the_handler_regardless_of_call_count(
        self, middleware: AntiFloodMiddleware, handler: _HandlerSpy, clock: _FakeClock
    ) -> None:
        """
        Without a user to track, every call is let through unconditionally, even past the normal limit.

        :param middleware: The AntiFloodMiddleware fixture.
        :param handler: The handler spy fixture.
        :param clock: The fake clock fixture (unused directly - no throttling happens at all).
        :return: None
        """
        data: dict[str, Any] = _user_data(user_id=None)
        for _ in range(AntiFloodMiddleware._limit + 5):
            result: Any = await middleware(handler=handler, event=_EVENT, data=data)
            assert result == "handled"
        assert len(handler.calls) == AntiFloodMiddleware._limit + 5


class TestWithinLimit:
    """Tests calls that stay within the configured limit inside the sliding window."""

    async def test_allows_every_call_up_to_the_limit(
        self, middleware: AntiFloodMiddleware, handler: _HandlerSpy
    ) -> None:
        """
        Every call up to and including the limit-th is passed through to the handler.

        :param middleware: The AntiFloodMiddleware fixture.
        :param handler: The handler spy fixture.
        :return: None
        """
        data: dict[str, Any] = _user_data(user_id=1)
        for _ in range(AntiFloodMiddleware._limit):
            result: Any = await middleware(handler=handler, event=_EVENT, data=data)
            assert result == "handled"
        assert len(handler.calls) == AntiFloodMiddleware._limit

    async def test_tracks_separate_users_independently(
        self, middleware: AntiFloodMiddleware, handler: _HandlerSpy
    ) -> None:
        """
        Using up one user's limit doesn't affect a different user's own limit.

        :param middleware: The AntiFloodMiddleware fixture.
        :param handler: The handler spy fixture.
        :return: None
        """
        limit: int = AntiFloodMiddleware._limit
        for _ in range(limit):
            await middleware(handler=handler, event=_EVENT, data=_user_data(user_id=1))
        result: Any = await middleware(handler=handler, event=_EVENT, data=_user_data(user_id=2))
        assert result == "handled"
        assert len(handler.calls) == limit + 1

    async def test_forwards_event_and_data_unchanged(
        self, middleware: AntiFloodMiddleware, handler: _HandlerSpy
    ) -> None:
        """
        The exact event and data objects reach the handler, not copies.

        :param middleware: The AntiFloodMiddleware fixture.
        :param handler: The handler spy fixture.
        :return: None
        """
        event: TelegramObject = TelegramObject()
        data: dict[str, Any] = _user_data(user_id=1)
        await middleware(handler=handler, event=event, data=data)
        called_event, called_data = handler.calls[0]
        assert called_event is event
        assert called_data is data


class TestExceedsLimit:
    """Tests calls that exceed the configured limit inside the sliding window."""

    async def test_drops_the_call_past_the_limit(self, middleware: AntiFloodMiddleware, handler: _HandlerSpy) -> None:
        """
        The call right after the limit is reached is dropped: the handler isn't called and None is returned.

        :param middleware: The AntiFloodMiddleware fixture.
        :param handler: The handler spy fixture.
        :return: None
        """
        data: dict[str, Any] = _user_data(user_id=1)
        limit: int = AntiFloodMiddleware._limit
        for _ in range(limit):
            await middleware(handler=handler, event=_EVENT, data=data)
        result: Any = await middleware(handler=handler, event=_EVENT, data=data)
        assert result is None
        assert len(handler.calls) == limit

    async def test_dropped_calls_dont_count_towards_future_allowance(
        self, middleware: AntiFloodMiddleware, handler: _HandlerSpy
    ) -> None:
        """
        Repeated calls past the limit stay dropped - a dropped call isn't itself recorded as a hit.

        :param middleware: The AntiFloodMiddleware fixture.
        :param handler: The handler spy fixture.
        :return: None
        """
        data: dict[str, Any] = _user_data(user_id=1)
        limit: int = AntiFloodMiddleware._limit
        for _ in range(limit):
            await middleware(handler=handler, event=_EVENT, data=data)
        for _ in range(5):
            result: Any = await middleware(handler=handler, event=_EVENT, data=data)
            assert result is None
        assert len(handler.calls) == limit


class TestSlidingWindowExpiry:
    """Tests that a throttled user is let through again once old hits age out of the window."""

    async def test_still_blocked_exactly_at_the_window_boundary(
        self, middleware: AntiFloodMiddleware, handler: _HandlerSpy, clock: _FakeClock
    ) -> None:
        """
        The oldest hit is only dropped once it's strictly older than the window, not merely as old as it.

        :param middleware: The AntiFloodMiddleware fixture.
        :param handler: The handler spy fixture.
        :param clock: The fake clock fixture, advanced to exactly the window's length.
        :return: None
        """
        data: dict[str, Any] = _user_data(user_id=1)
        limit: int = AntiFloodMiddleware._limit
        period: float = AntiFloodMiddleware._period
        for _ in range(limit):
            await middleware(handler=handler, event=_EVENT, data=data)
        clock.advance(delta=period)
        result: Any = await middleware(handler=handler, event=_EVENT, data=data)
        assert result is None
        assert len(handler.calls) == limit

    async def test_allows_one_more_once_the_oldest_hit_falls_out_of_the_window(
        self, middleware: AntiFloodMiddleware, handler: _HandlerSpy, clock: _FakeClock
    ) -> None:
        """
        Once enough time passes for the oldest recorded hit to age out, a new call is let through again.

        :param middleware: The AntiFloodMiddleware fixture.
        :param handler: The handler spy fixture.
        :param clock: The fake clock fixture, advanced past the window's length.
        :return: None
        """
        data: dict[str, Any] = _user_data(user_id=1)
        limit: int = AntiFloodMiddleware._limit
        period: float = AntiFloodMiddleware._period
        for _ in range(limit):
            await middleware(handler=handler, event=_EVENT, data=data)
        clock.advance(delta=period + 0.001)
        result: Any = await middleware(handler=handler, event=_EVENT, data=data)
        assert result == "handled"
        assert len(handler.calls) == limit + 1

    async def test_immediately_throttled_again_after_the_single_slot_is_used(
        self, middleware: AntiFloodMiddleware, handler: _HandlerSpy, clock: _FakeClock
    ) -> None:
        """
        The slot freed by one aged-out hit only lets a single new call through before throttling resumes.

        Hits are staggered by a tiny step so they age out one at a time, not all together.

        :param middleware: The AntiFloodMiddleware fixture.
        :param handler: The handler spy fixture.
        :param clock: The fake clock fixture, advanced just past the point where only the very
            first hit has aged out of the window.
        :return: None
        """
        data: dict[str, Any] = _user_data(user_id=1)
        limit: int = AntiFloodMiddleware._limit
        period: float = AntiFloodMiddleware._period
        step: float = 0.01
        for i in range(limit):
            clock.now = i * step
            await middleware(handler=handler, event=_EVENT, data=data)
        clock.now = period + step / 2  # only the hit at t=0 is older than the window now
        await middleware(handler=handler, event=_EVENT, data=data)
        result: Any = await middleware(handler=handler, event=_EVENT, data=data)
        assert result is None
        assert len(handler.calls) == limit + 1
