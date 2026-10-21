"""
Unit tests for src/tgbot/misc/filters.py (UserIsAdmin).

Message/CallbackQuery are built as real aiogram objects (both are cheap pydantic models with no
methods that would reach Telegram) rather than mocks, since the filter only ever reads
.from_user off them.
"""

from datetime import datetime
from aiogram.types import CallbackQuery, Chat, Message, User

from tgbot.misc.filters import UserIsAdmin

__all__: tuple = ()


def _make_message(user_id: int | None) -> Message:
    """
    Builds a real Message, with a real User as its sender or none at all.

    :param user_id: ID to give the sender, or None to simulate a message with no resolvable sender
        (e.g. a channel post).
    :return: A Message usable as the "obj" argument to either filter.
    """
    from_user: User | None = User(id=user_id, is_bot=False, first_name="Test") if user_id is not None else None
    return Message(message_id=1, date=datetime.now(), chat=Chat(id=1, type="private"), from_user=from_user)


def _make_callback_query(user_id: int) -> CallbackQuery:
    """
    Builds a real CallbackQuery - unlike Message, it's from_user is never optional.

    :param user_id: ID to give the sender.
    :return: A CallbackQuery usable as the "obj" argument to either filter.
    """
    return CallbackQuery(id="1", from_user=User(id=user_id, is_bot=False, first_name="Test"), chat_instance="x")


class TestUserIsAdmin:
    """Tests UserIsAdmin: whether the sender's ID is in the configured admin list."""

    async def test_returns_true_for_an_admin_sender(self) -> None:
        """
        A message from a user ID in admins_ids passes the filter.

        :return: None
        """
        is_admin: UserIsAdmin = UserIsAdmin(admins_ids=[111, 222])
        assert await is_admin(_make_message(user_id=111)) is True

    async def test_returns_false_for_a_non_admin_sender(self) -> None:
        """
        A message from a user ID not in admins_ids fails the filter.

        :return: None
        """
        is_admin: UserIsAdmin = UserIsAdmin(admins_ids=[111, 222])
        assert await is_admin(_make_message(user_id=333)) is False

    async def test_returns_false_when_the_sender_cant_be_identified(self) -> None:
        """
        A message with no resolvable sender (from_user=None) fails the filter, rather than raising.

        :return: None
        """
        is_admin: UserIsAdmin = UserIsAdmin(admins_ids=[111])
        assert await is_admin(_make_message(user_id=None)) is False

    async def test_works_for_a_callback_query_too(self) -> None:
        """
        The filter applies the same admins_ids check to a CallbackQuery, not just a Message.

        :return: None
        """
        is_admin: UserIsAdmin = UserIsAdmin(admins_ids=[111])
        assert await is_admin(_make_callback_query(user_id=111)) is True
        assert await is_admin(_make_callback_query(user_id=999)) is False
