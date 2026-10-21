"""Builders shared by the tgbot tests."""

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

from aiogram import Bot
from aiogram.methods import TelegramMethod
from aiogram.types import CallbackQuery, Chat, Location, Message, PhotoSize, User

__all__: tuple[str, ...] = ("USER_ID", "make_call", "make_message", "telegram_method")

USER_ID: int = 222


def make_message(
    message_id: int = 1,
    text: str | None = None,
    photo_id: str | None = None,
    location: Location | None = None,
    language_code: str | None = "ru",
    bot: Bot | None = None,
) -> Message:
    """
    Builds a real private-chat Message, optionally bound to a (mocked) bot.

    :param message_id: Message ID.
    :param text: Message text.
    :param photo_id: file_id of a photo attached to the message, if any.
    :param location: Location attached to the message, if any.
    :param language_code: Sender's language code.
    :param bot: Bot to bind the message to, so message.bot works.
    :return: The Message instance.
    """
    photo: list[PhotoSize] | None = None
    if photo_id is not None:
        photo = [
            PhotoSize(file_id="small", file_unique_id="s", width=90, height=22),
            PhotoSize(file_id=photo_id, file_unique_id="b", width=799, height=199),
        ]
    message: Message = Message(
        message_id=message_id,
        date=datetime.now(tz=timezone.utc),
        chat=Chat(id=USER_ID, type="private"),
        from_user=User(id=USER_ID, is_bot=False, first_name="Test", language_code=language_code),
        text=text,
        photo=photo,
        location=location,
    )
    return message.as_(bot) if bot is not None else message


def make_call(bot: Bot, message: Any = None, data: str = "x", language_code: str | None = "ru") -> CallbackQuery:
    """
    Builds a real CallbackQuery bound to a (mocked) bot.

    :param bot: Bot to bind the callback query to.
    :param message: The message the button belongs to (Message, InaccessibleMessage or None).
    :param data: Callback data.
    :param language_code: Sender's language code.
    :return: The CallbackQuery instance.
    """
    return CallbackQuery(
        id="1",
        from_user=User(id=USER_ID, is_bot=False, first_name="Test", language_code=language_code),
        chat_instance="x",
        message=message,
        data=data,
    ).as_(bot)


def telegram_method() -> TelegramMethod[Any]:
    """
    Returns a stand-in for the TelegramMethod an aiogram exception carries.

    :return: A mock method.
    """
    return MagicMock(spec=TelegramMethod)
