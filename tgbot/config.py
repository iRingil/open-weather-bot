"""Configuration settings for the bot."""

from pathlib import Path
from typing import NamedTuple

from aiogram.contrib.fsm_storage.redis import RedisStorage2
from environs import Env


__all__: tuple[str, ...] = ("BASE_DIR", "BOT_LOGO", "LOCALES_DIR", "LOG_FILE", "Config", "load_config")

BASE_DIR: Path = Path(__file__).resolve().parent.parent
_USE_PG_SOCKET: bool = False
_USE_REDIS_SOCKET: bool = False
BOT_LOGO: Path = Path(BASE_DIR, "tgbot/assets/logo/bot_logo.png")
LOCALES_DIR: Path = Path(BASE_DIR, "tgbot/locales")
LOG_FILE: Path = Path(BASE_DIR, "logs/open-weather-bot.log")


class Webhook(NamedTuple):
    """
    Webhook parameters.

    :param wh_host: Webhook host.
    :param wh_path: Webhook path.
    :param wh_token: Webhook token.
    :param app_host: WebApp host.
    :param app_port: WebApp port.
    """

    wh_host: str
    wh_path: str
    wh_token: str
    app_host: str
    app_port: int


class TgBot(NamedTuple):
    """
    Bot credentials.

    :param token: Bot token.
    :param admin_ids: Tuple of admin IDs.
    :param webhook: Webhook parameters.
    """

    token: str
    admin_ids: tuple[int, ...]
    webhook: Webhook


class WeatherToken(NamedTuple):
    """
    OpenWeatherMap weather API token.

    :param token: OpenWeatherMap weather API token.
    """

    token: str


class Config(NamedTuple):
    """
    Bot config.

    :param tg_bot: TgBot instance.
    :param weather_api: OpenWeatherMap weather API token.
    :param pg_dsn: Postgres database connection string.
    :param storage: Redis storage for FSM.
    """

    tg_bot: TgBot
    weather_api: WeatherToken
    pg_dsn: str
    storage: RedisStorage2


def _get_db_dsn(env: Env, use_socket: bool) -> str:
    """
    Returns the Postgres database connection string.

    :param env: Env instance.
    :param use_socket: True, if a postgres socket is used, otherwise False.
    :return: Postgres database connection string.
    """
    db_name: str = env.str("POSTGRES_DB_NAME")
    db_user: str = env.str("POSTGRES_DB_USER")
    db_pass: str = env.str("POSTGRES_DB_PASSWORD")
    if use_socket:
        db_socket_path: str = env.str("POSTGRES_SOCKET_PATH")
        return f"postgresql://{db_user}:{db_pass}@/{db_name}?host={db_socket_path}"
    db_host: str = env.str("POSTGRES_DB_HOST")
    db_port: str = env.str("POSTGRES_DB_PORT")
    return f"postgres://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"


def _get_redis_storage(env: Env, use_socket: bool) -> RedisStorage2:
    """
    Returns the Redis storage for FSM.

    :param env: Env instance.
    :param use_socket: True, if a redis socket is used, otherwise False.
    :return: Redis storage for FSM.
    """
    if use_socket:
        host: str = env.str("REDIS_HOST")
        port: int = env.int("REDIS_PORT")
    else:
        host = env.str("REDIS_SOCKET_PATH")
        port = 0
    return RedisStorage2(
        host=host,
        port=port,
        db=env.int("REDIS_DB_INDEX"),
        password=env.str("REDIS_DB_PASS"),
        prefix="open_weather_bot_fsm",
    )


def _get_webhook(env: Env) -> Webhook:
    """
    Returns the webhook parameters.

    :param env:
    :return: Webhook parameters.
    """
    return Webhook(
        wh_host=env.str("WEBHOOK_HOST"),
        wh_path=env.str("WEBHOOK_PATH"),
        wh_token=env.str("WEBHOOK_TOKEN"),
        app_host=env.str("WEBAPP_HOST"),
        app_port=env.int("WEBAPP_PORT"),
    )


def load_config() -> Config:
    """
    Loads data from environment variables.

    :return: Config instance.
    """
    env: Env = Env()
    env.read_env()
    return Config(
        tg_bot=TgBot(
            token=env.str("BOT_TOKEN"), admin_ids=tuple(map(int, env.list("ADMINS_IDS"))), webhook=_get_webhook(env=env)
        ),
        weather_api=WeatherToken(token=env.str("WEATHER_API_TOKEN")),
        pg_dsn=_get_db_dsn(env=env, use_socket=_USE_PG_SOCKET),
        storage=_get_redis_storage(env=env, use_socket=_USE_REDIS_SOCKET),
    )
