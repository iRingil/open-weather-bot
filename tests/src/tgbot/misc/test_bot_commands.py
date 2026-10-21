"""
Unit tests for src/tgbot/misc/bot_commands.py (BotCommands).

Bot and TgTemplater are autospecced mocks - no request ever reaches Telegram. The templater's
render() returns "<template>|<locale>", so every assertion shows which template was rendered in
which locale.
"""

from unittest.mock import AsyncMock, MagicMock, create_autospec

import pytest
from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeAllGroupChats, BotCommandScopeAllPrivateChats, BotCommandScopeChat

from core.tg_templater import TgTemplater
from tgbot.misc.bot_commands import BotCommands

__all__: tuple = ()

# pylint: disable=protected-access


async def _render(tmpl: str, locale: str) -> str:
    """
    Fake TgTemplater.render: encodes the template and locale into the result.

    :param tmpl: Template path.
    :param locale: Locale.
    :return: "<template file name>|<locale>".
    """
    return f"{tmpl.rsplit('/', 1)[-1]}|{locale}"


@pytest.fixture(name="bot")
def bot_fixture() -> MagicMock:
    """
    An autospecced Bot with set_my_commands as an AsyncMock.

    :return: The mocked Bot.
    """
    mock: MagicMock = create_autospec(spec=Bot, instance=True)
    mock.set_my_commands = AsyncMock(return_value=True)
    return mock


@pytest.fixture(name="tmpl")
def tmpl_fixture() -> MagicMock:
    """
    An autospecced TgTemplater rendering "<template>|<locale>", with locales ru and uk.

    :return: The mocked TgTemplater.
    """
    mock: MagicMock = create_autospec(spec=TgTemplater, instance=True)
    mock.render = AsyncMock(side_effect=_render)
    mock.get_locales = MagicMock(return_value=["ru", "uk"])
    return mock


class TestGetCommands:
    """Tests BotCommands._get_commands / _get_admins_commands."""

    async def test_user_commands(self, bot: MagicMock, tmpl: MagicMock) -> None:
        """
        The user commands are start, about and stop, with descriptions rendered in the locale.

        :param bot: The mocked Bot.
        :param tmpl: The mocked TgTemplater.
        :return: None
        """
        commands: list[BotCommand] = await BotCommands(bot=bot, tmpl_render=tmpl, admin_ids=[])._get_commands("ru")
        assert commands == [
            BotCommand(command="start", description="cmd_start.jinja2|ru"),
            BotCommand(command="about", description="cmd_about.jinja2|ru"),
            BotCommand(command="stop", description="cmd_stop.jinja2|ru"),
        ]

    async def test_admin_commands(self, bot: MagicMock, tmpl: MagicMock) -> None:
        """
        The only admin command is stats.

        :param bot: The mocked Bot.
        :param tmpl: The mocked TgTemplater.
        :return: None
        """
        bot_commands: BotCommands = BotCommands(bot=bot, tmpl_render=tmpl, admin_ids=[])
        assert await bot_commands._get_admins_commands("uk") == [
            BotCommand(command="stats", description="cmd_stats.jinja2|uk")
        ]


class TestSetCommands:
    """Tests BotCommands.set_commands."""

    async def test_call_sequence(self, bot: MagicMock, tmpl: MagicMock) -> None:
        """
        Clears group and private commands, sets the English defaults (no language_code), then each
        locale - every time for all private chats and for each admin's chat with stats appended.

        :param bot: The mocked Bot.
        :param tmpl: The mocked TgTemplater.
        :return: None
        """
        await BotCommands(bot=bot, tmpl_render=tmpl, admin_ids=[111, 222]).set_commands()
        calls: list = bot.set_my_commands.await_args_list
        assert calls[0].kwargs == {"commands": [], "scope": BotCommandScopeAllGroupChats()}
        assert calls[1].kwargs == {"commands": [], "scope": BotCommandScopeAllPrivateChats()}
        rest: list = calls[2:]
        assert len(rest) == 3 * 3  # (default, ru, uk) x (private chats, admin 111, admin 222)
        for block, (locale, language_code) in enumerate([("en", None), ("ru", "ru"), ("uk", "uk")]):
            private, admin_1, admin_2 = rest[block * 3 : block * 3 + 3]
            assert private.kwargs["language_code"] == language_code
            assert private.kwargs["scope"] == BotCommandScopeAllPrivateChats()
            assert [c.description for c in private.kwargs["commands"]] == [
                f"cmd_start.jinja2|{locale}",
                f"cmd_about.jinja2|{locale}",
                f"cmd_stop.jinja2|{locale}",
            ]
            for admin_call, admin_id in ((admin_1, 111), (admin_2, 222)):
                assert admin_call.kwargs["scope"] == BotCommandScopeChat(chat_id=admin_id)
                assert admin_call.kwargs["language_code"] == language_code
                assert [c.command for c in admin_call.kwargs["commands"]] == ["start", "about", "stop", "stats"]

    async def test_without_admins(self, bot: MagicMock, tmpl: MagicMock) -> None:
        """
        With no admins, only the private-chat commands are set per locale.

        :param bot: The mocked Bot.
        :param tmpl: The mocked TgTemplater.
        :return: None
        """
        await BotCommands(bot=bot, tmpl_render=tmpl, admin_ids=[]).set_commands()
        assert bot.set_my_commands.await_count == 2 + 3
