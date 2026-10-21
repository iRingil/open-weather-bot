"""
Unit tests for src/tgbot/handlers/{dialog,commands,admin}.py.

The handlers are thin: each test checks the handler forwards its arguments to the matching
(autospecced) service method, and that callback handlers answer the callback query first so the
button's spinner stops even if the service takes a while.
"""

from unittest.mock import AsyncMock, MagicMock, create_autospec

import pytest

from core.db.data_types import Units
from tgbot.handlers.admin import AdminHandler
from tgbot.handlers.commands import CommandsHandler
from tgbot.handlers.dialog import DialogHandler
from tgbot.misc.data_types import CityCallback, UnitsCallback
from tgbot.services.admin import AdminService
from tgbot.services.commands import CommandsService
from tgbot.services.dialog import DialogService

from ..helpers import make_call, make_message

__all__: tuple = ()


@pytest.fixture(name="dialog_service")
def dialog_service_fixture() -> MagicMock:
    """
    An autospecced DialogService.

    :return: The mocked DialogService.
    """
    mock: MagicMock = create_autospec(spec=DialogService, instance=True)
    return mock


@pytest.fixture(name="call_bot")
def call_bot_fixture() -> AsyncMock:
    """
    A Bot stand-in whose __call__ (how aiogram sends every API method) is an AsyncMock.

    :return: The awaitable Bot stand-in.
    """
    return AsyncMock(return_value=True)


class TestDialogHandler:
    """Tests DialogHandler."""

    async def test_message_handlers(self, dialog_service: MagicMock) -> None:
        """
        cmd_start, msg_city and any_delete delegate to the service unchanged.

        :param dialog_service: The mocked DialogService.
        :return: None
        """
        handler: DialogHandler = DialogHandler(service=dialog_service)
        message = make_message(text="Kyiv")
        state: MagicMock = MagicMock()
        await handler.cmd_start(message=message, state=state)
        dialog_service.start.assert_awaited_once_with(message=message, state=state)
        await handler.msg_city(message=message, state=state)
        dialog_service.process_city.assert_awaited_once_with(message=message, state=state)
        await handler.any_delete(message=message)
        dialog_service.delete_any.assert_awaited_once_with(message=message)

    async def test_callback_handlers_answer_then_delegate(self, dialog_service: MagicMock, call_bot: AsyncMock) -> None:
        """
        Every callback handler answers the query, then delegates with the parsed callback data.

        :param dialog_service: The mocked DialogService.
        :param call_bot: The mocked Bot.
        :return: None
        """
        handler: DialogHandler = DialogHandler(service=dialog_service)
        call = make_call(bot=call_bot)
        state: MagicMock = MagicMock()
        city_data: CityCallback = CityCallback(index=2)
        units_data: UnitsCallback = UnitsCallback(units=Units.IMPERIAL)
        await handler.call_another_city(call=call, state=state)
        dialog_service.select_another_city.assert_awaited_once_with(call=call, state=state)
        await handler.call_city(call=call, callback_data=city_data, state=state)
        dialog_service.select_city.assert_awaited_once_with(call=call, callback_data=city_data, state=state)
        await handler.call_units(call=call, callback_data=units_data, state=state)
        dialog_service.select_units.assert_awaited_once_with(call=call, callback_data=units_data, state=state)
        assert call_bot.call_count == 3  # One AnswerCallbackQuery per press, sent through Bot.__call__


class TestCommandsHandler:
    """Tests CommandsHandler."""

    async def test_delegates(self) -> None:
        """
        cmd_about and cmd_stop delegate to the service unchanged.

        :return: None
        """
        service: MagicMock = create_autospec(spec=CommandsService, instance=True)
        handler: CommandsHandler = CommandsHandler(service=service)
        message = make_message(text="/about")
        state: MagicMock = MagicMock()
        await handler.cmd_about(message=message)
        service.about.assert_awaited_once_with(message=message)
        await handler.cmd_stop(message=message, state=state)
        service.stop.assert_awaited_once_with(message=message, state=state)


class TestAdminHandler:
    """Tests AdminHandler."""

    async def test_delegates(self) -> None:
        """
        cmd_stats delegates to the service unchanged.

        :return: None
        """
        service: MagicMock = create_autospec(spec=AdminService, instance=True)
        message = make_message(text="/stats")
        await AdminHandler(service=service).cmd_stats(message=message)
        service.stats.assert_awaited_once_with(message=message)
