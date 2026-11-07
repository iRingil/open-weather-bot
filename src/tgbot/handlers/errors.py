"""Handler of errors that are not caught by other functions."""

from typing import override

from aiogram.handlers import BaseHandler
from aiogram.types import ErrorEvent

from tgbot.services.errors import ErrService

__all__: tuple[str] = ("ErrHandler",)


class ErrHandler(BaseHandler[ErrorEvent]):
    """
    Class for errors handlers that are not caught by other functions.

    Based on BaseHandler[ErrorEvent], not the aiogram ErrorHandler: that one is typed as
    BaseHandler[Exception], while error handlers actually receive an ErrorEvent.
    """

    @override
    async def handle(self) -> None:
        """
        Delegates handling of an exception not caught by other functions to ErrService.

        :return: None
        """
        await ErrService.log_exception(event=self.event)
