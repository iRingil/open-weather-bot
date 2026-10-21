"""This module contains handlers of the weather setup dialog."""

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from tgbot.misc.data_types import CityCallback, UnitsCallback
from tgbot.services.dialog import DialogService

__all__: tuple[str] = ("DialogHandler",)


class DialogHandler:
    """The class implements handlers of the weather setup dialog."""

    def __init__(self, service: DialogService) -> None:
        """
        Initialize necessary parameters.

        :param service: DialogService object for business logic.
        """
        self._service: DialogService = service

    async def cmd_start(self, message: Message, state: FSMContext) -> None:
        """
        Handle the '/start' command to start the weather setup.

        :param message: The incoming message from the user.
        :param state: The Finite State Machine (FSM) context for managing user states.
        :return: None
        """
        await self._service.start(message=message, state=state)

    async def msg_city(self, message: Message, state: FSMContext) -> None:
        """
        Handle a city name or a location sent during the weather setup.

        :param message: The incoming message from the user.
        :param state: The Finite State Machine (FSM) context for managing user states.
        :return: None
        """
        await self._service.process_city(message=message, state=state)

    async def call_another_city(self, call: CallbackQuery, state: FSMContext) -> None:
        """
        Handle the 'Select another city' button press.

        :param call: The callback query from the button press.
        :param state: The Finite State Machine (FSM) context for managing user states.
        :return: None
        """
        await call.answer()
        await self._service.select_another_city(call=call, state=state)

    async def call_city(self, call: CallbackQuery, callback_data: CityCallback, state: FSMContext) -> None:
        """
        Handle a city button press.

        :param call: The callback query from the button press.
        :param callback_data: The pressed button's data.
        :param state: The Finite State Machine (FSM) context for managing user states.
        :return: None
        """
        await call.answer()
        await self._service.select_city(call=call, callback_data=callback_data, state=state)

    async def call_units(self, call: CallbackQuery, callback_data: UnitsCallback, state: FSMContext) -> None:
        """
        Handle a measurement units button press.

        :param call: The callback query from the button press.
        :param callback_data: The pressed button's data.
        :param state: The Finite State Machine (FSM) context for managing user states.
        :return: None
        """
        await call.answer()
        await self._service.select_units(call=call, callback_data=callback_data, state=state)

    async def any_delete(self, message: Message) -> None:
        """
        Deletes content sent by a user if the bot should not respond to it.

        :param message: The incoming message from the user.
        :return: None
        """
        await self._service.delete_any(message=message)
