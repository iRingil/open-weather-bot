"""Functions for sending scheduled weather data."""

from asyncio import sleep
from datetime import timezone
from os import remove as os_remove
from pathlib import Path

from aiogram import Dispatcher
from aiogram.types import InputFile, Message
from aiogram.utils.exceptions import BotBlocked, RetryAfter, UserDeactivated
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from tgbot.services.database import User, database
from tgbot.services.weather import weather

__all__: tuple[str] = ("schedule",)


async def _update_weather_data(dp: Dispatcher) -> None:
    """
    Updates weather data for all users.

    :param dp: Aiogram dispatcher object.
    :return: None
    """
    users: list[User] = await database.get_list_all_users()
    for user in users:
        weather_forecast: Path = await weather.get_weather_forecast(user_id=user.id)
        current_weather: str = await weather.get_current_weather(user_id=user.id)
        try:
            dialog: Message = await dp.bot.send_photo(
                chat_id=user.id,
                photo=InputFile(path_or_bytesio=weather_forecast),
                caption=current_weather,
                disable_notification=True,
            )
            await database.save_dialog_id(user_id=user.id, dialog_id=dialog.message_id)
        except (BotBlocked, UserDeactivated):
            await database.delete_user(user_id=user.id)
        except RetryAfter as exc:
            await sleep(delay=exc.timeout)
            dialog = await dp.bot.send_photo(
                chat_id=user.id,
                photo=InputFile(path_or_bytesio=weather_forecast),
                caption=current_weather,
                disable_notification=True,
            )
            await database.save_dialog_id(user_id=user.id, dialog_id=dialog.message_id)
        finally:
            await dp.bot.delete_message(chat_id=user.id, message_id=user.dialog_id)
            if not str(weather_forecast).endswith("bot_logo.png"):
                os_remove(weather_forecast)


async def schedule(dp: Dispatcher) -> None:
    """
    Creates a weather update task in the scheduler.

    :param dp: Aiogram dispatcher object.
    :return: None
    """
    scheduler: AsyncIOScheduler = AsyncIOScheduler(timezone=timezone.utc)
    scheduler.add_job(func=_update_weather_data, trigger="cron", hour="*/3", args=(dp,))
    scheduler.start()
