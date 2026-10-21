"""
Unit tests for src/tgbot/misc/keyboards.py (KeyboardManager).

TgTemplater is an autospecced mock rendering "<template>|<locale>".
"""

from unittest.mock import AsyncMock, MagicMock, create_autospec

import pytest
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup

from core.db.data_types import Units
from core.tg_templater import TgTemplater
from tgbot.misc.data_types import CityCallback, UnitsCallback
from tgbot.misc.keyboards import KeyboardManager
from weather.data_types import CityData

__all__: tuple = ()


async def _render(tmpl: str, locale: str) -> str:
    """
    Fake TgTemplater.render.

    :param tmpl: Template path.
    :param locale: Locale.
    :return: "<template file name>|<locale>".
    """
    return f"{tmpl.rsplit('/', 1)[-1]}|{locale}"


@pytest.fixture(name="kb")
def kb_fixture() -> KeyboardManager:
    """
    A KeyboardManager over a mocked templater.

    :return: The KeyboardManager under test.
    """
    tmpl: MagicMock = create_autospec(spec=TgTemplater, instance=True)
    tmpl.render = AsyncMock(side_effect=_render)
    return KeyboardManager(tmpl=tmpl)


class TestGeolocation:
    """Tests KeyboardManager.geolocation."""

    async def test_single_location_button(self, kb: KeyboardManager) -> None:
        """
        One resized, one-time button requesting the location.

        :param kb: The KeyboardManager under test.
        :return: None
        """
        markup: ReplyKeyboardMarkup = await kb.geolocation(locale="uk")
        assert len(markup.keyboard) == 1 and len(markup.keyboard[0]) == 1
        button = markup.keyboard[0][0]
        assert button.text == "kb_send_geolocation.jinja2|uk"
        assert button.request_location is True
        assert markup.resize_keyboard and markup.one_time_keyboard and markup.selective


class TestCities:
    """Tests KeyboardManager.cities."""

    async def test_one_row_per_city_plus_another_city(self, kb: KeyboardManager) -> None:
        """
        Each city gets its own row carrying its index; the last row is "another city".

        :param kb: The KeyboardManager under test.
        :return: None
        """
        cities: list[CityData] = [
            CityData(name="Kyiv", full_name="Kyiv, UA", latitude=1.0, longitude=2.0),
            CityData(name="Kyiv", full_name="Kyiv, Kyiv Oblast, UA", latitude=3.0, longitude=4.0),
        ]
        markup: InlineKeyboardMarkup = await kb.cities(locale="ru", cities=cities)
        rows = markup.inline_keyboard
        assert [(r[0].text, r[0].callback_data) for r in rows] == [
            ("Kyiv, UA", CityCallback(index=0).pack()),
            ("Kyiv, Kyiv Oblast, UA", CityCallback(index=1).pack()),
            ("kb_another_city.jinja2|ru", "another_city"),
        ]
        assert all(len(row) == 1 for row in rows)


class TestUnits:
    """Tests KeyboardManager.units."""

    def test_celsius_and_fahrenheit(self) -> None:
        """
        One row: °C (metric) and °F (imperial).

        :return: None
        """
        markup: InlineKeyboardMarkup = KeyboardManager.units()
        assert [(b.text, b.callback_data) for b in markup.inline_keyboard[0]] == [
            ("°C", UnitsCallback(units=Units.METRIC).pack()),
            ("°F", UnitsCallback(units=Units.IMPERIAL).pack()),
        ]
