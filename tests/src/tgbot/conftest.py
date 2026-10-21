"""Shared fixtures for the tgbot tests."""

from pathlib import Path
from typing import Iterator
from unittest.mock import AsyncMock, MagicMock, create_autospec

import pytest
from aiogram import Bot

from core.db.repository import Database
from core.tg_templater import TgTemplater
from tgbot.misc.keyboards import KeyboardManager
from tgbot.services.common import BaseService

from .helpers import make_message

__all__: tuple = ()


@pytest.fixture(autouse=True)
def reset_logo_cache() -> Iterator[None]:
    """
    Resets the process-wide Logo file_id cache around every test.

    :return: None
    """
    BaseService._logo_file_id = None  # pylint: disable=protected-access
    yield
    BaseService._logo_file_id = None  # pylint: disable=protected-access


@pytest.fixture(name="bot")
def bot_fixture() -> MagicMock:
    """
    An autospecced Bot whose API methods are AsyncMocks: send_photo returns a photo Message with
    ID 100, edits return a photo Message with ID 50.

    :return: The mocked Bot.
    """
    mock: MagicMock = create_autospec(spec=Bot, instance=True)
    mock.send_photo = AsyncMock(return_value=make_message(message_id=100, photo_id="sent"))
    mock.send_message = AsyncMock(return_value=make_message(message_id=101, text="notice"))
    mock.edit_message_caption = AsyncMock(return_value=make_message(message_id=50, photo_id="kept"))
    mock.edit_message_media = AsyncMock(return_value=make_message(message_id=50, photo_id="edited"))
    mock.delete_message = AsyncMock(return_value=True)
    mock.send_chat_action = AsyncMock(return_value=True)
    mock.id = 1
    return mock


@pytest.fixture(name="config")
def config_fixture(tmp_path: Path) -> MagicMock:
    """
    A Config stand-in whose bot logo path points into tmp_path.

    :param tmp_path: pytest's temporary directory.
    :return: The mocked Config.
    """
    config: MagicMock = MagicMock()
    config.paths.bot_logo = tmp_path / "bot_logo.jpg"
    config.admins = [111]
    return config


@pytest.fixture(name="db")
def db_fixture() -> MagicMock:
    """
    An autospecced Database with AsyncMock queries; get_dialog_id returns 50 by default.

    :return: The mocked Database.
    """
    mock: MagicMock = create_autospec(spec=Database, instance=True)
    mock.get_dialog_id = AsyncMock(return_value=50)
    mock.save_dialog_id = AsyncMock(return_value=None)
    mock.delete_user = AsyncMock(return_value=None)
    mock.save_user_settings = AsyncMock(return_value=None)
    mock.get_all_user_settings = AsyncMock(return_value=[])
    mock.get_api_counter_value = AsyncMock(return_value=0)
    mock.get_number_of_users = AsyncMock(return_value=0)
    return mock


async def _render(tmpl: str, locale: str, data: dict | None = None, **_: object) -> str:
    """
    Fake TgTemplater.render: encodes the template, locale and data into the result.

    :param tmpl: Template path.
    :param locale: Locale.
    :param data: Template data.
    :param _: Other render arguments (max_len), unused.
    :return: "<template file name>|<locale>|<data>".
    """
    return f"{tmpl.rsplit('/', 1)[-1]}|{locale}|{data or {}}"


@pytest.fixture(name="tmpl")
def tmpl_fixture() -> MagicMock:
    """
    An autospecced TgTemplater rendering "<template>|<locale>|<data>".

    :return: The mocked TgTemplater.
    """
    mock: MagicMock = create_autospec(spec=TgTemplater, instance=True)
    mock.render = AsyncMock(side_effect=_render)
    return mock


@pytest.fixture(name="kb")
def kb_fixture() -> MagicMock:
    """
    An autospecced KeyboardManager returning sentinel markups.

    :return: The mocked KeyboardManager.
    """
    mock: MagicMock = create_autospec(spec=KeyboardManager, instance=True)
    mock.geolocation = AsyncMock(return_value="geo_kb")
    mock.cities = AsyncMock(return_value="cities_kb")
    mock.units = MagicMock(return_value="units_kb")
    return mock
