"""This module contains handlers for admin-related functionality."""

from aiogram.types import Message

from tgbot.services.admin import AdminService

__all__: tuple[str] = ("AdminHandler",)


class AdminHandler:
    """The class implements handlers for admin-related user interactions."""

    def __init__(self, service: AdminService) -> None:
        """
        Initialize necessary parameters.

        :param service: AdminService object for business logic.
        """
        self._service: AdminService = service

    async def cmd_stats(self, message: Message) -> None:
        """
        Handle the '/stats' command to show the bot statistics.

        :param message: The incoming message from the user.
        :return: None
        """
        await self._service.stats(message=message)
