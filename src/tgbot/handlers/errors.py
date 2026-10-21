"""Handler of errors that are not caught by other functions."""

from aiogram.handlers import ErrorHandler
from aiogram.types import ErrorEvent

from tgbot.services.errors import ErrService

__all__: tuple[str] = ("ErrHandler",)


class ErrHandler(ErrorHandler):
    """Class for errors handlers that are not caught by other functions."""

    async def handle(self) -> None:
        """
        Delegates handling of an exception not caught by other functions to ErrService.

        :return: None
        """
        event: ErrorEvent = self.event  # type: ignore[assignment]
        await ErrService.log_exception(event=event)
