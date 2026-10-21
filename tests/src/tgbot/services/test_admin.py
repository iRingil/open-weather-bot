"""
Unit tests for src/tgbot/services/admin.py (AdminService).

Bot, Database, TgTemplater and KeyboardManager are autospecced mocks (see ../conftest.py).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tgbot.services.admin import AdminService

from ..helpers import make_message

__all__: tuple = ()


@pytest.fixture(name="service")
def service_fixture(config: MagicMock, tmpl: MagicMock, kb: MagicMock, db: MagicMock) -> AdminService:
    """
    An AdminService over the mocked dependencies.

    :param config: The mocked Config.
    :param tmpl: The mocked TgTemplater.
    :param kb: The mocked KeyboardManager.
    :param db: The mocked Database.
    :return: The AdminService under test.
    """
    return AdminService(config=config, tmpl=tmpl, kb=kb, db=db)


class TestStats:
    """Tests AdminService.stats."""

    @pytest.mark.parametrize(("counter", "percent"), [(0, 0), (123_456, 12), (995_000, 100)])
    async def test_renders_usage(
        self,
        service: AdminService,
        bot: MagicMock,
        db: MagicMock,
        tmpl: MagicMock,
        counter: int,
        percent: int,
    ) -> None:
        """
        The statistics show the monthly API usage against the 1M limit (rounded percent) and
        the user count, then disappear after 15 seconds.

        :param service: The AdminService under test.
        :param bot: The mocked Bot.
        :param db: The mocked Database.
        :param tmpl: The mocked TgTemplater.
        :param counter: API requests this month.
        :param percent: Expected percent of the limit.
        :return: None
        """
        db.get_api_counter_value.return_value = counter
        db.get_number_of_users.return_value = 42
        with patch("tgbot.services.common.sleep", new=AsyncMock()) as fake_sleep:
            await service.stats(message=make_message(message_id=7, text="/stats", bot=bot))
        tmpl.render.assert_awaited_once_with(
            tmpl="tgbot/admin/msg_stats.jinja2",
            locale="ru",
            data={"api_counter": counter, "api_limit": 1_000_000, "percent": percent, "users": 42},
        )
        fake_sleep.assert_awaited_once_with(15)
        assert [c.kwargs["message_id"] for c in bot.delete_message.await_args_list] == [7, 100]
