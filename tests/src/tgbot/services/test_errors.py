"""
Unit tests for src/tgbot/services/errors.py (ErrService).

ErrorEvent/Update/Message/CallbackQuery are built as real aiogram objects (cheap pydantic models,
no network calls) rather than mocks, since log_exception only ever reads plain fields off them.
Log output is asserted via a loguru sink (captured_records), the same pattern
tests/src/core/test_decorators.py established.
"""

from datetime import datetime
from typing import Iterator

import pytest
from aiogram.types import CallbackQuery, Chat, ErrorEvent, Message, Update, User
from loguru import logger

from tgbot.services.errors import ErrService

__all__: tuple = ()


def _message(text: str) -> Message:
    """
    Builds a real Message with the given text.

    :param text: Text the message carries.
    :return: A usable Message instance.
    """
    return Message(message_id=1, date=datetime.now(), chat=Chat(id=1, type="private"), text=text)


def _callback_query(data: str) -> CallbackQuery:
    """
    Builds a real CallbackQuery with the given callback data.

    :param data: Callback data the query carries.
    :return: A usable CallbackQuery instance.
    """
    return CallbackQuery(id="1", from_user=User(id=1, is_bot=False, first_name="Test"), chat_instance="x", data=data)


def _error_event(
    exception: Exception, message: Message | None = None, callback_query: CallbackQuery | None = None
) -> ErrorEvent:
    """
    Builds a real ErrorEvent wrapping the given exception and update contents.

    :param exception: The exception that was raised while handling the update.
    :param message: The update's message, or None if it carried no message.
    :param callback_query: The update's callback query, or None if it carried no callback query.
    :return: A usable ErrorEvent instance.
    """
    update: Update = Update(update_id=1, message=message, callback_query=callback_query)
    return ErrorEvent(update=update, exception=exception)


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


class TestLogException:
    """Tests ErrService.log_exception: what gets logged for each kind of update."""

    async def test_logs_the_exception_and_message_text_for_an_update_with_a_message(
        self, captured_records: list
    ) -> None:
        """
        An update carrying a Message logs the exception plus the message's own text.

        :param captured_records: Fixture capturing every record loguru receives.
        :return: None
        """
        event: ErrorEvent = _error_event(exception=RuntimeError("boom"), message=_message(text="hello"))
        await ErrService.log_exception(event=event)
        assert len(captured_records) == 1
        record: dict = captured_records[0]
        assert record["level"].name == "ERROR"
        assert "boom" in record["message"]
        assert ", Message: hello" in record["message"]

    async def test_logs_the_exception_and_callback_data_for_an_update_with_no_message(
        self, captured_records: list
    ) -> None:
        """
        An update with no message but a callback query logs the exception plus the callback's data.

        :param captured_records: Fixture capturing every record loguru receives.
        :return: None
        """
        event: ErrorEvent = _error_event(exception=RuntimeError("boom"), callback_query=_callback_query(data="page_2"))
        await ErrService.log_exception(event=event)
        assert ", Callback: page_2" in captured_records[0]["message"]

    async def test_logs_the_exception_alone_for_an_update_with_neither(self, captured_records: list) -> None:
        """
        An update with neither a message nor a callback query logs just the bare exception.

        :param captured_records: Fixture capturing every record loguru receives.
        :return: None
        """
        event: ErrorEvent = _error_event(exception=RuntimeError("boom"))
        await ErrService.log_exception(event=event)
        record: dict = captured_records[0]
        assert "boom" in record["message"]
        assert ", Message:" not in record["message"]
        assert ", Callback:" not in record["message"]

    async def test_prefers_the_message_branch_when_an_update_somehow_carries_both(self, captured_records: list) -> None:
        """
        A Message takes priority over a callback query when (unrealistically) an update carries both.

        :param captured_records: Fixture capturing every record loguru receives.
        :return: None
        """
        event: ErrorEvent = _error_event(
            exception=RuntimeError("boom"),
            message=_message(text="hello"),
            callback_query=_callback_query(data="page_2"),
        )
        await ErrService.log_exception(event=event)
        record: dict = captured_records[0]
        assert ", Message: hello" in record["message"]
        assert ", Callback:" not in record["message"]
