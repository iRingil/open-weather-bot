"""Main program module."""

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, UpdateType
from aiogram.fsm.storage.redis import DefaultKeyBuilder, RedisStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp.web import Application as AiohttpApp, run_app
from loguru import logger

from core.config import CoreConfig
from core.db.repository import Database
from core.http_client import HttpClient
from core.log_setup import LoggingManager
from core.scheduler import Scheduler
from core.tg_templater import TgTemplater
from tgbot.config import Config
from tgbot.handlers.main import MainHandler
from tgbot.misc.bot_commands import BotCommands
from tgbot.misc.data_types import WebhookCredentials
from tgbot.misc.keyboards import KeyboardManager
from tgbot.misc.middlewares import AntiFloodMiddleware
from tgbot.services.forecast import ForecastService
from weather.client import WeatherAPI
from weather.image import ForecastImage
from weather.reporter import WeatherReporter

__all__: tuple = ()


class Application:
    """
    The main class that wires up and runs every subsystem of the application.

    :cvar _ALLOWED_UPDATES: Update types Telegram is allowed to send - both webhook and polling
        mode are restricted to these, so nothing the bot doesn't act on ever reaches it.
    """

    _ALLOWED_UPDATES: list[str] = [UpdateType.MESSAGE, UpdateType.CALLBACK_QUERY]

    def __init__(self, core: CoreConfig | None = None) -> None:
        """
        Initializes the necessary parameters.

        :param core: CoreConfig instance to use. Constructs its own if not given (e.g. when
            logging didn't need to be set up before this - see main(), which builds one early).
        """
        self._core: CoreConfig = core or CoreConfig()
        self._config: Config = Config(core=self._core)
        self._bot: Bot = Bot(
            token=self._config.token,
            default=DefaultBotProperties(
                parse_mode=ParseMode.HTML, allow_sending_without_reply=True, link_preview_is_disabled=True
            ),
        )
        storage: RedisStorage = RedisStorage(redis=self._config.redis, key_builder=DefaultKeyBuilder(prefix="owb_fsm"))
        self._dp: Dispatcher = Dispatcher(storage=storage)
        self._dp.update.outer_middleware(AntiFloodMiddleware())
        self._tmpl: TgTemplater = TgTemplater(
            templates_dir=self._config.paths.templates, locale_dir=self._core.locale_dir
        )
        self._kb: KeyboardManager = KeyboardManager(tmpl=self._tmpl)
        self._db: Database = Database(pg_config=self._core.postgres)
        self._http: HttpClient = HttpClient()
        self._api: WeatherAPI = WeatherAPI(http_client=self._http, token=self._core.weather_token, db=self._db)
        self._reporter: WeatherReporter = WeatherReporter(api=self._api, image=ForecastImage(), tmpl=self._tmpl)
        self._forecast: ForecastService = ForecastService(
            config=self._config, tmpl=self._tmpl, kb=self._kb, db=self._db, bot=self._bot, reporter=self._reporter
        )
        self._scheduler: Scheduler = Scheduler(update_weather=self._forecast.update_all)

    async def _on_startup(self) -> None:
        """
        Runs when the bot starts.

        :return: None
        """
        await self._db.create_tables()
        bot_commands: BotCommands = BotCommands(bot=self._bot, tmpl_render=self._tmpl, admin_ids=self._config.admins)
        await bot_commands.set_commands()
        self._scheduler.start()

        webhook: WebhookCredentials | None = self._config.webhook
        if webhook:
            await self._bot.set_webhook(
                url=f"{webhook.wh_host}/{webhook.wh_path}",
                allowed_updates=self._ALLOWED_UPDATES,
                drop_pending_updates=False,
                secret_token=webhook.wh_token,
            )

    async def _on_shutdown(self) -> None:
        """
        Runs when the bot is stopped.

        Stops the scheduler first, waiting for an in-flight weather update to finish
        (Scheduler.shutdown's default wait=True) before closing anything it might still be using -
        FSM storage (Redis), the shared HTTP client, and the database.

        :return: None
        """
        self._scheduler.shutdown()
        if self._config.webhook:
            await self._bot.delete_webhook()
        if self._bot.session is not None:
            await self._bot.session.close()
        await self._dp.storage.close()
        await self._http.close()
        await self._db.close()

    def run(self) -> None:
        """
        Runs the bot - via webhook if configured (see tgbot.config.Config.webhook), otherwise via long polling.

        :return: None
        """
        MainHandler(
            config=self._config,
            dp=self._dp,
            tmpl=self._tmpl,
            kb=self._kb,
            db=self._db,
            api=self._api,
            reporter=self._reporter,
        )
        self._dp.startup.register(callback=self._on_startup)
        self._dp.shutdown.register(callback=self._on_shutdown)
        webhook: WebhookCredentials | None = self._config.webhook
        if webhook:
            web_app: AiohttpApp = AiohttpApp()
            SimpleRequestHandler(dispatcher=self._dp, bot=self._bot, secret_token=webhook.wh_token).register(
                web_app, path=f"/{webhook.wh_path}"
            )
            setup_application(web_app, self._dp)
            run_app(app=web_app, host=webhook.app_host, port=webhook.app_port)
            return
        asyncio.run(main=self._dp.start_polling(self._bot, allowed_updates=self._ALLOWED_UPDATES))


def main() -> None:
    """
    Entry point: sets up logging, then builds and runs the Application.

    :return: None
    """
    core: CoreConfig = CoreConfig()
    LoggingManager(debug=core.debug, log_dir=core.log_dir, project_name="open-weather-bot")
    logger.info("Starting application")
    application: Application = Application(core=core)
    try:
        application.run()
    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception as exc:
        logger.critical(f"Unhandled error: {repr(exc)}")
    finally:
        logger.info("Application stopped!")


if __name__ == "__main__":  # pragma: no cover
    main()
