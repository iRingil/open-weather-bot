"""Setting up the aiogram bot-specific configuration."""

from pathlib import Path

from environs import Env, EnvError
from redis.asyncio import Redis

from tgbot.misc.data_types import Paths, WebhookCredentials
from core.config import CoreConfig

__all__: tuple[str] = ("Config",)


_BASE_DIR: Path = Path(__file__).resolve().parent  # Path settings


class Config:
    """Reads bot-specific variables from the .env file, on top of the shared CoreConfig."""

    def __init__(self, core: CoreConfig, base_dir: Path = _BASE_DIR) -> None:
        """
        Initializes the config.

        :param core: CoreConfig instance with settings shared across the whole application.
        :param base_dir: Path to the tgbot package directory.
        """
        self._core: CoreConfig = core
        self._env: Env = core.env
        self._paths: Paths = self._get_paths(base_dir=base_dir)
        self._token: str = self._get_token()
        self._webhook: WebhookCredentials | None = self._get_webhook()

    @property
    def admins(self) -> list[int]:
        """
        Returns bots admins IDs.

        :return: list with bot admins IDs.
        """
        return self._core.admins

    @staticmethod
    def _get_paths(base_dir: Path) -> Paths:
        """
        Returns the paths to the folders used in the program.

        :param base_dir: Path to the tgbot package directory.
        :return: Paths object.
        """
        logo: Path = Path(base_dir, "assets/img/bot_logo.jpg")
        templates: Path = Path(base_dir.parent, "templates")
        return Paths(bot_logo=logo, templates=templates)

    @property
    def paths(self) -> Paths:
        """
        Returns the paths to the folders used in the program.

        :return: Paths object.
        """
        return self._paths

    @property
    def redis(self) -> Redis:
        """
        Returns the shared Redis connection for aiogram's FSM storage.

        Forwards the shared connection rather than building its own, so there's only ever one
        live connection to Redis for the whole application.

        :return: Redis instance.
        """
        return self._core.redis

    def _get_token(self) -> str:
        """
        Returns the bot token or terminates the program in case of an error.

        :return: Telegram bot token.
        :raise EnvError: if the bot token is not found in the .env file.
        """
        try:
            return self._env.str(name="BOT_TOKEN")
        except EnvError as exc:
            raise EnvError(f"BOT_TOKEN not found: {repr(exc)}") from exc

    @property
    def token(self) -> str:
        """
        Returns the bot token.

        :return: Telegram bot token.
        """
        return self._token

    def _get_webhook(self) -> WebhookCredentials | None:
        """
        Returns the credentials to run the bot via webhook, or None for the long-polling default.

        :return: WebhookCredentials, or None if USE_WEBHOOK isn't set to true in the .env file.
        :raise EnvError: if USE_WEBHOOK is true but the matching credentials are missing.
        """
        if not self._env.bool(name="USE_WEBHOOK", default=False):
            return None
        try:
            return WebhookCredentials(
                wh_host=self._env.str(name="WEBHOOK_HOST"),
                wh_path=self._env.str(name="WEBHOOK_PATH"),
                wh_token=self._env.str(name="WEBHOOK_TOKEN"),
                app_host=self._env.str(name="WEBAPP_HOST"),
                app_port=self._env.int(name="WEBAPP_PORT"),
            )
        except EnvError as exc:
            raise EnvError(f"Webhook credentials not found in the .env file: {repr(exc)}") from exc

    @property
    def webhook(self) -> WebhookCredentials | None:
        """
        Returns the credentials to run the bot via webhook.

        :return: WebhookCredentials, or None if USE_WEBHOOK isn't set to true in the .env file.
        """
        return self._webhook
