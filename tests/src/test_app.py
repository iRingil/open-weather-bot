"""
Unit tests for src/app.py (Application, main).

Every class/function app.py builds or calls at module level is patched with a MagicMock via the
classes fixture - never a real Telegram/Postgres/network call, and no event loop actually runs.
The application fixture wires this mocks into a real Application, with every awaited method
pre-armed as an AsyncMock. TestMain patches CoreConfig/LoggingManager/Application separately, to
test main()'s own orchestration rather than Application's internals.
"""

# pylint: disable=protected-access

from types import SimpleNamespace
from typing import Iterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import DefaultKeyBuilder
from loguru import logger

import app as app_module

# noinspection PyProtectedMember
from app import Application
from tgbot.misc.data_types import WebhookCredentials

__all__: tuple = ()

_PATCHED_NAMES: tuple[str, ...] = (
    "CoreConfig",
    "Config",
    "Bot",
    "RedisStorage",
    "Dispatcher",
    "AntiFloodMiddleware",
    "TgTemplater",
    "KeyboardManager",
    "Database",
    "HttpClient",
    "WeatherAPI",
    "ForecastImage",
    "WeatherReporter",
    "ForecastService",
    "Scheduler",
    "BotCommands",
    "MainHandler",
    "LoggingManager",
    "AiohttpApp",
    "SimpleRequestHandler",
    "setup_application",
    "run_app",
    "asyncio",
)


@pytest.fixture(name="captured_records")
def captured_records_fixture() -> Iterator[list]:
    """
    Adds a loguru sink that records every emitted record's structured data, regardless of level.

    :return: The list every record loguru receives while this fixture is active gets appended to.
    """
    records: list = []
    sink_id: int = logger.add(sink=lambda message: records.append(message.record), level=0)
    yield records
    logger.remove(sink_id)


@pytest.fixture(name="classes")
def classes_fixture(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """
    Patches every class/function/module app.py constructs or calls at module level with a
    MagicMock, returning them in a namespace keyed by their app.py attribute name.

    :param monkeypatch: pytest fixture used to apply each patch.
    :return: Namespace of the mocked classes/functions/modules.
    """
    mocks: dict[str, MagicMock] = {name: MagicMock() for name in _PATCHED_NAMES}
    for name, value in mocks.items():
        monkeypatch.setattr(target=app_module, name=name, value=value)
    return SimpleNamespace(**mocks)


@pytest.fixture(name="config")
def config_fixture(classes: SimpleNamespace) -> MagicMock:
    """
    The mocked Config instance Application.__init__ receives, with sane defaults (no webhook) so
    tests only need to override what they actually care about. config.redis is left as the
    fixture's own auto-generated MagicMock child - a stand-in for the shared Redis connection,
    which is always present now (see tgbot.config.Config.redis).

    :param classes: The patched-classes fixture.
    :return: The mocked Config instance (classes.Config.return_value).
    """
    config: MagicMock = classes.Config.return_value
    config.token = "fake-token"
    config.admins = [111]
    config.webhook = None
    config.paths.templates = "templates-dir"
    return config


@pytest.fixture(name="core")
def core_fixture() -> MagicMock:
    """
    A mocked CoreConfig, passed explicitly to Application so its core=None branch isn't exercised.

    :return: A fresh mocked CoreConfig instance.
    """
    return MagicMock()


@pytest.fixture(name="application")
def application_fixture(classes: SimpleNamespace, config: MagicMock, core: MagicMock) -> Application:
    """
    A real Application built on the classes/config/core fixtures, with every awaited collaborator
    method pre-armed as an AsyncMock and no bot session to close by default.

    :param classes: The patched-classes fixture.
    :param config: The mocked Config fixture.
    :param core: The mocked CoreConfig fixture.
    :return: The Application instance under test.
    """
    application: Application = Application(core=core)
    classes.Database.return_value.create_tables = AsyncMock()
    classes.Database.return_value.close = AsyncMock()
    classes.BotCommands.return_value.set_commands = AsyncMock()
    classes.Bot.return_value.set_webhook = AsyncMock()
    classes.Bot.return_value.delete_webhook = AsyncMock()
    classes.Bot.return_value.session = None
    classes.Bot.return_value.send_message = AsyncMock()
    classes.Dispatcher.return_value.storage.close = AsyncMock()
    classes.HttpClient.return_value.close = AsyncMock()
    return application


class TestInit:
    """Tests for Application.__init__: wiring every collaborator together."""

    def test_uses_the_given_core_config(
        self, application: Application, core: MagicMock, classes: SimpleNamespace
    ) -> None:
        """
        Passing core explicitly skips building a new CoreConfig.

        :param application: The Application fixture.
        :param core: The mocked CoreConfig fixture, expected to become application._core.
        :param classes: The patched-classes fixture.
        :return: None
        """
        assert application._core is core
        classes.CoreConfig.assert_not_called()

    def test_builds_its_own_core_config_when_none_given(self, classes: SimpleNamespace, config: MagicMock) -> None:
        """
        core=None (the default) builds a fresh CoreConfig instead.

        :param classes: The patched-classes fixture.
        :param config: The mocked Config fixture (unused directly, but needed so Config() resolves).
        :return: None
        """
        application: Application = Application()
        classes.CoreConfig.assert_called_once_with()
        assert application._core is classes.CoreConfig.return_value

    def test_builds_config_from_core(self, application: Application, classes: SimpleNamespace, core: MagicMock) -> None:
        """
        Config is built from the resolved CoreConfig.

        :param application: The Application fixture.
        :param classes: The patched-classes fixture.
        :param core: The mocked CoreConfig fixture.
        :return: None
        """
        classes.Config.assert_called_once_with(core=core)

    def test_constructs_the_bot_with_html_parse_mode(self, application: Application, classes: SimpleNamespace) -> None:
        """
        The bot is built with the config's token and HTML parse mode, replying/link-previews relaxed.

        :param application: The Application fixture.
        :param classes: The patched-classes fixture.
        :return: None
        """
        call_kwargs: dict = classes.Bot.call_args.kwargs
        assert call_kwargs["token"] == "fake-token"
        default: DefaultBotProperties = call_kwargs["default"]
        assert isinstance(default, DefaultBotProperties)
        assert default.parse_mode is ParseMode.HTML
        assert default.allow_sending_without_reply is True
        assert default.link_preview_is_disabled is True

    def test_builds_redis_storage_from_the_shared_connection(
        self, application: Application, classes: SimpleNamespace, config: MagicMock
    ) -> None:
        """
        FSM storage is always Redis-backed now, built from config's shared connection and
        prefixed for this bot - there's no in-memory fallback, since Redis is mandatory
        infrastructure.

        :param application: The Application fixture.
        :param classes: The patched-classes fixture.
        :param config: The mocked Config fixture.
        :return: None
        """
        redis_kwargs: dict = classes.RedisStorage.call_args.kwargs
        assert redis_kwargs["redis"] is config.redis
        assert isinstance(redis_kwargs["key_builder"], DefaultKeyBuilder)
        assert redis_kwargs["key_builder"].prefix == "owb_fsm"
        assert classes.Dispatcher.call_args.kwargs["storage"] is classes.RedisStorage.return_value

    def test_registers_the_antiflood_middleware(self, application: Application, classes: SimpleNamespace) -> None:
        """
        The anti-flood middleware is built and registered as an outer middleware on every update.

        :param application: The Application fixture.
        :param classes: The patched-classes fixture.
        :return: None
        """
        classes.AntiFloodMiddleware.assert_called_once_with()
        classes.Dispatcher.return_value.update.outer_middleware.assert_called_once_with(
            classes.AntiFloodMiddleware.return_value
        )

    def test_wires_every_remaining_collaborator(
        self, application: Application, classes: SimpleNamespace, config: MagicMock, core: MagicMock
    ) -> None:
        """
        TgTemplater/KeyboardManager/Database/HttpClient/WeatherAPI/WeatherReporter/ForecastService/
        Scheduler are all built from the right upstream collaborators.

        :param application: The Application fixture.
        :param classes: The patched-classes fixture.
        :param config: The mocked Config fixture.
        :param core: The mocked CoreConfig fixture.
        :return: None
        """
        classes.TgTemplater.assert_called_once_with(templates_dir=config.paths.templates, locale_dir=core.locale_dir)
        classes.KeyboardManager.assert_called_once_with(tmpl=classes.TgTemplater.return_value)
        classes.Database.assert_called_once_with(pg_config=core.postgres)
        classes.HttpClient.assert_called_once_with()
        classes.WeatherAPI.assert_called_once_with(
            http_client=classes.HttpClient.return_value, token=core.weather_token, db=classes.Database.return_value
        )
        classes.ForecastImage.assert_called_once_with()
        classes.WeatherReporter.assert_called_once_with(
            api=classes.WeatherAPI.return_value,
            image=classes.ForecastImage.return_value,
            tmpl=classes.TgTemplater.return_value,
        )
        classes.ForecastService.assert_called_once_with(
            config=config,
            tmpl=classes.TgTemplater.return_value,
            kb=classes.KeyboardManager.return_value,
            db=classes.Database.return_value,
            bot=classes.Bot.return_value,
            reporter=classes.WeatherReporter.return_value,
        )
        classes.Scheduler.assert_called_once_with(update_weather=classes.ForecastService.return_value.update_all)


class TestOnStartup:
    """Tests for Application._on_startup: tables, bot commands, scheduler, webhook, admin notice."""

    async def test_creates_tables_sets_commands_and_starts_the_scheduler(
        self, application: Application, classes: SimpleNamespace, config: MagicMock
    ) -> None:
        """
        Tables are created, the bot's command list is set, and the scheduler is started.

        :param application: The Application fixture.
        :param classes: The patched-classes fixture.
        :param config: The mocked Config fixture.
        :return: None
        """
        await application._on_startup()
        classes.Database.return_value.create_tables.assert_awaited_once()
        classes.BotCommands.assert_called_once_with(
            bot=application._bot, tmpl_render=application._tmpl, admin_ids=config.admins
        )
        classes.BotCommands.return_value.set_commands.assert_awaited_once()
        classes.Scheduler.return_value.start.assert_called_once()

    async def test_sets_the_webhook_when_configured(
        self, application: Application, classes: SimpleNamespace, config: MagicMock
    ) -> None:
        """
        A configured webhook is registered with the bot, built from the host/path/token.

        :param application: The Application fixture.
        :param classes: The patched-classes fixture.
        :param config: The mocked Config fixture.
        :return: None
        """
        config.webhook = WebhookCredentials(
            wh_host="https://example.com", wh_path="hook", wh_token="secret", app_host="0.0.0.0", app_port=8080
        )
        await application._on_startup()
        classes.Bot.return_value.set_webhook.assert_awaited_once_with(
            url="https://example.com/hook",
            allowed_updates=Application._ALLOWED_UPDATES,
            drop_pending_updates=False,
            secret_token="secret",
        )

    async def test_skips_the_webhook_when_not_configured(
        self, application: Application, classes: SimpleNamespace, config: MagicMock
    ) -> None:
        """
        No webhook configured means the long-polling default is left alone.

        :param application: The Application fixture.
        :param classes: The patched-classes fixture.
        :param config: The mocked Config fixture.
        :return: None
        """
        config.webhook = None
        await application._on_startup()
        classes.Bot.return_value.set_webhook.assert_not_awaited()


class TestOnShutdown:
    """Tests for Application._on_shutdown: webhook teardown, session/storage/http/db close, scheduler stop."""

    async def test_deletes_the_webhook_when_configured(
        self, application: Application, classes: SimpleNamespace, config: MagicMock
    ) -> None:
        """
        A configured webhook is deleted from the bot before shutting down.

        :param application: The Application fixture.
        :param classes: The patched-classes fixture.
        :param config: The mocked Config fixture.
        :return: None
        """
        config.webhook = WebhookCredentials(wh_host="h", wh_path="p", wh_token="t", app_host="0.0.0.0", app_port=1)
        await application._on_shutdown()
        classes.Bot.return_value.delete_webhook.assert_awaited_once()

    async def test_skips_the_webhook_when_not_configured(
        self, application: Application, classes: SimpleNamespace, config: MagicMock
    ) -> None:
        """
        No webhook configured means there's nothing to delete.

        :param application: The Application fixture.
        :param classes: The patched-classes fixture.
        :param config: The mocked Config fixture.
        :return: None
        """
        config.webhook = None
        await application._on_shutdown()
        classes.Bot.return_value.delete_webhook.assert_not_awaited()

    async def test_closes_the_bot_session_when_present(self, application: Application) -> None:
        """
        A live aiohttp session on the bot is closed.

        :param application: The Application fixture.
        :return: None
        """
        application._bot.session = AsyncMock()
        await application._on_shutdown()
        application._bot.session.close.assert_awaited_once()

    async def test_skips_closing_the_session_when_absent(self, application: Application) -> None:
        """
        No live session means nothing is closed, and this doesn't raise.

        :param application: The Application fixture.
        :return: None
        """
        application._bot.session = None  # type: ignore[assignment]
        await application._on_shutdown()

    async def test_closes_storage_http_and_database_and_stops_the_scheduler(
        self, application: Application, classes: SimpleNamespace
    ) -> None:
        """
        FSM storage, the shared HTTP client, and the database are all closed, and the scheduler stops.

        :param application: The Application fixture.
        :param classes: The patched-classes fixture.
        :return: None
        """
        await application._on_shutdown()
        classes.Dispatcher.return_value.storage.close.assert_awaited_once()
        classes.HttpClient.return_value.close.assert_awaited_once()
        classes.Database.return_value.close.assert_awaited_once()
        classes.Scheduler.return_value.shutdown.assert_called_once()

    async def test_stops_the_scheduler_before_closing_shared_connections(
        self, application: Application, classes: SimpleNamespace
    ) -> None:
        """
        The scheduler is stopped (waiting for any in-flight job) before FSM storage, the HTTP
        client, and the database are closed. A still-running job depends on all three, so closing
        them first would pull them out from under it while Scheduler.shutdown(wait=True) is still
        waiting on that same job to finish.

        :param application: The Application fixture.
        :param classes: The patched-classes fixture.
        :return: None
        """
        manager: MagicMock = MagicMock()
        manager.attach_mock(classes.Scheduler.return_value.shutdown, "scheduler_shutdown")
        manager.attach_mock(classes.Dispatcher.return_value.storage.close, "storage_close")
        manager.attach_mock(classes.HttpClient.return_value.close, "http_close")
        manager.attach_mock(classes.Database.return_value.close, "db_close")
        await application._on_shutdown()
        call_names: list[str] = [call[0] for call in manager.mock_calls]
        scheduler_index: int = call_names.index("scheduler_shutdown")
        assert scheduler_index < call_names.index("storage_close")
        assert scheduler_index < call_names.index("http_close")
        assert scheduler_index < call_names.index("db_close")


class TestRun:
    """Tests for Application.run: handler registration, and the webhook/long-polling split."""

    def test_registers_the_main_handler_and_lifecycle_callbacks(
        self, application: Application, classes: SimpleNamespace, config: MagicMock
    ) -> None:
        """
        MainHandler is built from every relevant collaborator, and startup/shutdown are registered.

        :param application: The Application fixture.
        :param classes: The patched-classes fixture.
        :param config: The mocked Config fixture.
        :return: None
        """
        application.run()
        classes.MainHandler.assert_called_once_with(
            config=config,
            dp=application._dp,
            tmpl=application._tmpl,
            kb=application._kb,
            db=application._db,
            api=application._api,
            reporter=application._reporter,
        )
        classes.Dispatcher.return_value.startup.register.assert_called_once_with(callback=application._on_startup)
        classes.Dispatcher.return_value.shutdown.register.assert_called_once_with(callback=application._on_shutdown)

    def test_webhook_mode_runs_the_aiohttp_app_and_returns(
        self, application: Application, classes: SimpleNamespace, config: MagicMock
    ) -> None:
        """
        A configured webhook runs an aiohttp server instead of long polling.

        :param application: The Application fixture.
        :param classes: The patched-classes fixture.
        :param config: The mocked Config fixture.
        :return: None
        """
        config.webhook = WebhookCredentials(
            wh_host="h", wh_path="hook", wh_token="t", app_host="0.0.0.0", app_port=8080
        )
        application.run()
        classes.AiohttpApp.assert_called_once_with()
        classes.SimpleRequestHandler.assert_called_once_with(
            dispatcher=application._dp, bot=application._bot, secret_token="t"
        )
        classes.SimpleRequestHandler.return_value.register.assert_called_once_with(
            classes.AiohttpApp.return_value, path="/hook"
        )
        classes.setup_application.assert_called_once_with(classes.AiohttpApp.return_value, application._dp)
        classes.run_app.assert_called_once_with(app=classes.AiohttpApp.return_value, host="0.0.0.0", port=8080)
        classes.asyncio.run.assert_not_called()

    def test_polling_mode_runs_via_asyncio_run(
        self, application: Application, classes: SimpleNamespace, config: MagicMock
    ) -> None:
        """
        No webhook configured starts long polling through asyncio.run.

        :param application: The Application fixture.
        :param classes: The patched-classes fixture.
        :param config: The mocked Config fixture.
        :return: None
        """
        config.webhook = None
        application.run()
        classes.Dispatcher.return_value.start_polling.assert_called_once_with(
            application._bot, allowed_updates=Application._ALLOWED_UPDATES
        )
        classes.asyncio.run.assert_called_once_with(main=classes.Dispatcher.return_value.start_polling.return_value)
        classes.run_app.assert_not_called()


@pytest.fixture(name="main_classes")
def main_classes_fixture(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """
    Patches CoreConfig/LoggingManager/Application for main()'s own tests - main()'s orchestration
    is what's under test here, not Application's internals (see TestInit/TestOnStartup/etc. above).

    :param monkeypatch: pytest fixture used to apply each patch.
    :return: Namespace of the three mocked names.
    """
    mocks: dict[str, MagicMock] = {"CoreConfig": MagicMock(), "LoggingManager": MagicMock(), "Application": MagicMock()}
    for name, value in mocks.items():
        monkeypatch.setattr(target=app_module, name=name, value=value)
    return SimpleNamespace(**mocks)


class TestMain:
    """Tests for the module-level main(): entry-point wiring and top-level error handling."""

    def test_builds_logging_and_the_application_then_runs_it(self, main_classes: SimpleNamespace) -> None:
        """
        A CoreConfig, LoggingManager, and Application are built in order, then Application.run() runs.

        :param main_classes: The patched CoreConfig/LoggingManager/Application fixture.
        :return: None
        """
        app_module.main()
        core: MagicMock = main_classes.CoreConfig.return_value
        main_classes.LoggingManager.assert_called_once_with(
            debug=core.debug, log_dir=core.log_dir, project_name="open-weather-bot"
        )
        main_classes.Application.assert_called_once_with(core=core)
        main_classes.Application.return_value.run.assert_called_once()

    def test_keyboard_interrupt_is_silently_caught(self, main_classes: SimpleNamespace) -> None:
        """
        A KeyboardInterrupt from run() doesn't propagate out of main().

        :param main_classes: The patched CoreConfig/LoggingManager/Application fixture.
        :return: None
        """
        main_classes.Application.return_value.run.side_effect = KeyboardInterrupt()
        app_module.main()

    def test_system_exit_is_silently_caught(self, main_classes: SimpleNamespace) -> None:
        """
        A SystemExit from run() doesn't propagate out of main().

        :param main_classes: The patched CoreConfig/LoggingManager/Application fixture.
        :return: None
        """
        main_classes.Application.return_value.run.side_effect = SystemExit()
        app_module.main()

    def test_other_exceptions_are_logged_critical_not_raised(
        self, main_classes: SimpleNamespace, captured_records: list
    ) -> None:
        """
        Any other exception from run() is logged at CRITICAL rather than propagating.

        :param main_classes: The patched CoreConfig/LoggingManager/Application fixture.
        :param captured_records: Fixture capturing every record loguru receives.
        :return: None
        """
        main_classes.Application.return_value.run.side_effect = RuntimeError("boom")
        app_module.main()
        assert any(record["level"].name == "CRITICAL" for record in captured_records)

    def test_always_logs_that_the_application_stopped(
        self, main_classes: SimpleNamespace, captured_records: list
    ) -> None:
        """
        The "stopped" message is logged even on a clean run, via the finally block.

        :param main_classes: The patched CoreConfig/LoggingManager/Application fixture.
        :param captured_records: Fixture capturing every record loguru receives.
        :return: None
        """
        app_module.main()
        assert any("Application stopped" in record["message"] for record in captured_records)
