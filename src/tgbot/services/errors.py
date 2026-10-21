"""This module contains business logic for handling exceptions not caught by other functions."""

from aiogram.types import CallbackQuery, ErrorEvent, Message
from loguru import logger

__all__: tuple[str] = ("ErrService",)


class ErrService:
    """The class implements business logic for logging unhandled exceptions."""

    @staticmethod
    async def log_exception(event: ErrorEvent) -> None:
        """
        Logs an exception that was not handled by other functions.

        :param event: The error event carrying the raised exception and the update that triggered it.
        :return: None
        """
        if isinstance(event.update.message, Message):
            msg_or_call_from_user: str = f", Message: {event.update.message.text}"
        elif isinstance(event.update.callback_query, CallbackQuery):
            msg_or_call_from_user = f", Callback: {event.update.callback_query.data}"
        else:
            msg_or_call_from_user = ""
        logger.error(f"Exception while handling an update: {event.exception} {msg_or_call_from_user}")
