"""Plain data types for the tgbot package."""

from pathlib import Path
from typing import NamedTuple

from aiogram.filters.callback_data import CallbackData

from core.db.data_types import Units

__all__: tuple[str, ...] = ("CityCallback", "Paths", "UnitsCallback", "WebhookCredentials")


class Paths(NamedTuple):
    """
    A class to represent paths to folders and files used in the program.

    :param bot_logo: Path to the file containing the bot logo.
    :param templates: Path to the folder containing Jinja2 templates.
    """

    bot_logo: Path
    templates: Path


class WebhookCredentials(NamedTuple):
    """
    Credentials and local bind address for running the bot via webhook instead of long polling.

    :param wh_host: Public HTTPS host Telegram sends updates to, e.g. "https://example.com".
    :param wh_path: URL path Telegram posts updates to, appended to wh_host.
    :param wh_token: Secret token Telegram echoes back in the X-Telegram-Bot-Api-Secret-Token
        header on every request - checked to reject requests not actually from Telegram.
    :param app_host: Local address the aiohttp server binds to, e.g. "0.0.0.0".
    :param app_port: Local port the aiohttp server binds to.
    """

    wh_host: str
    wh_path: str
    wh_token: str
    app_host: str
    app_port: int


class CityCallback(CallbackData, prefix="city"):
    """
    Callback data of a city button.

    The found cities themselves are kept in the FSM data, so a button only carries its index
    (Telegram limits callback data to 64 bytes, too short for a city name with its coordinates).

    :param index: Index of the city in the FSM data's list of found cities.
    """

    index: int


class UnitsCallback(CallbackData, prefix="units"):
    """
    Callback data of a measurement units button.

    :param units: Selected measurement units.
    """

    units: Units
