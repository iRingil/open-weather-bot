"""Message handlers for administrators"""

from asyncio import sleep

from aiogram import Dispatcher
from aiogram.types import InputFile, Message

from tgbot.config import BOT_LOGO
from tgbot.middlewares.localization import i18n
from tgbot.services.database import database

__all__: tuple[str] = ("register_admin_handlers",)

_ = i18n.gettext  # Alias for gettext method


async def _if_admin_sent_command_stats(message: Message) -> None:
    """
    Shows statistics for administrators.

    :param message: Message object from bot user.
    :return: None
    """
    await message.delete()
    user_lang_code: str = message.from_user.language_code
    api_counter: int = await database.get_api_counter_value()
    users_counter: int = await database.get_number_of_users()
    bot_answer_text: str = (
        "ℹ️ <b>"
        + _("Statistics", locale=user_lang_code)
        + ":</b>\n\n• "
        + _("Since beginning of the month", locale=user_lang_code)
        + f",\n  <b>{round((api_counter / 1000000) * 100)} %</b>"
        + _("requests have been spent", locale=user_lang_code)
        + ":\n  <b>"
        + f"{api_counter:_}".replace("_", " ")
        + "</b> "
        + _("out of", locale=user_lang_code)
        + " <b>1 000 000</b>\n\n• "
        + _("Users in the database", locale=user_lang_code)
        + f": <b>{users_counter}</b>"
    )
    bot_answer: Message = await message.answer_photo(photo=InputFile(path_or_bytesio=BOT_LOGO), caption=bot_answer_text)
    await sleep(delay=15)
    await message.bot.delete_message(chat_id=bot_answer.chat.id, message_id=bot_answer.message_id)


def register_admin_handlers(dp: Dispatcher) -> None:
    """
    Registers admin handlers.

    :param dp: Aiogram dispatcher instance.
    :return: None
    """
    dp.register_message_handler(callback=_if_admin_sent_command_stats, commands="stats", state="*", is_admin=True)
