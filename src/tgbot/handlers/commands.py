"""This module contains handlers of the '/about' and '/stop' commands."""

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from tgbot.services.commands import CommandsService

__all__: tuple[str] = ("CommandsHandler",)


class CommandsHandler:
    """The class implements handlers of the '/about' and '/stop' commands."""

    def __init__(self, service: CommandsService) -> None:
        """
        Initialize necessary parameters.

        :param service: CommandsService object for business logic.
        """
        self._service: CommandsService = service

    async def cmd_about(self, message: Message) -> None:
        """
        Handle the '/about' command to show the bot info.

        :param message: The incoming message from the user.
        :return: None
        """
        await self._service.about(message=message)

    async def cmd_stop(self, message: Message, state: FSMContext) -> None:
        """
        Handle the '/stop' command to delete the user's data.

        :param message: The incoming message from the user.
        :param state: The Finite State Machine (FSM) context for managing user states.
        :return: None
        """
        await self._service.stop(message=message, state=state)
