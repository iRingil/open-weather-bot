"""Settings shared across every subsystem of the application (bot, weather logic)."""

from pathlib import Path
from typing import NamedTuple

from environs import Env, EnvError
from pydantic import SecretStr
from redis.asyncio import Redis

__all__: tuple[str, ...] = ("CoreConfig", "PostgresConfig")

_BASE_DIR: Path = Path(__file__).resolve().parent.parent  # src/


# noinspection GrazieInspection
class PostgresConfig(NamedTuple):
    """
    PostgreSQL connection parameters.

    :param host: PostgreSQL host - unused if use_socket is True.
    :param port: PostgreSQL port - unused if use_socket is True.
    :param database: Database name.
    :param username: PostgreSQL username.
    :param password: PostgreSQL password.
    :param socket_path: Unix socket path - unused unless use_socket is True.
    :param use_socket: True to connect over a Unix socket instead of host/port.
    """

    host: str | None
    port: int | None
    database: str
    username: str
    password: SecretStr
    socket_path: str | None
    use_socket: bool


class CoreConfig:
    """Reads settings shared across the whole application from the .env file."""

    def __init__(self, base_dir: Path = _BASE_DIR) -> None:
        """
        Initializes the config, or raises if the .env file is not found.

        :param base_dir: Path to the src/ directory.
        :raise FileNotFoundError: if the .env file is not found.
        """
        self._env_path: Path = base_dir / ".env"
        if not self._env_path.exists():
            raise FileNotFoundError(f"The .env file was not found in the path: {self._env_path}")
        self._env: Env = Env()
        self._env.read_env(path=self._env_path, recurse=False)
        self._debug: bool = self._env.bool(name="DEBUG", default=True)
        self._admins: list[int] = self._get_admins()
        self._weather_token: SecretStr = self._get_weather_token()
        self._locale_dir: Path = base_dir / "locales"
        self._log_dir: Path = self._ensure_dir(base_dir / "logs")
        self._postgres: PostgresConfig = self._get_postgres()
        self._redis: Redis = self._get_redis()

    @staticmethod
    def _ensure_dir(path: Path) -> Path:
        """
        Creates the directory if it doesn't exist yet.

        :param path: Path to the directory.
        :return: The same path.
        """
        path.mkdir(exist_ok=True)
        return path

    def _get_admins(self) -> list[int]:
        """
        Returns the list of admin IDs that receive system notifications.

        :return: list of admin IDs.
        :raise EnvError: if the admin IDs are not found in the .env file.
        """
        try:
            return list(map(int, self._env.list(name="ADMIN_IDS")))
        except EnvError as exc:
            raise EnvError(f"Admin IDs not found in the .env file: {repr(exc)}") from exc

    def _get_weather_token(self) -> SecretStr:
        """
        Returns the OpenWeatherMap API key.

        :return: OpenWeatherMap API key.
        :raise EnvError: if the API key is not found in the .env file.
        """
        try:
            return SecretStr(self._env.str(name="WEATHER_API_TOKEN"))
        except EnvError as exc:
            raise EnvError(f"WEATHER_API_TOKEN not found in the .env file: {repr(exc)}") from exc

    def _get_postgres(self) -> PostgresConfig:
        """
        Returns the PostgreSQL connection parameters.

        :return: PostgresConfig instance.
        :raise EnvError: if the required Postgres credentials are missing from the .env file.
        """
        try:
            return PostgresConfig(
                host=self._env.str(name="POSTGRES_HOST", default=None),
                port=self._env.int(name="POSTGRES_PORT", default=None),
                database=self._env.str(name="POSTGRES_DB_NAME"),
                username=self._env.str(name="POSTGRES_DB_USER"),
                password=SecretStr(self._env.str(name="POSTGRES_DB_PASS")),
                socket_path=self._env.str(name="POSTGRES_SOCKET_PATH", default=None),
                use_socket=self._env.bool(name="USE_POSTGRES_SOCKET", default=False),
            )
        except EnvError as exc:
            raise EnvError(f"Postgres credentials not found in the .env file: {repr(exc)}") from exc

    def _get_redis(self) -> Redis:
        """
        Returns the shared Redis connection.

        REDIS_DB_USER is optional: without it, Redis authenticates the password against its
        'default' user.

        :return: Redis instance.
        :raise EnvError: if the required Redis credentials are missing from the .env file.
        """
        try:
            db_index: int = self._env.int(name="REDIS_DB_INDEX")
            password: str | None = self._env.str(name="REDIS_DB_PASS", default=None) or None
            username: str | None = self._env.str(name="REDIS_DB_USER", default=None) or None
            if self._env.bool(name="USE_REDIS_SOCKET", default=False):
                return Redis(
                    unix_socket_path=self._env.str(name="REDIS_SOCKET_PATH"),
                    db=db_index,
                    password=password,
                    username=username,
                    decode_responses=True,
                )
            return Redis(
                host=self._env.str(name="REDIS_HOST"),
                port=self._env.int(name="REDIS_PORT"),
                db=db_index,
                password=password,
                username=username,
                decode_responses=True,
            )
        except EnvError as exc:
            raise EnvError(f"Redis credentials not found in the .env file: {repr(exc)}") from exc

    @property
    def debug(self) -> bool:
        """
        Returns whether the application runs in debug mode (verbose logging).

        :return: True if debug mode is enabled.
        """
        return self._debug

    @property
    def admins(self) -> list[int]:
        """
        Returns the list of admin IDs that receive system notifications.

        :return: list of admin IDs.
        """
        return self._admins

    @property
    def weather_token(self) -> SecretStr:
        """
        Returns the OpenWeatherMap API key.

        :return: OpenWeatherMap API key.
        """
        return self._weather_token

    @property
    def locale_dir(self) -> Path:
        """
        Returns the path to the shared localization folder.

        :return: Path to the localization folder.
        """
        return self._locale_dir

    @property
    def log_dir(self) -> Path:
        """
        Returns the path to the shared log files folder.

        :return: Path to the log files folder.
        """
        return self._log_dir

    @property
    def postgres(self) -> PostgresConfig:
        """
        Returns the PostgreSQL connection parameters.

        :return: PostgresConfig instance.
        """
        return self._postgres

    @property
    def redis(self) -> Redis:
        """
        Returns the shared Redis connection.

        :return: Redis instance.
        """
        return self._redis

    @property
    def env(self) -> Env:
        """
        Returns the parsed .env environment.

        :return: Env instance.
        """
        return self._env
