"""This module contains business logic of the weather setup dialog."""

from asyncio import sleep
from typing import Any

from aiogram import Bot
from aiogram.enums import ChatAction
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardMarkup, Message, ReplyKeyboardMarkup
from loguru import logger

from core.db.data_types import Units, UserSettings
from core.db.repository import Database
from core.tg_templater import TgTemplater
from tgbot.config import Config
from tgbot.misc.data_types import CityCallback, UnitsCallback
from tgbot.misc.fsm_states import WeatherSetupStates
from tgbot.misc.keyboards import KeyboardManager
from tgbot.services.common import BaseService, PhotoSource
from weather.client import WeatherAPI
from weather.data_types import CityData
from weather.reporter import WeatherReport, WeatherReporter

__all__: tuple[str] = ("DialogService",)


class DialogService(BaseService):
    """
    The class implements the weather setup dialog: city (by name or location) -> one of the found
    cities -> measurement units -> the first weather report.

    :cvar _msg_enter_city: Path to the "write the city name" template.
    :cvar _msg_city_not_found: Path to the "no city found" template.
    :cvar _msg_select_city: Path to the "select the city" template.
    :cvar _msg_select_units: Path to the "choose the units" template.
    :cvar _msg_setup_complete: Path to the "setup complete" template.
    :cvar _SETUP_COMPLETE_TTL: Seconds the "setup complete" notice stays in the chat.
    :cvar _MAX_CITY_LENGTH: Length of the users.city column.
    """

    _msg_enter_city: str = "tgbot/dialog/msg_enter_city.jinja2"
    _msg_city_not_found: str = "tgbot/dialog/msg_city_not_found.jinja2"
    _msg_select_city: str = "tgbot/dialog/msg_select_city.jinja2"
    _msg_select_units: str = "tgbot/dialog/msg_select_units.jinja2"
    _msg_setup_complete: str = "tgbot/dialog/msg_setup_complete.jinja2"
    _SETUP_COMPLETE_TTL: float = 15
    _MAX_CITY_LENGTH: int = 72

    # pylint: disable=too-many-arguments
    def __init__(
        self,
        config: Config,
        tmpl: TgTemplater,
        kb: KeyboardManager,
        db: Database,
        api: WeatherAPI,
        reporter: WeatherReporter,
    ) -> None:
        """
        Initialize the service.

        :param config: Config object with configuration settings.
        :param tmpl: TgTemplater object for rendering templates.
        :param kb: KeyboardManager object for keyboard generation.
        :param db: Database instance.
        :param api: OpenWeatherMap API client, for the city search.
        :param reporter: Weather report builder.
        """
        super().__init__(config=config, tmpl=tmpl, kb=kb, db=db)
        self._api: WeatherAPI = api
        self._reporter: WeatherReporter = reporter

    async def start(self, message: Message, state: FSMContext) -> None:
        """
        Starts the setup dialog from scratch, dropping the user's previous settings.

        :param message: The '/start' message.
        :param state: The FSM context of the user.
        :return: None
        """
        await state.clear()
        await self._delete_user_msg(message=message)
        user_id: int = message.chat.id
        locale: str = self._locale(user=message.from_user)
        old_dialog_id: int | None = await self._db.get_dialog_id(user_id=user_id)
        await self._db.delete_user(user_id=user_id)
        await self._replace_dialog(
            bot=message.bot,  # type: ignore [arg-type]
            chat_id=user_id,
            old_msg_id=old_dialog_id,
            caption=await self._tmpl.render(tmpl=self._msg_enter_city, locale=locale, data={"greeting": True}),
            reply_markup=await self._kb.geolocation(locale=locale),
        )
        await state.set_state(WeatherSetupStates.wait_for_city)

    async def process_city(self, message: Message, state: FSMContext) -> None:
        """
        Searches for the city the user typed or the location they sent, and offers the found cities.

        :param message: The message with a city name or a location.
        :param state: The FSM context of the user.
        :return: None
        """
        # Ignore further input while this search runs
        await state.set_state(WeatherSetupStates.wait_for_city_choice)
        await self._delete_user_msg(message=message)
        bot: Bot = message.bot  # type: ignore [assignment]
        user_id: int = message.chat.id
        locale: str = self._locale(user=message.from_user)
        await bot.send_chat_action(chat_id=user_id, action=ChatAction.TYPING)
        cities: list[CityData] = []
        if message.location is not None:  # A location or a venue
            cities = await self._api.reverse_geocode(
                latitude=message.location.latitude, longitude=message.location.longitude, lang=locale
            )
        elif message.text:
            cities = await self._api.search_cities(city_name=message.text, lang=locale)
        reply_markup: InlineKeyboardMarkup | ReplyKeyboardMarkup
        if cities:
            await state.update_data(cities=[city._asdict() for city in cities])
            caption: str = await self._tmpl.render(tmpl=self._msg_select_city, locale=locale)
            reply_markup = await self._kb.cities(locale=locale, cities=cities)
        else:
            caption = await self._tmpl.render(tmpl=self._msg_city_not_found, locale=locale)
            reply_markup = await self._kb.geolocation(locale=locale)
            await state.set_state(WeatherSetupStates.wait_for_city)
        await self._replace_dialog(
            bot=bot,
            chat_id=user_id,
            old_msg_id=await self._db.get_dialog_id(user_id=user_id),
            caption=caption,
            reply_markup=reply_markup,
        )

    async def select_another_city(self, call: CallbackQuery, state: FSMContext) -> None:
        """
        Returns the dialog to the city input.

        :param call: The callback query of the button press.
        :param state: The FSM context of the user.
        :return: None
        """
        locale: str = self._locale(user=call.from_user)
        old_msg_id: int | None = (
            call.message.message_id
            if isinstance(call.message, Message)
            else await self._db.get_dialog_id(user_id=call.from_user.id)
        )
        await self._replace_dialog(
            bot=call.bot,  # type: ignore [arg-type]
            chat_id=call.from_user.id,
            old_msg_id=old_msg_id,
            caption=await self._tmpl.render(tmpl=self._msg_enter_city, locale=locale, data={"greeting": False}),
            reply_markup=await self._kb.geolocation(locale=locale),
        )
        await state.set_state(WeatherSetupStates.wait_for_city)

    async def select_city(self, call: CallbackQuery, callback_data: CityCallback, state: FSMContext) -> None:
        """
        Remembers the chosen city and asks for the measurement units.

        A button of an outdated city list (its FSM data is gone) restarts the city input instead.

        :param call: The callback query of the button press.
        :param callback_data: The pressed city button's data.
        :param state: The FSM context of the user.
        :return: None
        """
        data: dict[str, Any] = await state.get_data()
        cities: list[dict[str, Any]] = data.get("cities") or []
        if not 0 <= callback_data.index < len(cities):
            await self.select_another_city(call=call, state=state)
            return
        await state.set_data({"city": cities[callback_data.index]})
        await state.set_state(WeatherSetupStates.wait_for_units)
        locale: str = self._locale(user=call.from_user)
        await self._edit_or_send_callback(
            call=call,
            caption=await self._tmpl.render(tmpl=self._msg_select_units, locale=locale),
            reply_markup=self._kb.units(),
        )

    async def select_units(self, call: CallbackQuery, callback_data: UnitsCallback, state: FSMContext) -> None:
        """
        Saves the settings, shows the first weather report and completes the dialog.

        :param call: The callback query of the button press.
        :param callback_data: The pressed units button's data.
        :param state: The FSM context of the user.
        :return: None
        """
        data: dict[str, Any] = await state.get_data()
        if "city" not in data:
            await self.select_another_city(call=call, state=state)
            return
        await state.clear()
        city: CityData = CityData(**data["city"])
        bot: Bot = call.bot  # type: ignore [assignment]
        user_id: int = call.from_user.id
        locale: str = self._locale(user=call.from_user)
        units: Units = callback_data.units
        await bot.send_chat_action(chat_id=user_id, action=ChatAction.UPLOAD_PHOTO)
        dialog_id: int | None = await self._db.get_dialog_id(user_id=user_id)
        if isinstance(call.message, Message):
            dialog_id = call.message.message_id
        settings: UserSettings = UserSettings(
            user_id=user_id,
            dialog_id=dialog_id or 0,
            lang=locale,
            city=city.name[: self._MAX_CITY_LENGTH],
            latitude=city.latitude,
            longitude=city.longitude,
            units=units,
        )
        await self._db.save_user_settings(settings=settings)
        logger.info(f"User {user_id} set up the weather for {city.full_name} ({units})")
        report: WeatherReport = await self._reporter.report(settings=settings)
        photo: PhotoSource = (
            BufferedInputFile(file=report.photo, filename="forecast.png") if report.photo else self._logo()
        )
        await self._edit_or_send_callback(call=call, caption=report.caption, photo=photo)
        notice: Message = await bot.send_message(
            chat_id=user_id,
            text=await self._tmpl.render(tmpl=self._msg_setup_complete, locale=locale),
            disable_notification=True,
        )
        await sleep(self._SETUP_COMPLETE_TTL)
        await self._delete_msg(bot=bot, chat_id=user_id, msg_id=notice.message_id)

    async def delete_any(self, message: Message) -> None:
        """
        Deletes a message the bot doesn't expect at this point of the dialog.

        :param message: The incoming message from the user.
        :return: None
        """
        await self._delete_user_msg(message=message)
