"""This module contains base service classes for shared functionality."""

from asyncio import sleep

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardMarkup,
    InputFile,
    InputMediaPhoto,
    Message,
    PhotoSize,
    ReplyKeyboardMarkup,
    User,
)
from loguru import logger

from core.db.repository import Database
from core.tg_templater import TgTemplater
from tgbot.config import Config
from tgbot.misc.keyboards import KeyboardManager

__all__: tuple[str, ...] = ("BaseService", "PhotoSource")

PhotoSource = InputFile | str  # A file to upload, or the file_id of one Telegram already has

_NOT_MODIFIED: str = "message is not modified"


class BaseService:
    """
    Base service class with shared functionality for other services.

    Every user has a single live "dialog message" (users.dialog_id): a photo whose caption and
    inline keyboard change at every step, so the whole dialog stays in one window. Telegram never
    lets a bot delete its messages older than 48 hours and refuses edits of messages that are gone,
    so failing to edit or delete one is an expected situation, not an error: the helpers below fall
    back to sending a new dialog message (and only log the failure at DEBUG level).

    :cvar _DEFAULT_LOCALE: Locale used when Telegram doesn't report the user's language.
    :cvar _logo_file_id: file_id of the bot logo once uploaded, shared by every service, so the
        logo is uploaded to Telegram only once per process.
    """

    _DEFAULT_LOCALE: str = "en"
    _logo_file_id: str | None = None

    def __init__(self, config: Config, tmpl: TgTemplater, kb: KeyboardManager, db: Database) -> None:
        """
        Initialize shared dependencies for services.

        :param config: Config object with configuration settings.
        :param tmpl: TgTemplater object for rendering templates.
        :param kb: KeyboardManager object for keyboard generation.
        :param db: Database instance.
        """
        self._config: Config = config
        self._tmpl: TgTemplater = tmpl
        self._kb: KeyboardManager = kb
        self._db: Database = db

    # region Private methods
    @classmethod
    def _locale(cls, user: User | None) -> str:
        """
        Returns the language code of a user.

        :param user: Telegram user, if known.
        :return: ISO 639-1 language code reported by Telegram, or the default locale.
        """
        return user.language_code if user is not None and user.language_code else cls._DEFAULT_LOCALE

    def _logo(self) -> PhotoSource:
        """
        Returns the bot logo, by file_id if it was already uploaded.

        :return: The bot logo.
        """
        return BaseService._logo_file_id or FSInputFile(path=self._config.paths.bot_logo)

    @staticmethod
    def _remember_logo(sent: PhotoSource, message: Message) -> None:
        """
        Remembers the logo's file_id once Telegram has it.

        :param sent: The photo that was just sent.
        :param message: The message it was sent in.
        :return: None
        """
        sizes: list[PhotoSize] | None = message.photo
        if isinstance(sent, FSInputFile) and sizes and BaseService._logo_file_id is None:
            BaseService._logo_file_id = sizes[-1].file_id

    @staticmethod
    async def _delete_msg(bot: Bot, chat_id: int, msg_id: int | None) -> None:
        """
        Deletes a message, if Telegram still allows it.

        :param bot: The bot instance.
        :param chat_id: The chat ID.
        :param msg_id: The message ID, or None to do nothing.
        :return: None
        """
        if msg_id is None:
            return
        try:
            await bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except TelegramBadRequest as e:  # Older than 48 hours, or already gone
            logger.debug(f"Message {msg_id} in chat {chat_id} was not deleted: {e.message}")

    async def _delete_user_msg(self, message: Message) -> None:
        """
        Deletes a message sent by the user, if Telegram still allows it.

        :param message: The message to delete.
        :return: None
        """
        bot: Bot | None = message.bot
        if bot is not None:
            await self._delete_msg(bot=bot, chat_id=message.chat.id, msg_id=message.message_id)

    async def _send_photo(
        self,
        bot: Bot,
        chat_id: int,
        caption: str,
        photo: PhotoSource | None = None,
        reply_markup: InlineKeyboardMarkup | ReplyKeyboardMarkup | None = None,
    ) -> Message:
        """
        Sends a photo message.

        :param bot: The bot instance.
        :param chat_id: The chat ID.
        :param caption: Photo caption.
        :param photo: The photo, or None for the bot logo.
        :param reply_markup: The keyboard markup to include (optional).
        :return: The sent message.
        """
        photo = photo or self._logo()
        msg: Message = await bot.send_photo(
            chat_id=chat_id, photo=photo, caption=caption, reply_markup=reply_markup, disable_notification=True
        )
        self._remember_logo(sent=photo, message=msg)
        return msg

    async def _replace_dialog(
        self,
        bot: Bot,
        chat_id: int,
        old_msg_id: int | None,
        caption: str,
        reply_markup: InlineKeyboardMarkup | ReplyKeyboardMarkup | None = None,
    ) -> Message:
        """
        Sends a new dialog message (with the bot logo) and deletes the previous one.

        Needed instead of an edit whenever the step shows a reply keyboard - Telegram can only
        attach those to a new message.

        :param bot: The bot instance.
        :param chat_id: The chat ID.
        :param old_msg_id: ID of the previous dialog message, or None.
        :param caption: Caption of the new dialog message.
        :param reply_markup: The keyboard markup to include (optional).
        :return: The new dialog message.
        """
        msg: Message = await self._send_photo(bot=bot, chat_id=chat_id, caption=caption, reply_markup=reply_markup)
        await self._db.save_dialog_id(user_id=chat_id, dialog_id=msg.message_id)
        if old_msg_id != msg.message_id:
            await self._delete_msg(bot=bot, chat_id=chat_id, msg_id=old_msg_id)
        return msg

    # pylint: disable=too-many-arguments
    async def _edit_or_send_msg(
        self,
        bot: Bot,
        chat_id: int,
        msg_id: int | None,
        caption: str,
        photo: PhotoSource | None = None,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> Message | None:
        """
        Edit the dialog message if possible, otherwise send a new one and make it the dialog message.

        :param bot: The bot instance.
        :param chat_id: The chat ID to send the message to.
        :param msg_id: The message ID to edit, or None if there is none.
        :param caption: The new caption.
        :param photo: The new photo, or None to keep the current one (a new message then gets the
            bot logo).
        :param reply_markup: The inline keyboard to include (optional).
        :return: The edited message, a new one, or None if the content was unchanged.
        """
        if msg_id is not None:
            # 1. Trying to edit an existing message, if it does not exist anymore, the try will fail
            try:
                result: Message | bool
                if photo is None:
                    result = await bot.edit_message_caption(
                        chat_id=chat_id, message_id=msg_id, caption=caption, reply_markup=reply_markup
                    )
                else:
                    result = await bot.edit_message_media(
                        chat_id=chat_id,
                        message_id=msg_id,
                        media=InputMediaPhoto(media=photo, caption=caption),
                        reply_markup=reply_markup,
                    )
                if not isinstance(result, Message):
                    return None
                if photo is not None:
                    self._remember_logo(sent=photo, message=result)
                return result
            # 2. If the message doesn't exist or has the same content:
            except TelegramBadRequest as e:
                # 2.1 If the message as same as a current content, do nothing
                if _NOT_MODIFIED in e.message:
                    return None
                logger.debug(f"Message {msg_id} in chat {chat_id} was not edited: {e.message}")
        # 2.2 If the message can't be edited, send a new one and drop the old one if Telegram allows
        msg: Message = await self._send_photo(
            bot=bot, chat_id=chat_id, caption=caption, photo=photo, reply_markup=reply_markup
        )
        await self._db.save_dialog_id(user_id=chat_id, dialog_id=msg.message_id)
        await self._delete_msg(bot=bot, chat_id=chat_id, msg_id=msg_id)
        return msg

    async def _edit_or_send_callback(
        self,
        call: CallbackQuery,
        caption: str,
        photo: PhotoSource | None = None,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> Message | None:
        """
        Edit the message a callback came from if possible, otherwise send a new dialog message.

        The callback itself must already be answered by the caller.

        :param call: The callback query to edit the message of.
        :param caption: The new caption.
        :param photo: The new photo, or None to keep the current one.
        :param reply_markup: The inline keyboard to include (optional).
        :return: The edited message, a new one, or None if the content was unchanged.
        """
        msg_id: int | None = (
            call.message.message_id
            if isinstance(call.message, Message)
            else await self._db.get_dialog_id(user_id=call.from_user.id)
        )
        return await self._edit_or_send_msg(
            bot=call.bot,  # type: ignore [arg-type]
            chat_id=call.from_user.id,
            msg_id=msg_id,
            caption=caption,
            photo=photo,
            reply_markup=reply_markup,
        )

    async def _send_temporary(self, bot: Bot, chat_id: int, caption: str, delay: float) -> None:
        """
        Sends a message with the bot logo and deletes it after a delay.

        :param bot: The bot instance.
        :param chat_id: The chat ID.
        :param caption: Photo caption.
        :param delay: Seconds before the message is deleted.
        :return: None
        """
        msg: Message = await self._send_photo(bot=bot, chat_id=chat_id, caption=caption)
        await sleep(delay)
        await self._delete_msg(bot=bot, chat_id=chat_id, msg_id=msg.message_id)

    # endregion
