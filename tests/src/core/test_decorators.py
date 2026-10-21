"""
Unit tests for src/core/decorators.py (handle_exc).

handle_exc wraps a scripted async callable rather than a mock - it has
no real external dependency of its own, so there's nothing here that qualifies for mocking under
this suite's usual "mock only at genuine boundaries" rule.
"""

import asyncio
from typing import Any, Callable, Iterator

import pytest
from loguru import logger

from core.decorators import handle_exc

__all__: tuple = ()


class _ScriptedCalls:
    """An async callable that returns/raises one scripted outcome per call, in order, recording every call's args."""

    def __init__(self, *outcomes: Any, name: str = "_scripted") -> None:
        """
        Schedules the outcomes returned/raised by successive calls, in order.

        :param outcomes: A value to return, or an exception instance to raise, one per call.
        :param name: Value exposed as __name__, mirroring a real function - handle_exc logs it.
        """
        self._outcomes: list[Any] = list(outcomes)
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.__name__: str = name

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """
        Records the call, then returns or raises the next scripted outcome.

        :param args: Positional arguments the caller passed.
        :param kwargs: Keyword arguments the caller passed.
        :return: The next scripted outcome.
        """
        self.calls.append((args, kwargs))
        outcome: Any = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


@pytest.fixture(name="captured_records")
def captured_records_fixture() -> Iterator[list]:
    """
    Adds a loguru sink that records every emitted record's structured data, regardless of level.

    :return: The list every record loguru receives while this fixture is active gets appended to.
    """
    records: list = []
    sink_id: int = logger.add(sink=lambda message: records.append(message.record), level=0)
    yield records
    logger.remove(sink_id)


class TestHandleExcSuccess:
    """Tests handle_exc's pass-through behavior when the wrapped function succeeds."""

    async def test_returns_the_wrapped_functions_result(self) -> None:
        """
        A successful call's return value passes through unchanged.

        :return: None
        """
        wrapped: Callable[..., Any] = handle_exc(func=_ScriptedCalls(123))
        result: Any = await wrapped()
        assert result == 123

    async def test_passes_positional_and_keyword_arguments_through_unchanged(self) -> None:
        """
        Every positional and keyword argument reaches the wrapped function untouched.

        :return: None
        """
        spy: _ScriptedCalls = _ScriptedCalls(None)
        wrapped: Callable[..., Any] = handle_exc(func=spy)
        await wrapped(1, "x", flag=True)
        assert spy.calls == [((1, "x"), {"flag": True})]


class TestHandleExcException:
    """Tests handle_exc's generic Exception branch: swallowing, return value, and logging."""

    async def test_returns_none_instead_of_raising(self) -> None:
        """
        A raised exception is swallowed - the call returns None instead of propagating it.

        :return: None
        """
        wrapped: Callable[..., Any] = handle_exc(func=_ScriptedCalls(RuntimeError("boom")))
        result: Any = await wrapped()
        assert result is None

    async def test_logs_the_exception_with_the_functions_name_via_logger_exception(
        self, captured_records: list
    ) -> None:
        """
        The failure is logged at ERROR level, naming the wrapped function and the exception, with a traceback
        attached - via loguru's logger.exception, not a hand-built one.

        :param captured_records: Fixture capturing every record loguru receives.
        :return: None
        """
        spy: _ScriptedCalls = _ScriptedCalls(RuntimeError("boom"), name="_my_task")
        wrapped: Callable[..., Any] = handle_exc(func=spy)
        await wrapped()
        assert len(captured_records) == 1
        record: dict = captured_records[0]
        assert record["level"].name == "ERROR"
        assert "_my_task" in record["message"]
        assert "boom" in record["message"]
        assert record["exception"] is not None


class TestHandleExcCancellation:
    """Tests that handle_exc lets task cancellation propagate untouched, instead of swallowing it as a generic error."""

    async def test_propagates_cancelled_error_without_catching_or_logging_it(self, captured_records: list) -> None:
        """
        CancelledError is a BaseException, not an Exception, so it isn't caught by handle_exc's except Exception
        clause - it passes straight through unhandled and unlogged, letting a canceled task actually finish
        canceled instead of appearing to complete normally.

        :param captured_records: Fixture capturing every record loguru receives.
        :return: None
        """
        wrapped: Callable[..., Any] = handle_exc(func=_ScriptedCalls(asyncio.CancelledError()))
        with pytest.raises(expected_exception=asyncio.CancelledError):
            await wrapped()
        assert captured_records == []


class TestPreservesFunctionMetadata:
    """Tests that handle_exc preserves the wrapped function's identity via functools.wraps."""

    async def test_handle_exc_preserves_the_wrapped_functions_name(self) -> None:
        """
        The decorated function's __name__ matches the original, not "wrapper".

        :return: None
        """

        @handle_exc
        async def _my_task() -> None:
            """
            Stands in for a real task function, for a functools.wraps name check only.

            :return: None
            """
            return None

        assert _my_task.__name__ == "_my_task"
