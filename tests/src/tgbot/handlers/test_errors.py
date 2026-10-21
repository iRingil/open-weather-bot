"""
Unit tests for src/tgbot/handlers/errors.py (ErrHandler).

ErrService.log_exception is the only collaborator (patched as an AsyncMock) - it has its own full
test suite in tests/src/tgbot/services/test_errors.py, so this suite only checks that handle()
delegates to it with the right event, not what logging it produces. The ErrorEvent itself is built
as a real aiogram object (a cheap pydantic model, no network calls).
"""

from unittest.mock import AsyncMock

import pytest
from aiogram.types import ErrorEvent, Update

from tgbot.handlers import errors as errors_module
from tgbot.handlers.errors import ErrHandler

__all__: tuple = ()


def _error_event(exception: Exception) -> ErrorEvent:
    """
    Builds a real ErrorEvent wrapping the given exception, with an otherwise-empty update.

    :param exception: The exception that was raised while handling the update.
    :return: A usable ErrorEvent instance.
    """
    return ErrorEvent(update=Update(update_id=1), exception=exception)


@pytest.fixture(name="log_exception")
def log_exception_fixture(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """
    Replaces ErrService.log_exception with an AsyncMock, as seen by tgbot.handlers.errors.

    :param monkeypatch: pytest fixture used to patch tgbot.handlers.errors.ErrService.log_exception.
    :return: The AsyncMock standing in for ErrService.log_exception.
    """
    mock: AsyncMock = AsyncMock(return_value=None)
    monkeypatch.setattr(target=errors_module.ErrService, name="log_exception", value=mock)
    return mock


class TestHandle:
    """Tests ErrHandler.handle(): delegation to ErrService.log_exception."""

    async def test_calls_err_service_log_exception_with_the_event(self, log_exception: AsyncMock) -> None:
        """
        handle() awaits ErrService.log_exception with the handler's own event, unchanged.

        ErrHandler's constructor is typed against BaseHandler[Exception]'s stub, which doesn't
        accept a real ErrorEvent - hence the type: ignore on construction below.

        :param log_exception: Fixture standing in for ErrService.log_exception.
        :return: None
        """
        event: ErrorEvent = _error_event(exception=RuntimeError("boom"))
        handler: ErrHandler = ErrHandler(event=event)  # type: ignore[arg-type]
        await handler.handle()
        log_exception.assert_awaited_once_with(event=event)
