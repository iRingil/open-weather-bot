"""This module contains event handlers registration for the bot."""

from aiogram import Dispatcher, F, Router
from aiogram.enums import ContentType
from aiogram.filters import Command

from core.db.repository import Database
from core.tg_templater import TgTemplater
from tgbot.config import Config
from tgbot.handlers.admin import AdminHandler
from tgbot.handlers.commands import CommandsHandler
from tgbot.handlers.dialog import DialogHandler
from tgbot.handlers.errors import ErrHandler
from tgbot.misc.data_types import CityCallback, UnitsCallback
from tgbot.misc.filters import UserIsAdmin
from tgbot.misc.fsm_states import WeatherSetupStates
from tgbot.misc.keyboards import KeyboardManager
from tgbot.services.admin import AdminService
from tgbot.services.commands import CommandsService
from tgbot.services.dialog import DialogService
from weather.client import WeatherAPI
from weather.reporter import WeatherReporter

__all__: tuple[str] = ("MainHandler",)


class MainHandler:
    """Registers event handlers for the bot."""

    # pylint: disable=too-many-arguments
    def __init__(
        self,
        config: Config,
        dp: Dispatcher,
        tmpl: TgTemplater,
        kb: KeyboardManager,
        db: Database,
        api: WeatherAPI,
        reporter: WeatherReporter,
    ) -> None:
        """
        Initialize necessary parameters and handlers.

        :param config: Config object with configuration settings.
        :param dp: Aiogram Dispatcher object for handling events.
        :param tmpl: TgTemplater object for rendering templates.
        :param kb: KeyboardManager object for keyboard generation.
        :param db: Database instance, used by the services.
        :param api: OpenWeatherMap API client.
        :param reporter: Weather report builder.
        """
        self._dp: Dispatcher = dp
        self._user_is_admin: UserIsAdmin = UserIsAdmin(admins_ids=config.admins)

        # region Initialize services
        self._admin_svc: AdminService = AdminService(config=config, tmpl=tmpl, kb=kb, db=db)
        self._commands_svc: CommandsService = CommandsService(config=config, tmpl=tmpl, kb=kb, db=db)
        self._dialog_svc: DialogService = DialogService(
            config=config, tmpl=tmpl, kb=kb, db=db, api=api, reporter=reporter
        )
        # endregion

        # region Initialize handlers
        self._admin_hdlr: AdminHandler = AdminHandler(service=self._admin_svc)
        self._commands_hdlr: CommandsHandler = CommandsHandler(service=self._commands_svc)
        self._dialog_hdlr: DialogHandler = DialogHandler(service=self._dialog_svc)
        # endregion

        self._register_handlers()

    def _register_handlers(self) -> None:
        """
        Register event and error handlers for the bot.

        THE ORDER HANDLERS ARE REGISTERED IN IS CRITICAL TO THE BOT WORKING CORRECTLY.

        :return: None
        """
        pr: Router = Router(name="Private chat")
        pr.message.filter(F.chat.type == "private")  # Filter for handling messages in private chats only
        self._dp.include_router(router=pr)

        # region Commands handlers - work in any state
        pr.message.register(self._dialog_hdlr.cmd_start, Command(commands=["start"]))
        pr.message.register(self._commands_hdlr.cmd_about, Command(commands=["about"]))
        pr.message.register(self._commands_hdlr.cmd_stop, Command(commands=["stop"]))
        pr.message.register(self._admin_hdlr.cmd_stats, Command(commands=["stats"]), self._user_is_admin)
        # endregion

        # region Weather setup dialog handlers
        pr.message.register(
            self._dialog_hdlr.msg_city,
            WeatherSetupStates.wait_for_city,
            F.content_type.in_({ContentType.TEXT, ContentType.LOCATION, ContentType.VENUE}),
        )
        # Buttons work in any state: an outdated one is handled inside the service
        pr.callback_query.register(self._dialog_hdlr.call_another_city, F.data == "another_city")
        pr.callback_query.register(self._dialog_hdlr.call_city, CityCallback.filter())
        pr.callback_query.register(self._dialog_hdlr.call_units, UnitsCallback.filter())
        # endregion

        # region Delete unhandled messages
        pr.message.register(self._dialog_hdlr.any_delete)
        # endregion

        # region Error handler
        pr.errors.register(ErrHandler)
        # endregion
