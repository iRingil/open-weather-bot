"""This module contains business logic of the '/about' and '/stop' commands."""

from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from tgbot.services.common import BaseService

__all__: tuple[str] = ("CommandsService",)


class CommandsService(BaseService):
    """
    The class implements the '/about' and '/stop' commands.

    :cvar _msg_about: Path to the bot info template.
    :cvar _msg_data_deleted: Path to the "data deleted" template.
    :cvar _ABOUT_TTL: Seconds the bot info stays in the chat.
    :cvar _DATA_DELETED_TTL: Seconds the "data deleted" notice stays in the chat.
    """

    _msg_about: str = "tgbot/commands/msg_about.jinja2"
    _msg_data_deleted: str = "tgbot/commands/msg_data_deleted.jinja2"
    _ABOUT_TTL: float = 15
    _DATA_DELETED_TTL: float = 5

    async def about(self, message: Message) -> None:
        """
        Shows the bot info for a while.

        :param message: The '/about' message.
        :return: None
        """
        await self._delete_user_msg(message=message)
        await self._send_temporary(
            bot=message.bot,  # type: ignore [arg-type]
            chat_id=message.chat.id,
            caption=await self._tmpl.render(tmpl=self._msg_about, locale=self._locale(user=message.from_user)),
            delay=self._ABOUT_TTL,
        )

    async def stop(self, message: Message, state: FSMContext) -> None:
        """
        Deletes the user's data and dialog message, which also stops the scheduled updates.

        :param message: The '/stop' message.
        :param state: The FSM context of the user.
        :return: None
        """
        await state.clear()
        await self._delete_user_msg(message=message)
        bot: Bot = message.bot  # type: ignore [assignment]
        user_id: int = message.chat.id
        await self._delete_msg(bot=bot, chat_id=user_id, msg_id=await self._db.get_dialog_id(user_id=user_id))
        await self._db.delete_user(user_id=user_id)
        await self._send_temporary(
            bot=bot,
            chat_id=user_id,
            caption=await self._tmpl.render(tmpl=self._msg_data_deleted, locale=self._locale(user=message.from_user)),
            delay=self._DATA_DELETED_TTL,
        )
