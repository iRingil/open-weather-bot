"""Describes the state for the FSM (Final State Machine)."""

from aiogram.fsm.state import State, StatesGroup

__all__: tuple[str] = ("WeatherSetupStates",)


class WeatherSetupStates(StatesGroup):
    """
    A group of states of the weather setup dialog.

    :cvar wait_for_city: The state where the bot waits for a city name or a location.
    :cvar wait_for_city_choice: The state where the bot waits for the user to pick one of the found cities.
    :cvar wait_for_units: The state where the bot waits for the user to pick the measurement units.
    """

    wait_for_city: State = State()
    wait_for_city_choice: State = State()
    wait_for_units: State = State()
