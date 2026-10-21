"""
Unit tests for src/tgbot/services/commands.py (CommandsService).

Bot, Database, TgTemplater and KeyboardManager are autospecced mocks (see ../conftest.py);
asyncio.sleep is patched out so the temporary messages don't slow the suite down.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from tests.src.tgbot.helpers import USER_ID, make_message
from tgbot.misc.fsm_states import WeatherSetupStates
from tgbot.services.commands import CommandsService

__all__: tuple = ()


@pytest.fixture(name="service")
def service_fixture(config: MagicMock, tmpl: MagicMock, kb: MagicMock, db: MagicMock) -> CommandsService:
    """
    A CommandsService over the mocked dependencies.

    :param config: The mocked Config.
    :param tmpl: The mocked TgTemplater.
    :param kb: The mocked KeyboardManager.
    :param db: The mocked Database.
    :return: The CommandsService under test.
    """
    return CommandsService(config=config, tmpl=tmpl, kb=kb, db=db)


class TestAbout:
    """Tests CommandsService.about."""

    async def test_shows_info_for_a_while(self, service: CommandsService, bot: MagicMock) -> None:
        """
        The command is deleted, the bot info is sent and deleted after 15 seconds.

        :param service: The CommandsService under test.
        :param bot: The mocked Bot.
        :return: None
        """
        with patch("tgbot.services.common.sleep", new=AsyncMock()) as fake_sleep:
            await service.about(message=make_message(message_id=7, text="/about", bot=bot))
        assert bot.send_photo.await_args.kwargs["caption"] == "msg_about.jinja2|ru|{}"
        fake_sleep.assert_awaited_once_with(15)
        assert [c.kwargs["message_id"] for c in bot.delete_message.await_args_list] == [7, 100]


class TestStop:
    """Tests CommandsService.stop."""

    async def test_deletes_everything(self, service: CommandsService, bot: MagicMock, db: MagicMock) -> None:
        """
        The state is cleared, the command and the dialog message deleted, the user's row removed,
        and a "data deleted" notice is shown for 5 seconds.

        :param service: The CommandsService under test.
        :param bot: The mocked Bot.
        :param db: The mocked Database.
        :return: None
        """
        state: FSMContext = FSMContext(
            storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=USER_ID, user_id=USER_ID)
        )
        await state.set_state(WeatherSetupStates.wait_for_city)
        with patch("tgbot.services.common.sleep", new=AsyncMock()) as fake_sleep:
            await service.stop(message=make_message(message_id=7, text="/stop", bot=bot), state=state)
        assert await state.get_state() is None
        db.delete_user.assert_awaited_once_with(user_id=USER_ID)
        assert bot.send_photo.await_args.kwargs["caption"] == "msg_data_deleted.jinja2|ru|{}"
        fake_sleep.assert_awaited_once_with(5)
        assert [c.kwargs["message_id"] for c in bot.delete_message.await_args_list] == [7, 50, 100]
