"""
Unit tests for src/tgbot/services/dialog.py (DialogService).

The FSM context is a real one over aiogram's MemoryStorage, so state transitions and the stored
city list are checked as they would be stored. Bot, Database, TgTemplater, KeyboardManager,
WeatherAPI and WeatherReporter are autospecced mocks (see ../conftest.py).
"""

# pylint: disable=protected-access

from unittest.mock import AsyncMock, MagicMock, create_autospec, patch

import pytest
from aiogram.enums import ChatAction
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BufferedInputFile, Chat, FSInputFile, InaccessibleMessage, Location

from core.db.data_types import Units, UserSettings
from tests.src.tgbot.helpers import USER_ID, make_call, make_message
from tgbot.misc.data_types import CityCallback, UnitsCallback
from tgbot.misc.fsm_states import WeatherSetupStates
from tgbot.services.dialog import DialogService
from weather.client import WeatherAPI
from weather.data_types import CityData
from weather.reporter import WeatherReport, WeatherReporter

__all__: tuple = ()

_KYIV: CityData = CityData(name="Київ", full_name="Київ, UA", latitude=50.45, longitude=30.52)
_LVIV: CityData = CityData(name="Львів", full_name="Львів, UA", latitude=49.84, longitude=24.03)


@pytest.fixture(name="state")
def state_fixture() -> FSMContext:
    """
    A real FSM context over MemoryStorage.

    :return: The FSM context.
    """
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=USER_ID, user_id=USER_ID))


@pytest.fixture(name="api")
def api_fixture() -> MagicMock:
    """
    An autospecced WeatherAPI: a name search finds Kyiv and Lviv, a location finds Kyiv.

    :return: The mocked WeatherAPI.
    """
    mock: MagicMock = create_autospec(spec=WeatherAPI, instance=True)
    mock.search_cities = AsyncMock(return_value=[_KYIV, _LVIV])
    mock.reverse_geocode = AsyncMock(return_value=[_KYIV])
    return mock


@pytest.fixture(name="reporter")
def reporter_fixture() -> MagicMock:
    """
    An autospecced WeatherReporter returning a report with a PNG image.

    :return: The mocked WeatherReporter.
    """
    mock: MagicMock = create_autospec(spec=WeatherReporter, instance=True)
    mock.report = AsyncMock(return_value=WeatherReport(photo=b"png", caption="weather"))
    return mock


# pylint: disable=too-many-arguments
@pytest.fixture(name="service")
def service_fixture(
    config: MagicMock, tmpl: MagicMock, kb: MagicMock, db: MagicMock, api: MagicMock, reporter: MagicMock
) -> DialogService:
    """
    A DialogService over the mocked dependencies.

    :param config: The mocked Config.
    :param tmpl: The mocked TgTemplater.
    :param kb: The mocked KeyboardManager.
    :param db: The mocked Database.
    :param api: The mocked WeatherAPI.
    :param reporter: The mocked WeatherReporter.
    :return: The DialogService under test.
    """
    return DialogService(config=config, tmpl=tmpl, kb=kb, db=db, api=api, reporter=reporter)


class TestStart:
    """Tests DialogService.start."""

    async def test_resets_user_and_asks_for_city(
        self, service: DialogService, bot: MagicMock, db: MagicMock, state: FSMContext
    ) -> None:
        """
        /start clears the state, deletes the command and the user's row, replaces the dialog
        message with the greeting + geolocation keyboard and waits for a city.

        :param service: The DialogService under test.
        :param bot: The mocked Bot.
        :param db: The mocked Database.
        :param state: The FSM context.
        :return: None
        """
        await state.set_data({"cities": []})
        await service.start(message=make_message(message_id=7, text="/start", bot=bot), state=state)
        db.delete_user.assert_awaited_once_with(user_id=USER_ID)
        kwargs = bot.send_photo.await_args.kwargs
        assert kwargs["caption"] == "msg_enter_city.jinja2|ru|{'greeting': True}"
        assert kwargs["reply_markup"] == "geo_kb"
        db.save_dialog_id.assert_awaited_once_with(user_id=USER_ID, dialog_id=100)
        deleted = [c.kwargs["message_id"] for c in bot.delete_message.await_args_list]
        assert deleted == [7, 50]
        assert await state.get_state() == WeatherSetupStates.wait_for_city.state
        assert await state.get_data() == {}


class TestProcessCity:
    """Tests DialogService.process_city."""

    async def test_text_search_offers_cities(
        self, service: DialogService, bot: MagicMock, api: MagicMock, kb: MagicMock, state: FSMContext
    ) -> None:
        """
        A typed name is searched; the found cities are stored and offered as buttons.

        :param service: The DialogService under test.
        :param bot: The mocked Bot.
        :param api: The mocked WeatherAPI.
        :param kb: The mocked KeyboardManager.
        :param state: The FSM context.
        :return: None
        """
        await service.process_city(message=make_message(text="Kyiv", bot=bot), state=state)
        bot.send_chat_action.assert_awaited_once_with(chat_id=USER_ID, action=ChatAction.TYPING)
        api.search_cities.assert_awaited_once_with(city_name="Kyiv", lang="ru")
        kb.cities.assert_awaited_once_with(locale="ru", cities=[_KYIV, _LVIV])
        kwargs = bot.send_photo.await_args.kwargs
        assert kwargs["caption"] == "msg_select_city.jinja2|ru|{}"
        assert kwargs["reply_markup"] == "cities_kb"
        assert await state.get_state() == WeatherSetupStates.wait_for_city_choice.state
        assert await state.get_data() == {"cities": [_KYIV._asdict(), _LVIV._asdict()]}

    async def test_location_uses_reverse_geocoding(
        self, service: DialogService, bot: MagicMock, api: MagicMock, state: FSMContext
    ) -> None:
        """
        A sent location is reverse-geocoded.

        :param service: The DialogService under test.
        :param bot: The mocked Bot.
        :param api: The mocked WeatherAPI.
        :param state: The FSM context.
        :return: None
        """
        message = make_message(location=Location(latitude=50.0, longitude=30.0), bot=bot)
        await service.process_city(message=message, state=state)
        api.reverse_geocode.assert_awaited_once_with(latitude=50.0, longitude=30.0, lang="ru")
        api.search_cities.assert_not_awaited()

    async def test_nothing_found(
        self, service: DialogService, bot: MagicMock, api: MagicMock, state: FSMContext
    ) -> None:
        """
        No city found: the user is told so and asked again, with the geolocation keyboard.

        :param service: The DialogService under test.
        :param bot: The mocked Bot.
        :param api: The mocked WeatherAPI.
        :param state: The FSM context.
        :return: None
        """
        api.search_cities.return_value = []
        await service.process_city(message=make_message(text="Nowhere", bot=bot), state=state)
        kwargs = bot.send_photo.await_args.kwargs
        assert kwargs["caption"] == "msg_city_not_found.jinja2|ru|{}"
        assert kwargs["reply_markup"] == "geo_kb"
        assert await state.get_state() == WeatherSetupStates.wait_for_city.state

    async def test_no_text_and_no_location(
        self, service: DialogService, bot: MagicMock, api: MagicMock, state: FSMContext
    ) -> None:
        """
        A message with neither text nor location searches nothing and counts as not found.

        :param service: The DialogService under test.
        :param bot: The mocked Bot.
        :param api: The mocked WeatherAPI.
        :param state: The FSM context.
        :return: None
        """
        await service.process_city(message=make_message(bot=bot), state=state)
        api.search_cities.assert_not_awaited()
        api.reverse_geocode.assert_not_awaited()
        assert bot.send_photo.await_args.kwargs["caption"].startswith("msg_city_not_found")


class TestSelectAnotherCity:
    """Tests DialogService.select_another_city."""

    async def test_replaces_callback_message(self, service: DialogService, bot: MagicMock, state: FSMContext) -> None:
        """
        The callback message is replaced with the city prompt (without greeting).

        :param service: The DialogService under test.
        :param bot: The mocked Bot.
        :param state: The FSM context.
        :return: None
        """
        call = make_call(bot=bot, message=make_message(message_id=33, photo_id="p"))
        await service.select_another_city(call=call, state=state)
        assert bot.send_photo.await_args.kwargs["caption"] == "msg_enter_city.jinja2|ru|{'greeting': False}"
        bot.delete_message.assert_awaited_once_with(chat_id=USER_ID, message_id=33)
        assert await state.get_state() == WeatherSetupStates.wait_for_city.state

    async def test_inaccessible_message_uses_dialog_id(
        self, service: DialogService, bot: MagicMock, db: MagicMock, state: FSMContext
    ) -> None:
        """
        An inaccessible callback message falls back to the stored dialog message.

        :param service: The DialogService under test.
        :param bot: The mocked Bot.
        :param db: The mocked Database.
        :param state: The FSM context.
        :return: None
        """
        call = make_call(bot=bot, message=InaccessibleMessage(chat=Chat(id=USER_ID, type="private"), message_id=9))
        await service.select_another_city(call=call, state=state)
        db.get_dialog_id.assert_awaited_once_with(user_id=USER_ID)
        bot.delete_message.assert_awaited_once_with(chat_id=USER_ID, message_id=50)


class TestSelectCity:
    """Tests DialogService.select_city."""

    async def test_valid_index(self, service: DialogService, bot: MagicMock, state: FSMContext) -> None:
        """
        The chosen city replaces the list in the FSM data, and the message asks for the units.

        :param service: The DialogService under test.
        :param bot: The mocked Bot.
        :param state: The FSM context.
        :return: None
        """
        await state.set_data({"cities": [_KYIV._asdict(), _LVIV._asdict()]})
        call = make_call(bot=bot, message=make_message(message_id=33, photo_id="p"))
        await service.select_city(call=call, callback_data=CityCallback(index=1), state=state)
        assert await state.get_data() == {"city": _LVIV._asdict()}
        assert await state.get_state() == WeatherSetupStates.wait_for_units.state
        bot.edit_message_caption.assert_awaited_once_with(
            chat_id=USER_ID, message_id=33, caption="msg_select_units.jinja2|ru|{}", reply_markup="units_kb"
        )

    @pytest.mark.parametrize("index", [2, -1])
    async def test_outdated_button_restarts_city_input(
        self, service: DialogService, bot: MagicMock, state: FSMContext, index: int
    ) -> None:
        """
        An index outside the stored list restarts the city input.

        :param service: The DialogService under test.
        :param bot: The mocked Bot.
        :param state: The FSM context.
        :param index: The pressed button's index.
        :return: None
        """
        await state.set_data({"cities": [_KYIV._asdict(), _LVIV._asdict()]})
        call = make_call(bot=bot, message=make_message(message_id=33, photo_id="p"))
        await service.select_city(call=call, callback_data=CityCallback(index=index), state=state)
        bot.edit_message_caption.assert_not_awaited()
        assert bot.send_photo.await_args.kwargs["caption"].startswith("msg_enter_city")
        assert await state.get_state() == WeatherSetupStates.wait_for_city.state


class TestSelectUnits:
    """Tests DialogService.select_units."""

    async def test_saves_settings_and_shows_report(
        self,
        service: DialogService,
        bot: MagicMock,
        db: MagicMock,
        reporter: MagicMock,
        state: FSMContext,
    ) -> None:
        """
        The settings are saved, the report image replaces the dialog photo, the state is cleared
        and the "setup complete" notice is deleted after its TTL.

        :param service: The DialogService under test.
        :param bot: The mocked Bot.
        :param db: The mocked Database.
        :param reporter: The mocked WeatherReporter.
        :param state: The FSM context.
        :return: None
        """
        await state.set_data({"city": _KYIV._asdict()})
        await state.set_state(WeatherSetupStates.wait_for_units)
        call = make_call(bot=bot, message=make_message(message_id=33, photo_id="p"), language_code="uk")
        with patch("tgbot.services.dialog.sleep", new=AsyncMock()) as fake_sleep:
            await service.select_units(call=call, callback_data=UnitsCallback(units=Units.IMPERIAL), state=state)
        settings = UserSettings(
            user_id=USER_ID,
            dialog_id=33,
            lang="uk",
            city="Київ",
            latitude=50.45,
            longitude=30.52,
            units=Units.IMPERIAL,
        )
        db.save_user_settings.assert_awaited_once_with(settings=settings)
        reporter.report.assert_awaited_once_with(settings=settings)
        bot.send_chat_action.assert_awaited_once_with(chat_id=USER_ID, action=ChatAction.UPLOAD_PHOTO)
        media = bot.edit_message_media.await_args.kwargs["media"]
        assert isinstance(media.media, BufferedInputFile)
        assert media.caption == "weather"
        assert bot.send_message.await_args.kwargs["text"] == "msg_setup_complete.jinja2|uk|{}"
        fake_sleep.assert_awaited_once_with(15)
        bot.delete_message.assert_awaited_once_with(chat_id=USER_ID, message_id=101)
        assert await state.get_state() is None
        assert await state.get_data() == {}

    async def test_logo_when_no_forecast_and_long_name_truncated(
        self,
        service: DialogService,
        bot: MagicMock,
        db: MagicMock,
        reporter: MagicMock,
        state: FSMContext,
    ) -> None:
        """
        Without a forecast image the logo is shown; a city name longer than the column is cut to
        72 characters; an inaccessible callback message falls back to the stored dialog ID.

        :param service: The DialogService under test.
        :param bot: The mocked Bot.
        :param db: The mocked Database.
        :param reporter: The mocked WeatherReporter.
        :param state: The FSM context.
        :return: None
        """
        reporter.report.return_value = WeatherReport(photo=None, caption="no forecast")
        await state.set_data({"city": _KYIV._replace(name="x" * 100)._asdict()})
        call = make_call(bot=bot, message=InaccessibleMessage(chat=Chat(id=USER_ID, type="private"), message_id=9))
        with patch("tgbot.services.dialog.sleep", new=AsyncMock()):
            await service.select_units(call=call, callback_data=UnitsCallback(units=Units.METRIC), state=state)
        settings: UserSettings = db.save_user_settings.await_args.kwargs["settings"]
        assert settings.city == "x" * 72
        assert settings.dialog_id == 50
        assert isinstance(bot.edit_message_media.await_args.kwargs["media"].media, FSInputFile)

    async def test_without_city_restarts_city_input(
        self, service: DialogService, bot: MagicMock, db: MagicMock, state: FSMContext
    ) -> None:
        """
        A units button without a chosen city in the FSM data restarts the city input.

        :param service: The DialogService under test.
        :param bot: The mocked Bot.
        :param db: The mocked Database.
        :param state: The FSM context.
        :return: None
        """
        call = make_call(bot=bot, message=make_message(message_id=33, photo_id="p"))
        await service.select_units(call=call, callback_data=UnitsCallback(units=Units.METRIC), state=state)
        db.save_user_settings.assert_not_awaited()
        assert bot.send_photo.await_args.kwargs["caption"].startswith("msg_enter_city")
        assert await state.get_state() == WeatherSetupStates.wait_for_city.state


class TestDeleteAny:
    """Tests DialogService.delete_any."""

    async def test_deletes_message(self, service: DialogService, bot: MagicMock) -> None:
        """
        An unexpected message is deleted.

        :param service: The DialogService under test.
        :param bot: The mocked Bot.
        :return: None
        """
        await service.delete_any(message=make_message(message_id=7, text="hi", bot=bot))
        bot.delete_message.assert_awaited_once_with(chat_id=USER_ID, message_id=7)
