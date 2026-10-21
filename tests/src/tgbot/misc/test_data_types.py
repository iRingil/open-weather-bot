"""
Unit tests for src/tgbot/misc/data_types.py (CityCallback, UnitsCallback) and
src/tgbot/misc/fsm_states.py (WeatherSetupStates).
"""

import pytest

from core.db.data_types import Units
from tgbot.misc.data_types import CityCallback, UnitsCallback
from tgbot.misc.fsm_states import WeatherSetupStates

__all__: tuple = ()


class TestCityCallback:
    """Tests CityCallback packing."""

    def test_round_trip(self) -> None:
        """
        A city button carries only its index, and unpacks back to it.

        :return: None
        """
        packed: str = CityCallback(index=4).pack()
        assert packed == "city:4"
        assert CityCallback.unpack(packed).index == 4


class TestUnitsCallback:
    """Tests UnitsCallback packing."""

    @pytest.mark.parametrize("units", list(Units))
    def test_round_trip(self, units: Units) -> None:
        """
        The units survive packing as their database value.

        :param units: Measurement units.
        :return: None
        """
        packed: str = UnitsCallback(units=units).pack()
        assert packed == f"units:{units.value}"
        assert UnitsCallback.unpack(packed).units is units

    def test_fits_telegram_limit(self) -> None:
        """
        Every packed callback stays under Telegram's 64-byte limit.

        :return: None
        """
        for packed in (CityCallback(index=99).pack(), *(UnitsCallback(units=u).pack() for u in Units)):
            assert len(packed.encode()) <= 64


class TestWeatherSetupStates:
    """Tests WeatherSetupStates."""

    def test_states(self) -> None:
        """
        The dialog has three distinct, group-qualified states.

        :return: None
        """
        assert [state.state for state in WeatherSetupStates.__all_states__] == [  # pylint: disable=no-member
            "WeatherSetupStates:wait_for_city",
            "WeatherSetupStates:wait_for_city_choice",
            "WeatherSetupStates:wait_for_units",
        ]
