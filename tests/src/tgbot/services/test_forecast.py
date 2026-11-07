"""
Unit tests for src/tgbot/services/forecast.py (ForecastService).

Bot, Database and WeatherReporter are autospecced mocks (see ../conftest.py); asyncio.sleep is
patched out in every test, so neither the per-send pause nor a flood-control wait slows the
suite down. The Bot's send_photo returns a photo Message (ID 100) whose largest size has file_id
"sent" - the ID the service should reuse for the rest of a location.
"""

# ruff: noqa: PLR2004, S101, SLF001, TID252

from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, create_autospec, patch

import pytest
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
)
from aiogram.types import BufferedInputFile

from core.db.data_types import Units, UserSettings
from tgbot.services.forecast import ForecastService
from weather.reporter import WeatherReporter

from ..helpers import telegram_method

__all__: tuple = ()


def _user(user_id: int, lang: str = "ru", city: str = "Kyiv", units: Units = Units.METRIC) -> UserSettings:
    """
    Builds a user's settings; "Kyiv" and "Lviv" map to fixed coordinates.

    :param user_id: Telegram user ID (the dialog message ID is user_id * 10).
    :param lang: Language code.
    :param city: "Kyiv" or "Lviv".
    :param units: Measurement units.
    :return: The user's settings.
    """
    lat, lon = (50.45, 30.52) if city == "Kyiv" else (49.84, 24.03)
    return UserSettings(
        user_id=user_id, dialog_id=user_id * 10, lang=lang, city=city, latitude=lat, longitude=lon, units=units
    )


@pytest.fixture(autouse=True, name="fake_sleep")
def fake_sleep_fixture() -> Iterator[AsyncMock]:
    """
    Patches asyncio.sleep inside the forecast service.

    :return: The patched sleep.
    """
    with patch("tgbot.services.forecast.sleep", new=AsyncMock()) as fake:
        yield fake


@pytest.fixture(name="reporter")
def reporter_fixture() -> MagicMock:
    """
    An autospecced WeatherReporter.

    Every location has an image and current weather, every caption names its city and language.

    :return: The mocked WeatherReporter.
    """
    mock: MagicMock = create_autospec(spec=WeatherReporter, instance=True)
    mock.forecast_image = AsyncMock(return_value=b"png")
    mock.current_weather = AsyncMock(return_value=MagicMock())

    async def caption(city: str, units: Units, lang: str, **_: object) -> str:
        """
        Fake caption.

        :param city: City name.
        :param units: Units.
        :param lang: Language code.
        :param _: Other caption arguments (current), unused.
        :return: "<city>|<units>|<lang>".
        """
        return f"{city}|{units}|{lang}"

    mock.caption = AsyncMock(side_effect=caption)
    return mock


@pytest.fixture(name="service")
def service_fixture(  # noqa: PLR0913 - one fixture per dependency
    *, config: MagicMock, tmpl: MagicMock, kb: MagicMock, db: MagicMock, bot: MagicMock, reporter: MagicMock
) -> ForecastService:
    """
    A ForecastService over the mocked dependencies.

    :param config: The mocked Config.
    :param tmpl: The mocked TgTemplater.
    :param kb: The mocked KeyboardManager.
    :param db: The mocked Database.
    :param bot: The mocked Bot.
    :param reporter: The mocked WeatherReporter.
    :return: The ForecastService under test.
    """
    return ForecastService(config=config, tmpl=tmpl, kb=kb, db=db, bot=bot, reporter=reporter)


class TestUpdateAll:
    """Tests ForecastService.update_all / _update_location."""

    async def test_groups_requests(
        self, service: ForecastService, db: MagicMock, reporter: MagicMock, bot: MagicMock
    ) -> None:
        """
        Requests are grouped by location, units and language.

        One forecast per (location, units), one current weather per language of each, one
        caption and one delivery per user.

        :param service: The ForecastService under test.
        :param db: The mocked Database.
        :param reporter: The mocked WeatherReporter.
        :param bot: The mocked Bot.
        :return: None
        """
        db.get_all_user_settings.return_value = [
            _user(1),
            _user(2),
            _user(3, lang="uk"),
            _user(4, units=Units.IMPERIAL),
            _user(5, city="Lviv"),
        ]
        await service.update_all()
        forecast_keys = [(c.kwargs["latitude"], c.kwargs["units"]) for c in reporter.forecast_image.await_args_list]
        assert forecast_keys == [(50.45, Units.METRIC), (50.45, Units.IMPERIAL), (49.84, Units.METRIC)]
        current_keys = [
            (c.kwargs["latitude"], c.kwargs["units"], c.kwargs["lang"])
            for c in reporter.current_weather.await_args_list
        ]
        assert current_keys == [
            (50.45, Units.METRIC, "ru"),
            (50.45, Units.METRIC, "uk"),
            (50.45, Units.IMPERIAL, "ru"),
            (49.84, Units.METRIC, "ru"),
        ]
        assert reporter.caption.await_count == 5
        delivered = [(c.kwargs["chat_id"], c.kwargs["caption"]) for c in bot.send_photo.await_args_list]
        assert delivered == [
            (1, "Kyiv|metric|ru"),
            (2, "Kyiv|metric|ru"),
            (3, "Kyiv|metric|uk"),
            (4, "Kyiv|imperial|ru"),
            (5, "Lviv|metric|ru"),
        ]
        deleted = [(c.kwargs["chat_id"], c.kwargs["message_id"]) for c in bot.delete_message.await_args_list]
        assert deleted == [(1, 10), (2, 20), (3, 30), (4, 40), (5, 50)]

    async def test_reuses_uploaded_file_id(self, service: ForecastService, db: MagicMock, bot: MagicMock) -> None:
        """
        The image is uploaded for the first user of a location only; the rest get its file_id.

        :param service: The ForecastService under test.
        :param db: The mocked Database.
        :param bot: The mocked Bot.
        :return: None
        """
        db.get_all_user_settings.return_value = [_user(1), _user(2, lang="uk"), _user(3, city="Lviv")]
        await service.update_all()
        media = [c.kwargs["photo"] for c in bot.send_photo.await_args_list]
        assert isinstance(media[0], BufferedInputFile)
        assert media[1] == "sent"
        assert isinstance(media[2], BufferedInputFile)  # Another location: its own upload

    async def test_no_forecast_keeps_previous_report(
        self, service: ForecastService, db: MagicMock, reporter: MagicMock, bot: MagicMock
    ) -> None:
        """
        Without a forecast image the location's users are left alone, the next location still runs.

        :param service: The ForecastService under test.
        :param db: The mocked Database.
        :param reporter: The mocked WeatherReporter.
        :param bot: The mocked Bot.
        :return: None
        """
        reporter.forecast_image.side_effect = [None, b"png"]
        db.get_all_user_settings.return_value = [_user(1), _user(2, city="Lviv")]
        await service.update_all()
        assert [c.kwargs["latitude"] for c in reporter.current_weather.await_args_list] == [49.84]
        assert [c.kwargs["chat_id"] for c in bot.send_photo.await_args_list] == [2]
        assert [c.kwargs["chat_id"] for c in bot.delete_message.await_args_list] == [2]

    async def test_no_current_weather_keeps_previous_report(
        self, service: ForecastService, db: MagicMock, reporter: MagicMock, bot: MagicMock
    ) -> None:
        """
        Without the current weather the language's users are skipped.

        Without the current weather in one language its users are left alone, the other
        languages of the location are still updated.

        :param service: The ForecastService under test.
        :param db: The mocked Database.
        :param reporter: The mocked WeatherReporter.
        :param bot: The mocked Bot.
        :return: None
        """
        reporter.current_weather.side_effect = [None, MagicMock()]
        db.get_all_user_settings.return_value = [_user(1), _user(2), _user(3, lang="uk")]
        await service.update_all()
        assert [c.kwargs["chat_id"] for c in bot.send_photo.await_args_list] == [3]
        assert reporter.caption.await_count == 1
        assert [c.kwargs["chat_id"] for c in bot.delete_message.await_args_list] == [3]

    async def test_failing_location_does_not_stop_others(
        self, service: ForecastService, db: MagicMock, reporter: MagicMock, bot: MagicMock
    ) -> None:
        """
        An exception while handling one location is logged and the next location still runs.

        :param service: The ForecastService under test.
        :param db: The mocked Database.
        :param reporter: The mocked WeatherReporter.
        :param bot: The mocked Bot.
        :return: None
        """
        reporter.forecast_image.side_effect = [RuntimeError("boom"), b"png"]
        db.get_all_user_settings.return_value = [_user(1), _user(2, city="Lviv")]
        await service.update_all()
        assert [c.kwargs["chat_id"] for c in bot.send_photo.await_args_list] == [2]

    async def test_no_users(self, service: ForecastService, reporter: MagicMock) -> None:
        """
        With no users nothing is requested.

        :param service: The ForecastService under test.
        :param reporter: The mocked WeatherReporter.
        :return: None
        """
        await service.update_all()
        reporter.forecast_image.assert_not_awaited()


class TestDeliver:
    """Tests ForecastService._deliver."""

    async def test_success_sends_new_and_deletes_previous(
        self, service: ForecastService, bot: MagicMock, db: MagicMock, fake_sleep: AsyncMock
    ) -> None:
        """
        A report replaces the previous dialog message.

        A report is sent as a new silent message that becomes the dialog message, the previous one
        is deleted, and the broadcast pauses for its interval.

        :param service: The ForecastService under test.
        :param bot: The mocked Bot.
        :param db: The mocked Database.
        :param fake_sleep: The patched sleep.
        :return: None
        """
        msg = await service._deliver(user=_user(1), photo="file", caption="cap")
        assert msg is not None
        assert msg.message_id == 100
        bot.send_photo.assert_awaited_once()
        assert bot.send_photo.await_args.kwargs["disable_notification"] is True
        bot.edit_message_media.assert_not_awaited()
        db.save_dialog_id.assert_awaited_once_with(user_id=1, dialog_id=100)
        bot.delete_message.assert_awaited_once_with(chat_id=1, message_id=10)
        fake_sleep.assert_awaited_once_with(1 / 25)

    async def test_failed_delete_of_previous_does_not_resend(self, service: ForecastService, bot: MagicMock) -> None:
        """
        A Telegram error while deleting the previous message is only logged.

        The new report is already delivered, so it is neither retried nor sent twice.

        :param service: The ForecastService under test.
        :param bot: The mocked Bot.
        :return: None
        """
        bot.delete_message.side_effect = TelegramNetworkError(method=telegram_method(), message="Request timeout")
        msg = await service._deliver(user=_user(1), photo="file", caption="cap")
        assert msg is not None
        assert msg.message_id == 100
        bot.send_photo.assert_awaited_once()

    async def test_forbidden_deletes_user(self, service: ForecastService, bot: MagicMock, db: MagicMock) -> None:
        """
        A user who blocked the bot is deleted.

        :param service: The ForecastService under test.
        :param bot: The mocked Bot.
        :param db: The mocked Database.
        :return: None
        """
        bot.send_photo.side_effect = TelegramForbiddenError(
            method=telegram_method(), message="Forbidden: bot was blocked by the user"
        )
        assert await service._deliver(user=_user(1), photo="file", caption="cap") is None
        db.delete_user.assert_awaited_once_with(user_id=1)

    async def test_retry_after_then_success(
        self, service: ForecastService, bot: MagicMock, fake_sleep: AsyncMock
    ) -> None:
        """
        Flood control waits the requested time and retries.

        :param service: The ForecastService under test.
        :param bot: The mocked Bot.
        :param fake_sleep: The patched sleep.
        :return: None
        """
        ok = bot.send_photo.return_value
        bot.send_photo.side_effect = [
            TelegramRetryAfter(method=telegram_method(), message="Too Many Requests", retry_after=7),
            ok,
        ]
        assert await service._deliver(user=_user(1), photo="file", caption="cap") is ok
        assert [c.args[0] for c in fake_sleep.await_args_list] == [7, 1 / 25]

    async def test_retry_after_gives_up(self, service: ForecastService, bot: MagicMock, db: MagicMock) -> None:
        """
        After three flood-control refusals the user is skipped (not deleted).

        :param service: The ForecastService under test.
        :param bot: The mocked Bot.
        :param db: The mocked Database.
        :return: None
        """
        bot.send_photo.side_effect = TelegramRetryAfter(
            method=telegram_method(), message="Too Many Requests", retry_after=1
        )
        assert await service._deliver(user=_user(1), photo="file", caption="cap") is None
        assert bot.send_photo.await_count == 3
        db.delete_user.assert_not_awaited()

    async def test_network_error_then_success(
        self, service: ForecastService, bot: MagicMock, fake_sleep: AsyncMock
    ) -> None:
        """
        A dropped connection waits a moment and retries.

        :param service: The ForecastService under test.
        :param bot: The mocked Bot.
        :param fake_sleep: The patched sleep.
        :return: None
        """
        ok = bot.send_photo.return_value
        bot.send_photo.side_effect = [
            TelegramNetworkError(method=telegram_method(), message="ClientOSError: Can not write request body"),
            ok,
        ]
        assert await service._deliver(user=_user(1), photo="file", caption="cap") is ok
        assert [c.args[0] for c in fake_sleep.await_args_list] == [1, 1 / 25]

    async def test_network_error_gives_up(self, service: ForecastService, bot: MagicMock, db: MagicMock) -> None:
        """
        After three network failures the user is skipped (not deleted).

        :param service: The ForecastService under test.
        :param bot: The mocked Bot.
        :param db: The mocked Database.
        :return: None
        """
        bot.send_photo.side_effect = TelegramNetworkError(method=telegram_method(), message="Request timeout error")
        assert await service._deliver(user=_user(1), photo="file", caption="cap") is None
        assert bot.send_photo.await_count == 3
        db.delete_user.assert_not_awaited()

    async def test_other_api_error_is_swallowed(self, service: ForecastService, bot: MagicMock, db: MagicMock) -> None:
        """
        Any other Telegram error skips the user and keeps the previous report.

        :param service: The ForecastService under test.
        :param bot: The mocked Bot.
        :param db: The mocked Database.
        :return: None
        """
        bot.send_photo.side_effect = TelegramBadRequest(method=telegram_method(), message="chat not found")
        assert await service._deliver(user=_user(1), photo="file", caption="cap") is None
        db.delete_user.assert_not_awaited()
        db.save_dialog_id.assert_not_awaited()
        bot.delete_message.assert_not_awaited()
