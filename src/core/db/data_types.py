"""Typed data structures mirroring rows of the users table.

Kept in their own module, separate from the query layer, so a type can be imported without
pulling in the query layer itself.
"""

from enum import StrEnum
from typing import NamedTuple

__all__: tuple[str, ...] = ("Units", "UserSettings")


class Units(StrEnum):
    """Possible values of users.units - also the OpenWeatherMap 'units' request parameter."""

    METRIC = "metric"
    IMPERIAL = "imperial"


class UserSettings(NamedTuple):
    """
    A user who completed the weather setup dialog.

    :param user_id: Telegram user id.
    :param dialog_id: ID of the user's single live dialog message.
    :param lang: ISO 639-1 language code the user had when finishing the setup.
    :param city: Name of the selected city.
    :param latitude: Latitude of the selected city.
    :param longitude: Longitude of the selected city.
    :param units: Measurement units.
    """

    user_id: int
    dialog_id: int
    lang: str
    city: str
    latitude: float
    longitude: float
    units: Units
