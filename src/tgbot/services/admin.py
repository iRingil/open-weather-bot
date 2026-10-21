"""This module contains business logic for admin-related functionality."""

from aiogram.types import Message

from tgbot.services.common import BaseService

__all__: tuple[str] = ("AdminService",)


class AdminService(BaseService):
    """
    The class implements the admin statistics.

    :cvar _msg_stats: Path to the statistics template.
    :cvar _API_MONTHLY_LIMIT: OpenWeatherMap free plan's monthly request limit.
    :cvar _STATS_TTL: Seconds the statistics stay in the chat.
    """

    _msg_stats: str = "tgbot/admin/msg_stats.jinja2"
    _API_MONTHLY_LIMIT: int = 1_000_000
    _STATS_TTL: float = 15

    async def stats(self, message: Message) -> None:
        """
        Shows the API usage and user count for a while.

        :param message: The '/stats' message.
        :return: None
        """
        await self._delete_user_msg(message=message)
        api_counter: int = await self._db.get_api_counter_value()
        data: dict[str, int] = {
            "api_counter": api_counter,
            "api_limit": self._API_MONTHLY_LIMIT,
            "percent": round(api_counter / self._API_MONTHLY_LIMIT * 100),
            "users": await self._db.get_number_of_users(),
        }
        await self._send_temporary(
            bot=message.bot,  # type: ignore [arg-type]
            chat_id=message.chat.id,
            caption=await self._tmpl.render(
                tmpl=self._msg_stats, locale=self._locale(user=message.from_user), data=data
            ),
            delay=self._STATS_TTL,
        )
