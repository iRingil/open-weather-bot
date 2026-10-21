"""
Unit tests for src/tgbot/handlers/main.py (MainHandler._register_handlers).

Routing is checked by driving a real aiogram Bot/Dispatcher via Dispatcher.feed_update (Bot.__call__
mocked, no network) rather than by inspecting the router's handler list. Every service class is
replaced at module level with a shared autospecced instance, so each scenario asserts exactly
which service method fired - and which did not.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, create_autospec

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import CallbackQuery, Chat, Location, Message, Update, User

import tgbot.handlers.main as main_module
from core.db.data_types import Units
from core.db.repository import Database
from core.tg_templater import TgTemplater
from tgbot.handlers.main import MainHandler
from tgbot.misc.data_types import CityCallback, UnitsCallback
from tgbot.misc.fsm_states import WeatherSetupStates
from tgbot.misc.keyboards import KeyboardManager
from tgbot.services.admin import AdminService
from tgbot.services.commands import CommandsService
from tgbot.services.dialog import DialogService
from weather.client import WeatherAPI
from weather.reporter import WeatherReporter

__all__: tuple = ()

_BOT_TOKEN: str = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
_ADMIN_ID: int = 111
_USER_ID: int = 222


@pytest.fixture(name="real_bot")
def real_bot_fixture(monkeypatch: pytest.MonkeyPatch) -> Bot:
    """
    A real Bot instance with __call__ monkeypatched, so call.answer() inside the real handlers
    resolves without ever hitting Telegram's API.

    :param monkeypatch: pytest's monkeypatch fixture.
    :return: The Bot instance.
    """
    monkeypatch.setattr(target=Bot, name="__call__", value=AsyncMock(return_value=True))
    return Bot(token=_BOT_TOKEN)


@pytest.fixture(name="services")
def services_fixture(monkeypatch: pytest.MonkeyPatch) -> dict[str, MagicMock]:
    """
    Replaces the service classes at module level with factories each returning one shared
    autospecced instance.

    :param monkeypatch: pytest's monkeypatch fixture.
    :return: The mocked service instances, keyed by class name.
    """
    mocks: dict[str, MagicMock] = {}
    for name, real_cls in (
        ("AdminService", AdminService),
        ("CommandsService", CommandsService),
        ("DialogService", DialogService),
    ):
        instance: MagicMock = create_autospec(spec=real_cls, instance=True)
        monkeypatch.setattr(target=main_module, name=name, value=MagicMock(return_value=instance))
        mocks[name] = instance
    return mocks


@pytest.fixture(name="dp")
def dp_fixture(services: dict[str, MagicMock]) -> Dispatcher:
    """
    A real Dispatcher (MemoryStorage FSM) with a fully-wired MainHandler, admins=[_ADMIN_ID].

    :param services: The mocked service instances (patched in before MainHandler builds them).
    :return: The Dispatcher.
    """
    assert services
    dispatcher: Dispatcher = Dispatcher()
    config: MagicMock = MagicMock()
    config.admins = [_ADMIN_ID]
    MainHandler(
        config=config,
        dp=dispatcher,
        tmpl=create_autospec(spec=TgTemplater, instance=True),
        kb=create_autospec(spec=KeyboardManager, instance=True),
        db=create_autospec(spec=Database, instance=True),
        api=create_autospec(spec=WeatherAPI, instance=True),
        reporter=create_autospec(spec=WeatherReporter, instance=True),
    )
    return dispatcher


def _user(user_id: int) -> User:
    """
    Builds a Telegram user.

    :param user_id: User ID.
    :return: The User.
    """
    return User(id=user_id, is_bot=False, first_name="Test")


def _message(
    user_id: int = _USER_ID, text: str | None = None, location: Location | None = None, chat_type: str = "private"
) -> Message:
    """
    Builds a real, minimal Message.

    :param user_id: Sender's user ID (also the chat ID).
    :param text: Message text.
    :param location: Attached location.
    :param chat_type: Chat type.
    :return: The Message.
    """
    return Message(
        message_id=1,
        date=datetime.now(tz=timezone.utc),
        chat=Chat(id=user_id, type=chat_type),
        from_user=_user(user_id),
        text=text,
        location=location,
    )


async def _set_state(dp: Dispatcher, bot: Bot, state: State) -> None:
    """
    Sets the FSM state of _USER_ID through the dispatcher's own storage.

    :param dp: The Dispatcher.
    :param bot: The Bot.
    :param state: The state to set.
    :return: None
    """
    key: StorageKey = StorageKey(bot_id=bot.id, chat_id=_USER_ID, user_id=_USER_ID)
    await FSMContext(storage=dp.storage, key=key).set_state(state)


async def _feed_message(dp: Dispatcher, bot: Bot, message: Message) -> None:
    """
    Feeds one Message through the Dispatcher.

    :param dp: The Dispatcher.
    :param bot: The Bot.
    :param message: The message.
    :return: None
    """
    await dp.feed_update(bot=bot, update=Update(update_id=1, message=message))


async def _feed_call(dp: Dispatcher, bot: Bot, data: str) -> None:
    """
    Feeds one CallbackQuery from _USER_ID through the Dispatcher.

    :param dp: The Dispatcher.
    :param bot: The Bot.
    :param data: Callback data.
    :return: None
    """
    call: CallbackQuery = CallbackQuery(
        id="1", from_user=_user(_USER_ID), chat_instance="x", data=data, message=_message(text="dialog")
    )
    await dp.feed_update(bot=bot, update=Update(update_id=1, callback_query=call))


class TestCommands:
    """Commands route to their services in any state."""

    @pytest.mark.parametrize(
        ("text", "service", "method"),
        [
            ("/start", "DialogService", "start"),
            ("/about", "CommandsService", "about"),
            ("/stop", "CommandsService", "stop"),
        ],
    )
    async def test_commands_win_over_city_input(
        self, dp: Dispatcher, real_bot: Bot, services: dict[str, MagicMock], text: str, service: str, method: str
    ) -> None:
        """
        A command sent while the bot waits for a city runs the command, not a city search.

        :param dp: The Dispatcher.
        :param real_bot: The Bot.
        :param services: The mocked services.
        :param text: The command.
        :param service: The service expected to handle it.
        :param method: The service method expected to run.
        :return: None
        """
        await _set_state(dp=dp, bot=real_bot, state=WeatherSetupStates.wait_for_city)
        await _feed_message(dp=dp, bot=real_bot, message=_message(text=text))
        getattr(services[service], method).assert_awaited_once()
        services["DialogService"].process_city.assert_not_awaited()

    async def test_stats_for_admin_only(self, dp: Dispatcher, real_bot: Bot, services: dict[str, MagicMock]) -> None:
        """
        /stats reaches the admin service for an admin; anyone else's /stats is just deleted.

        :param dp: The Dispatcher.
        :param real_bot: The Bot.
        :param services: The mocked services.
        :return: None
        """
        await _feed_message(dp=dp, bot=real_bot, message=_message(user_id=_ADMIN_ID, text="/stats"))
        services["AdminService"].stats.assert_awaited_once()
        await _feed_message(dp=dp, bot=real_bot, message=_message(text="/stats"))
        assert services["AdminService"].stats.await_count == 1
        services["DialogService"].delete_any.assert_awaited_once()


class TestDialog:
    """The setup dialog routes by state and callback data."""

    @pytest.mark.parametrize(
        "message", [_message(text="Kyiv"), _message(location=Location(latitude=1.0, longitude=2.0))]
    )
    async def test_city_input_in_wait_for_city(
        self, dp: Dispatcher, real_bot: Bot, services: dict[str, MagicMock], message: Message
    ) -> None:
        """
        A city name or a location is processed while the bot waits for a city.

        :param dp: The Dispatcher.
        :param real_bot: The Bot.
        :param services: The mocked services.
        :param message: The incoming message.
        :return: None
        """
        await _set_state(dp=dp, bot=real_bot, state=WeatherSetupStates.wait_for_city)
        await _feed_message(dp=dp, bot=real_bot, message=message)
        services["DialogService"].process_city.assert_awaited_once()

    @pytest.mark.parametrize("state", [None, WeatherSetupStates.wait_for_city_choice])
    async def test_text_outside_wait_for_city_is_deleted(
        self, dp: Dispatcher, real_bot: Bot, services: dict[str, MagicMock], state: State | None
    ) -> None:
        """
        Text outside the city input step (e.g. while a search runs) is just deleted.

        :param dp: The Dispatcher.
        :param real_bot: The Bot.
        :param services: The mocked services.
        :param state: The FSM state.
        :return: None
        """
        if state is not None:
            await _set_state(dp=dp, bot=real_bot, state=state)
        await _feed_message(dp=dp, bot=real_bot, message=_message(text="Kyiv"))
        services["DialogService"].process_city.assert_not_awaited()
        services["DialogService"].delete_any.assert_awaited_once()

    async def test_group_messages_are_ignored(
        self, dp: Dispatcher, real_bot: Bot, services: dict[str, MagicMock]
    ) -> None:
        """
        Messages outside private chats reach no handler.

        :param dp: The Dispatcher.
        :param real_bot: The Bot.
        :param services: The mocked services.
        :return: None
        """
        await _feed_message(dp=dp, bot=real_bot, message=_message(text="/start", chat_type="group"))
        services["DialogService"].start.assert_not_awaited()
        services["DialogService"].delete_any.assert_not_awaited()

    @pytest.mark.parametrize(
        ("data", "method"),
        [
            ("another_city", "select_another_city"),
            (CityCallback(index=0).pack(), "select_city"),
            (UnitsCallback(units=Units.METRIC).pack(), "select_units"),
        ],
    )
    async def test_buttons_work_in_any_state(
        self, dp: Dispatcher, real_bot: Bot, services: dict[str, MagicMock], data: str, method: str
    ) -> None:
        """
        Dialog buttons route by callback data regardless of the FSM state.

        :param dp: The Dispatcher.
        :param real_bot: The Bot.
        :param services: The mocked services.
        :param data: Callback data.
        :param method: The DialogService method expected to run.
        :return: None
        """
        await _feed_call(dp=dp, bot=real_bot, data=data)
        getattr(services["DialogService"], method).assert_awaited_once()
