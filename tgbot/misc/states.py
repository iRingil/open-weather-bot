"""Describes the state for the FSM (Final State Machine)."""

from aiogram.dispatcher.filters.state import StatesGroup, State

__all__: tuple[str] = ("WeatherSetupDialog",)


class WeatherSetupDialog(StatesGroup):
    """Describes the state of the weather setup dialog."""

    EnterCityName = State()
