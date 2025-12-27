"""Launches the bot."""

from aiogram import Bot, Dispatcher
from aiogram.types import ParseMode
from aiogram.utils.executor import start_webhook
from aiohttp import ClientSession

from tgbot.config import Config, load_config
from tgbot.filters.admin import AdminFilter
from tgbot.handlers.admin import register_admin_handlers
from tgbot.handlers.commands import register_other_handlers
from tgbot.handlers.dialog import register_dialog_handlers
from tgbot.handlers.error import register_errors_handlers
from tgbot.middlewares.localization import i18n
from tgbot.misc.commands import set_default_commands
from tgbot.misc.logger import logger
from tgbot.misc.scheduler import schedule
from tgbot.services.database import database

__all__: tuple = ()


def _register_all_middlewares(dp: Dispatcher) -> None:
    """
    Registers middlewares.

    :param dp: Aiogram dispatcher instance.
    :return: None
    """
    dp.middleware.setup(i18n)


def _register_all_filters(dp: Dispatcher) -> None:
    """
    Registers filters.

    :param dp: Aiogram dispatcher instance.
    :return: None
    """
    dp.filters_factory.bind(callback=AdminFilter)


def _register_all_handlers(dp: Dispatcher) -> None:
    """
    Registers handlers.

    :param dp: Aiogram dispatcher instance.
    :return: None
    """
    register_admin_handlers(dp=dp)
    register_other_handlers(dp=dp)
    register_dialog_handlers(dp=dp)
    register_errors_handlers(dp=dp)


def main() -> None:
    """
    Launches the bot.

    :return: None
    """
    config: Config = load_config()
    bot: Bot = Bot(token=config.tg_bot.token, parse_mode=ParseMode.HTML)
    dp: Dispatcher = Dispatcher(bot=bot, storage=config.storage)
    bot["config"] = config

    _register_all_middlewares(dp=dp)
    _register_all_filters(dp=dp)
    _register_all_handlers(dp=dp)

    async def on_startup(dp_: Dispatcher) -> None:
        """
        Performs actions on bot startup.

        :param dp_: Aiogram dispatcher instance.
        :return: None
        """
        await database.create_tables()
        await set_default_commands(dp=dp_)
        await schedule(dp=dp_)
        await bot.set_webhook(
            url=f"{config.tg_bot.webhook.wh_host}/{config.tg_bot.webhook.wh_path}",
            secret_token=config.tg_bot.webhook.wh_token,
        )

    async def on_shutdown(dp_: Dispatcher) -> None:
        """
        Performs actions on bot shutdown.

        :param dp_: Aiogram dispatcher instance.
        :return: None
        """
        await dp_.storage.close()
        await dp_.storage.wait_closed()
        await database.close()
        session: ClientSession = await bot.get_session()
        await session.close()

    start_webhook(
        dispatcher=dp,
        webhook_path=f"/{config.tg_bot.webhook.wh_path}",
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        skip_updates=True,
        host=config.tg_bot.webhook.app_host,
        port=config.tg_bot.webhook.app_port,
    )


if __name__ == "__main__":
    logger.info("Starting bot")
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception as exc:
        logger.critical("Unknown error: %s", exc)
    logger.info("Bot stopped!")
