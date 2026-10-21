"""This module implements the keyboards used in the bot."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from core.db.data_types import Units
from core.tg_templater import TgTemplater
from tgbot.misc.data_types import CityCallback, UnitsCallback
from weather.data_types import CityData

__all__: tuple[str] = ("KeyboardManager",)


class KeyboardManager:
    """
    Implements creation of bot keyboards.

    :cvar _kb_send_geolocation: Path to the "Send geolocation" button template.
    :cvar _kb_another_city: Path to the "Select another city" button template.
    """

    _kb_send_geolocation: str = "tgbot/dialog/kb_send_geolocation.jinja2"
    _kb_another_city: str = "tgbot/dialog/kb_another_city.jinja2"

    def __init__(self, tmpl: TgTemplater) -> None:
        """
        Initialize the keyboard manager.

        :param tmpl: TgTemplater object.
        """
        self._tmpl: TgTemplater = tmpl

    async def geolocation(self, locale: str) -> ReplyKeyboardMarkup:
        """
        Creates the keyboard with the "Send geolocation" button.

        :param locale: Language code of the user.
        :return: Keyboard as ReplyKeyboardMarkup object.
        """
        text: str = await self._tmpl.render(tmpl=self._kb_send_geolocation, locale=locale)
        return ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=text, request_location=True)]],
            resize_keyboard=True,
            one_time_keyboard=True,
            selective=True,
        )

    async def cities(self, locale: str, cities: list[CityData]) -> InlineKeyboardMarkup:
        """
        Creates the keyboard listing the found cities, one per row, plus a "Select another city" button.

        :param locale: Language code of the user.
        :param cities: Found cities.
        :return: Keyboard as InlineKeyboardMarkup object.
        """
        rows: list[list[InlineKeyboardButton]] = [
            [InlineKeyboardButton(text=city.full_name, callback_data=CityCallback(index=idx).pack())]
            for idx, city in enumerate(cities)
        ]
        another_city: str = await self._tmpl.render(tmpl=self._kb_another_city, locale=locale)
        rows.append([InlineKeyboardButton(text=another_city, callback_data="another_city")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    @staticmethod
    def units() -> InlineKeyboardMarkup:
        """
        Creates the measurement units selection keyboard.

        :return: Keyboard as InlineKeyboardMarkup object.
        """
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="°C", callback_data=UnitsCallback(units=Units.METRIC).pack()),
                    InlineKeyboardButton(text="°F", callback_data=UnitsCallback(units=Units.IMPERIAL).pack()),
                ]
            ]
        )
