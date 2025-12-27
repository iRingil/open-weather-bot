"""Allows to perform actions if the user is an administrator."""

from aiogram.dispatcher.filters import BoundFilter
from aiogram.types import CallbackQuery, Message

from tgbot.config import Config


__all__: tuple[str] = ("AdminFilter",)


class AdminFilter(BoundFilter):
    """Allows to define administrators."""

    key: str = "is_admin"

    def __init__(self, is_admin: bool | None = None) -> None:
        """
        Initializes the filter.

        :param is_admin: True if the user is an administrator, False otherwise.
        """
        self.is_admin = is_admin

    async def check(self, obj: Message | CallbackQuery) -> bool:
        """
        Checks if the user is an administrator

        :param obj: Message or CallbackQuery object from bot user.
        :return: True if the user is an administrator, False otherwise.
        """
        if self.is_admin is None:
            return False
        config: Config = obj.bot.get("config")
        return (obj.from_user.id in config.tg_bot.admin_ids) == self.is_admin
