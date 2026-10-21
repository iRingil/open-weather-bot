"""This module contains the scheduled weather update of every user."""

from asyncio import sleep
from collections import defaultdict
from typing import NamedTuple

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import BufferedInputFile, Message, PhotoSize
from loguru import logger

from core.db.data_types import Units, UserSettings
from core.db.repository import Database
from core.decorators import handle_exc
from core.tg_templater import TgTemplater
from tgbot.config import Config
from tgbot.misc.keyboards import KeyboardManager
from tgbot.services.common import BaseService, PhotoSource
from weather.data_types import CurrentWeatherData
from weather.reporter import WeatherReporter

__all__: tuple[str] = ("ForecastService",)


class _Location(NamedTuple):
    """
    Users sharing a location and units get the same forecast image.

    :param latitude: Latitude.
    :param longitude: Longitude.
    :param units: Measurement units.
    """

    latitude: float
    longitude: float
    units: Units


class ForecastService(BaseService):
    """
    Updates the dialog message of every user with a fresh weather report.

    Users are grouped so that nothing is requested from OpenWeatherMap twice: the forecast (and
    its image) once per location and units, the current weather once per location, units and
    language. The image is uploaded to Telegram once per location too - every next user of the
    same location gets it by file_id. Only the caption, which shows each user's own city name, is
    rendered per user.

    A location whose forecast or current weather couldn't be obtained (the request failed, or a
    required field of the response is missing) is skipped, so its users keep their previous
    report rather than an error message. A report missing only optional fields is still sent.

    :cvar _SEND_INTERVAL: Pause after every delivery, keeping under Telegram's broadcast limits.
    :cvar _MAX_ATTEMPTS: Attempts to deliver to one user when Telegram asks to retry later.
    """

    _SEND_INTERVAL: float = 1 / 25
    _MAX_ATTEMPTS: int = 3

    # pylint: disable=too-many-arguments
    def __init__(
        self,
        config: Config,
        tmpl: TgTemplater,
        kb: KeyboardManager,
        db: Database,
        bot: Bot,
        reporter: WeatherReporter,
    ) -> None:
        """
        Initialize the service.

        :param config: Config object with configuration settings.
        :param tmpl: TgTemplater object for rendering templates.
        :param kb: KeyboardManager object for keyboard generation.
        :param db: Database instance.
        :param bot: The bot instance.
        :param reporter: Weather report builder.
        """
        super().__init__(config=config, tmpl=tmpl, kb=kb, db=db)
        self._bot: Bot = bot
        self._reporter: WeatherReporter = reporter

    async def update_all(self) -> None:
        """
        Sends a fresh weather report to every user who finished the setup.

        :return: None
        """
        users: list[UserSettings] = await self._db.get_all_user_settings()
        locations: dict[_Location, list[UserSettings]] = defaultdict(list)
        for user in users:
            locations[_Location(latitude=user.latitude, longitude=user.longitude, units=user.units)].append(user)
        logger.info(f"Weather update started: {len(users)} users, {len(locations)} locations")
        for location, location_users in locations.items():
            await self._update_location(location=location, users=location_users)
        logger.info("Weather update finished")

    @handle_exc
    async def _update_location(self, location: _Location, users: list[UserSettings]) -> None:
        """
        Sends a fresh weather report to every user of one location.

        :param location: The location and units.
        :param users: Users of this location.
        :return: None
        """
        image: bytes | None = await self._reporter.forecast_image(
            latitude=location.latitude, longitude=location.longitude, units=location.units
        )
        if image is None:
            logger.warning(f"No forecast for {location}, {len(users)} users keep their previous report")
            return
        media: PhotoSource = BufferedInputFile(file=image, filename="forecast.png")
        by_lang: dict[str, list[UserSettings]] = defaultdict(list)
        for user in users:
            by_lang[user.lang].append(user)
        for lang, lang_users in by_lang.items():
            current: CurrentWeatherData | None = await self._reporter.current_weather(
                latitude=location.latitude, longitude=location.longitude, lang=lang, units=location.units
            )
            if current is None:
                logger.warning(
                    f"No current weather for {location} ({lang}), {len(lang_users)} users keep their previous report"
                )
                continue
            for user in lang_users:
                caption: str = await self._reporter.caption(
                    current=current, city=user.city, units=location.units, lang=lang
                )
                msg: Message | None = await self._deliver(user=user, photo=media, caption=caption)
                sizes: list[PhotoSize] | None = msg.photo if msg is not None else None
                if sizes and not isinstance(media, str):
                    media = sizes[-1].file_id  # Uploaded once, reused for the rest of the location

    async def _deliver(self, user: UserSettings, photo: PhotoSource, caption: str) -> Message | None:
        """
        Puts a weather report into one user's dialog message.

        A user who blocked the bot (or whose account is gone) is deleted, as there is no way to
        reach them anymore.

        :param user: The user.
        :param photo: Forecast image.
        :param caption: Current weather caption.
        :return: The updated or new dialog message, or None if nothing was delivered.
        """
        for _ in range(self._MAX_ATTEMPTS):
            try:
                msg: Message | None = await self._edit_or_send_msg(
                    bot=self._bot, chat_id=user.user_id, msg_id=user.dialog_id, caption=caption, photo=photo
                )
                await sleep(self._SEND_INTERVAL)
                return msg
            except TelegramRetryAfter as e:
                logger.warning(f"Flood control while updating user {user.user_id}, retrying in {e.retry_after}s")
                await sleep(e.retry_after)
            except TelegramForbiddenError as e:
                logger.info(f"User {user.user_id} is unreachable ({e.message}), deleting")
                await self._db.delete_user(user_id=user.user_id)
                return None
            except TelegramAPIError as e:
                logger.warning(f"Failed to update user {user.user_id}: {e.message}")
                return None
        return None
