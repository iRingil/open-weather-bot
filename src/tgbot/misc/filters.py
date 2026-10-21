"""The module contains various filters that can be used in handlers."""

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

__all__: tuple[str] = ("UserIsAdmin",)


class UserIsAdmin(BaseFilter):
    """The filter allows you to determine if the sender of the message is a bot admin."""

    def __init__(self, admins_ids: list[int]) -> None:
        """
        Initialize the filter.

        :param admins_ids: List of Bot admin IDs.
        """
        super().__init__()
        self.admins_ids: list[int] = admins_ids

    async def __call__(self, obj: CallbackQuery | Message) -> bool:
        """
        Returns True if the sender of the message or callback query is a bot administrator.

        :param obj: CallbackQuery | Message object.
        :return: True if the sender of the message or callback query is a bot administrator.
        """
        return obj.from_user is not None and obj.from_user.id in self.admins_ids
