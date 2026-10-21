"""
Unit tests for src/tgbot/services/common.py (BaseService).

Bot, Database, TgTemplater and KeyboardManager are autospecced mocks (see conftest.py) - nothing
reaches Telegram or Postgres. Telegram's refusals are simulated with real aiogram exceptions.
"""

# pylint: disable=protected-access

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BufferedInputFile, FSInputFile, InaccessibleMessage, InputMediaPhoto, Chat, Message, User

from tgbot.services.common import BaseService
from tests.src.tgbot.helpers import USER_ID, make_call, make_message, telegram_method

__all__: tuple = ()


@pytest.fixture(name="service")
def service_fixture(config: MagicMock, tmpl: MagicMock, kb: MagicMock, db: MagicMock) -> BaseService:
    """
    A BaseService over the mocked dependencies.

    :param config: The mocked Config.
    :param tmpl: The mocked TgTemplater.
    :param kb: The mocked KeyboardManager.
    :param db: The mocked Database.
    :return: The BaseService under test.
    """
    return BaseService(config=config, tmpl=tmpl, kb=kb, db=db)


def _bad_request(text: str) -> TelegramBadRequest:
    """
    Builds a TelegramBadRequest with the given message.

    :param text: Telegram's error description.
    :return: The exception.
    """
    return TelegramBadRequest(method=telegram_method(), message=text)


class TestLocale:
    """Tests BaseService._locale."""

    def test_returns_language_code(self) -> None:
        """
        The user's Telegram language code is used as is.

        :return: None
        """
        assert BaseService._locale(User(id=1, is_bot=False, first_name="T", language_code="uk")) == "uk"

    @pytest.mark.parametrize("user", [None, User(id=1, is_bot=False, first_name="T")])
    def test_falls_back_to_default(self, user: User | None) -> None:
        """
        No user, or no language code, falls back to English.

        :param user: The user, or None.
        :return: None
        """
        assert BaseService._locale(user) == "en"


class TestLogo:
    """Tests BaseService._logo / _remember_logo."""

    def test_uploads_file_until_remembered(self, service: BaseService, config: MagicMock) -> None:
        """
        Without a cached file_id the logo is an FSInputFile of the configured path; once a sent
        message with it is remembered, its largest photo's file_id is used instead.

        :param service: The BaseService under test.
        :param config: The mocked Config.
        :return: None
        """
        logo = service._logo()
        assert isinstance(logo, FSInputFile)
        assert logo.path == config.paths.bot_logo
        service._remember_logo(photo=logo, message=make_message(photo_id="logo_id"))
        assert service._logo() == "logo_id"

    def test_does_not_remember_other_photos_or_overwrite(self, service: BaseService) -> None:
        """
        Only an uploaded FSInputFile is remembered, and only the first time.

        :param service: The BaseService under test.
        :return: None
        """
        service._remember_logo(photo=BufferedInputFile(b"x", "f.png"), message=make_message(photo_id="forecast"))
        service._remember_logo(photo="file_id", message=make_message(photo_id="other"))
        service._remember_logo(photo=service._logo(), message=make_message(text="no photo"))
        assert BaseService._logo_file_id is None
        service._remember_logo(photo=service._logo(), message=make_message(photo_id="first"))
        service._remember_logo(photo=FSInputFile("x"), message=make_message(photo_id="second"))
        assert BaseService._logo_file_id == "first"


class TestDeleteMsg:
    """Tests BaseService._delete_msg / _delete_user_msg."""

    async def test_deletes(self, bot: MagicMock) -> None:
        """
        A message ID is deleted through the bot.

        :param bot: The mocked Bot.
        :return: None
        """
        await BaseService._delete_msg(bot=bot, chat_id=USER_ID, msg_id=5)
        bot.delete_message.assert_awaited_once_with(chat_id=USER_ID, message_id=5)

    async def test_none_does_nothing(self, bot: MagicMock) -> None:
        """
        A None message ID makes no request.

        :param bot: The mocked Bot.
        :return: None
        """
        await BaseService._delete_msg(bot=bot, chat_id=USER_ID, msg_id=None)
        bot.delete_message.assert_not_awaited()

    async def test_swallows_bad_request(self, bot: MagicMock) -> None:
        """
        Telegram refusing the deletion (48 hours passed) is not an error.

        :param bot: The mocked Bot.
        :return: None
        """
        bot.delete_message.side_effect = _bad_request("message can't be deleted for everyone")
        await BaseService._delete_msg(bot=bot, chat_id=USER_ID, msg_id=5)

    async def test_delete_user_msg(self, service: BaseService, bot: MagicMock) -> None:
        """
        The user's message is deleted in its own chat; a message without a bot is skipped.

        :param service: The BaseService under test.
        :param bot: The mocked Bot.
        :return: None
        """
        await service._delete_user_msg(message=make_message(message_id=7, bot=bot))
        bot.delete_message.assert_awaited_once_with(chat_id=USER_ID, message_id=7)
        await service._delete_user_msg(message=make_message(message_id=8))
        assert bot.delete_message.await_count == 1


class TestSendPhoto:
    """Tests BaseService._send_photo."""

    async def test_sends_logo_by_default_and_remembers_it(self, service: BaseService, bot: MagicMock) -> None:
        """
        Without a photo the logo is sent silently, and its file_id is cached.

        :param service: The BaseService under test.
        :param bot: The mocked Bot.
        :return: None
        """
        msg: Message = await service._send_photo(bot=bot, chat_id=USER_ID, caption="cap", reply_markup="kb")
        assert msg.message_id == 100
        kwargs = bot.send_photo.await_args.kwargs
        assert isinstance(kwargs["photo"], FSInputFile)
        assert kwargs == {**kwargs, "chat_id": USER_ID, "caption": "cap", "reply_markup": "kb"}
        assert kwargs["disable_notification"] is True
        assert BaseService._logo_file_id == "sent"

    async def test_sends_given_photo(self, service: BaseService, bot: MagicMock) -> None:
        """
        A given photo is sent instead of the logo.

        :param service: The BaseService under test.
        :param bot: The mocked Bot.
        :return: None
        """
        await service._send_photo(bot=bot, chat_id=USER_ID, caption="cap", photo="file")
        assert bot.send_photo.await_args.kwargs["photo"] == "file"
        assert BaseService._logo_file_id is None


class TestReplaceDialog:
    """Tests BaseService._replace_dialog."""

    async def test_sends_saves_and_deletes_old(self, service: BaseService, bot: MagicMock, db: MagicMock) -> None:
        """
        A new logo message is sent, saved as the dialog message, and the old one deleted.

        :param service: The BaseService under test.
        :param bot: The mocked Bot.
        :param db: The mocked Database.
        :return: None
        """
        msg: Message = await service._replace_dialog(
            bot=bot, chat_id=USER_ID, old_msg_id=50, caption="cap", reply_markup="geo"
        )
        assert msg.message_id == 100
        assert bot.send_photo.await_args.kwargs["reply_markup"] == "geo"
        db.save_dialog_id.assert_awaited_once_with(user_id=USER_ID, dialog_id=100)
        bot.delete_message.assert_awaited_once_with(chat_id=USER_ID, message_id=50)

    async def test_does_not_delete_the_new_message(self, service: BaseService, bot: MagicMock) -> None:
        """
        If the old ID equals the new one, nothing is deleted.

        :param service: The BaseService under test.
        :param bot: The mocked Bot.
        :return: None
        """
        await service._replace_dialog(bot=bot, chat_id=USER_ID, old_msg_id=100, caption="cap")
        bot.delete_message.assert_not_awaited()


class TestEditOrSendMsg:
    """Tests BaseService._edit_or_send_msg."""

    async def test_caption_only_edit(self, service: BaseService, bot: MagicMock, db: MagicMock) -> None:
        """
        With no photo, only the caption and keyboard are edited.

        :param service: The BaseService under test.
        :param bot: The mocked Bot.
        :param db: The mocked Database.
        :return: None
        """
        msg = await service._edit_or_send_msg(bot=bot, chat_id=USER_ID, msg_id=50, caption="cap", reply_markup="kb")
        assert msg is not None and msg.message_id == 50
        bot.edit_message_caption.assert_awaited_once_with(
            chat_id=USER_ID, message_id=50, caption="cap", reply_markup="kb"
        )
        bot.edit_message_media.assert_not_awaited()
        bot.send_photo.assert_not_awaited()
        db.save_dialog_id.assert_not_awaited()

    async def test_media_edit(self, service: BaseService, bot: MagicMock) -> None:
        """
        With a photo, the media is replaced and the caption goes with it.

        :param service: The BaseService under test.
        :param bot: The mocked Bot.
        :return: None
        """
        msg = await service._edit_or_send_msg(bot=bot, chat_id=USER_ID, msg_id=50, caption="cap", photo="file_id")
        assert msg is not None and msg.message_id == 50
        kwargs = bot.edit_message_media.await_args.kwargs
        assert kwargs["media"] == InputMediaPhoto(media="file_id", caption="cap")
        assert kwargs["message_id"] == 50
        bot.edit_message_caption.assert_not_awaited()

    async def test_media_edit_remembers_logo(self, service: BaseService, bot: MagicMock) -> None:
        """
        Editing the media to the uploaded logo caches its file_id.

        :param service: The BaseService under test.
        :param bot: The mocked Bot.
        :return: None
        """
        await service._edit_or_send_msg(bot=bot, chat_id=USER_ID, msg_id=50, caption="cap", photo=service._logo())
        assert BaseService._logo_file_id == "edited"

    async def test_non_message_result_returns_none(self, service: BaseService, bot: MagicMock) -> None:
        """
        A bare True result (inline messages) returns None.

        :param service: The BaseService under test.
        :param bot: The mocked Bot.
        :return: None
        """
        bot.edit_message_caption.return_value = True
        assert await service._edit_or_send_msg(bot=bot, chat_id=USER_ID, msg_id=50, caption="cap") is None

    async def test_not_modified_returns_none_without_sending(self, service: BaseService, bot: MagicMock) -> None:
        """
        "message is not modified" is a no-op: no new message.

        :param service: The BaseService under test.
        :param bot: The mocked Bot.
        :return: None
        """
        bot.edit_message_caption.side_effect = _bad_request(
            "Bad Request: message is not modified: specified new message content and reply markup are exactly the same"
        )
        assert await service._edit_or_send_msg(bot=bot, chat_id=USER_ID, msg_id=50, caption="cap") is None
        bot.send_photo.assert_not_awaited()

    async def test_other_bad_request_sends_new(self, service: BaseService, bot: MagicMock, db: MagicMock) -> None:
        """
        Any other refusal sends a new message (same photo), saves it as the dialog message and
        tries to delete the old one.

        :param service: The BaseService under test.
        :param bot: The mocked Bot.
        :param db: The mocked Database.
        :return: None
        """
        bot.edit_message_media.side_effect = _bad_request("Bad Request: message to edit not found")
        msg = await service._edit_or_send_msg(
            bot=bot, chat_id=USER_ID, msg_id=50, caption="cap", photo="file_id", reply_markup="kb"
        )
        assert msg is not None and msg.message_id == 100
        bot.send_photo.assert_awaited_once_with(
            chat_id=USER_ID, photo="file_id", caption="cap", reply_markup="kb", disable_notification=True
        )
        db.save_dialog_id.assert_awaited_once_with(user_id=USER_ID, dialog_id=100)
        bot.delete_message.assert_awaited_once_with(chat_id=USER_ID, message_id=50)

    async def test_no_msg_id_sends_directly(self, service: BaseService, bot: MagicMock, db: MagicMock) -> None:
        """
        Without a dialog message, a new one (with the logo) is sent right away.

        :param service: The BaseService under test.
        :param bot: The mocked Bot.
        :param db: The mocked Database.
        :return: None
        """
        msg = await service._edit_or_send_msg(bot=bot, chat_id=USER_ID, msg_id=None, caption="cap")
        assert msg is not None and msg.message_id == 100
        bot.edit_message_caption.assert_not_awaited()
        assert isinstance(bot.send_photo.await_args.kwargs["photo"], FSInputFile)
        db.save_dialog_id.assert_awaited_once_with(user_id=USER_ID, dialog_id=100)
        bot.delete_message.assert_not_awaited()


class TestEditOrSendCallback:
    """Tests BaseService._edit_or_send_callback."""

    async def test_edits_the_callback_message(self, service: BaseService, bot: MagicMock, db: MagicMock) -> None:
        """
        The message the button belongs to is the one edited.

        :param service: The BaseService under test.
        :param bot: The mocked Bot.
        :param db: The mocked Database.
        :return: None
        """
        call = make_call(bot=bot, message=make_message(message_id=33, photo_id="p"))
        await service._edit_or_send_callback(call=call, caption="cap", reply_markup="kb")
        bot.edit_message_caption.assert_awaited_once_with(
            chat_id=USER_ID, message_id=33, caption="cap", reply_markup="kb"
        )
        db.get_dialog_id.assert_not_awaited()

    async def test_inaccessible_message_uses_dialog_id(
        self, service: BaseService, bot: MagicMock, db: MagicMock
    ) -> None:
        """
        An inaccessible callback message falls back to the stored dialog message ID.

        :param service: The BaseService under test.
        :param bot: The mocked Bot.
        :param db: The mocked Database.
        :return: None
        """
        inaccessible = InaccessibleMessage(chat=Chat(id=USER_ID, type="private"), message_id=9)
        call = make_call(bot=bot, message=inaccessible)
        await service._edit_or_send_callback(call=call, caption="cap", photo="file")
        db.get_dialog_id.assert_awaited_once_with(user_id=USER_ID)
        assert bot.edit_message_media.await_args.kwargs["message_id"] == 50


class TestSendTemporary:
    """Tests BaseService._send_temporary."""

    async def test_sends_waits_and_deletes(self, service: BaseService, bot: MagicMock) -> None:
        """
        The message is sent, then deleted after the delay.

        :param service: The BaseService under test.
        :param bot: The mocked Bot.
        :return: None
        """
        with patch("tgbot.services.common.sleep", new=AsyncMock()) as fake_sleep:
            await service._send_temporary(bot=bot, chat_id=USER_ID, caption="cap", delay=15)
        fake_sleep.assert_awaited_once_with(15)
        bot.send_photo.assert_awaited_once()
        bot.delete_message.assert_awaited_once_with(chat_id=USER_ID, message_id=100)
