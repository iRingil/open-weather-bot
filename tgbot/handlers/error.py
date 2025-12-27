"""Handles errors."""

from aiogram import Dispatcher
from aiogram.types import Update
from aiogram.utils.exceptions import TelegramAPIError

from tgbot.misc.logger import logger

__all__: tuple[str] = ("register_errors_handlers",)


# pylint: disable=unused-argument
async def _errors_handler(update: Update, exception: TelegramAPIError) -> bool:
    """
    Logs exceptions that have occurred and are not handled by other functions.

    :param update: Aiogram update object.
    :param exception: Telegram exception.
    :return: Always returns True.
    """
    logger.error("Unexpected error while processing the update: %s", repr(exception))
    return True


def register_errors_handlers(dp: Dispatcher) -> None:
    """
    Registers errors handlers.

    :param dp: Aiogram dispatcher object.
    :return: None
    """
    dp.register_errors_handler(callback=_errors_handler)
