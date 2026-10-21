"""The module presents a function that changes the default list of commands for the bot."""

from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeAllGroupChats, BotCommandScopeAllPrivateChats, BotCommandScopeChat

from core.tg_templater import TgTemplater

__all__: tuple[str] = ("BotCommands",)


class BotCommands:
    """
    The class provides a function that changes the default list of commands for the bot.

    :cvar _cmd_start: Path to the template for the '/start' command.
    :cvar _cmd_about: Path to the template for the '/about' command.
    :cvar _cmd_stop: Path to the template for the '/stop' command.
    :cvar _cmd_stats: Path to the template for the admin '/stats' command.
    :cvar _DEFAULT_LOCALE: Locale of the commands shown to users whose language has no translation.
    """

    _cmd_start: str = "tgbot/commands/cmd_start.jinja2"
    _cmd_about: str = "tgbot/commands/cmd_about.jinja2"
    _cmd_stop: str = "tgbot/commands/cmd_stop.jinja2"
    _cmd_stats: str = "tgbot/admin/cmd_stats.jinja2"
    _DEFAULT_LOCALE: str = "en"

    def __init__(self, bot: Bot, tmpl_render: TgTemplater, admin_ids: list[int]) -> None:
        """
        Initializes the BotCommands class with the necessary parameters.

        :param bot: Bot instance.
        :param tmpl_render: TgTemplater instance for rendering templates.
        :param admin_ids: List of admin user IDs.
        """
        self._bot: Bot = bot
        self._tmpl: TgTemplater = tmpl_render
        self._admin_ids: list[int] = admin_ids

    async def _get_commands(self, lang_code: str) -> list[BotCommand]:
        """
        Returns a list of 'BotCommand' instances for the given language code.

        :param lang_code: The language code for which to return the commands.
        :return: A list of 'BotCommand' instances.
        """
        return [
            BotCommand(command="start", description=await self._tmpl.render(tmpl=self._cmd_start, locale=lang_code)),
            BotCommand(command="about", description=await self._tmpl.render(tmpl=self._cmd_about, locale=lang_code)),
            BotCommand(command="stop", description=await self._tmpl.render(tmpl=self._cmd_stop, locale=lang_code)),
        ]

    async def _get_admins_commands(self, lang_code: str) -> list[BotCommand]:
        """
        Returns a list of 'BotCommand' instances for admin users for the given language code.

        :param lang_code: The language code for which to return the commands.
        :return: A list of 'BotCommand' instances.
        """
        stats_desc: str = await self._tmpl.render(tmpl=self._cmd_stats, locale=lang_code)
        return [BotCommand(command="stats", description=stats_desc)]

    async def _set_for_locale(self, locale: str, language_code: str | None) -> None:
        """
        Sets the commands of one locale: the user commands for every private chat, plus the admin
        commands in each admin's own chat.

        :param locale: Locale to render the command descriptions in.
        :param language_code: Telegram language code the commands apply to, or None for the
            default commands shown to users of any language without its own.
        :return: None
        """
        commands: list[BotCommand] = await self._get_commands(lang_code=locale)
        await self._bot.set_my_commands(
            commands=commands, language_code=language_code, scope=BotCommandScopeAllPrivateChats()
        )
        admin_commands: list[BotCommand] = commands + await self._get_admins_commands(lang_code=locale)
        for admin_id in self._admin_ids:
            await self._bot.set_my_commands(
                commands=admin_commands, language_code=language_code, scope=BotCommandScopeChat(chat_id=admin_id)
            )

    async def set_commands(self) -> None:
        """
        Sets default commands for the bot, depending on the available translations in the program.

        :return: None
        """
        # Cleaning commands
        await self._bot.set_my_commands(commands=[], scope=BotCommandScopeAllGroupChats())
        await self._bot.set_my_commands(commands=[], scope=BotCommandScopeAllPrivateChats())
        await self._set_for_locale(locale=self._DEFAULT_LOCALE, language_code=None)
        for locale in self._tmpl.get_locales():
            await self._set_for_locale(locale=locale, language_code=locale)
