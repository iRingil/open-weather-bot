"""Unit tests for src/core/config.py (CoreConfig, PostgresConfig).

Every test builds its own throwaway .env file under pytest's tmp_path fixture and passes it as
CoreConfig's base_dir - never touches the real project .env (which holds live secrets, is
gitignored, and won't exist on a fresh CI checkout - that's exactly what would make these tests
fail on GitHub if they read it). Combined with tests/conftest.py's isolated_environ fixture, each
test is hermetic: it doesn't depend on run order or on anything set in the real environment. Redis
is never actually connected to either - Config only builds a lazy redis.asyncio.Redis client
object, it never connects.
"""

from pathlib import Path

import pytest
from environs import Env, EnvError
from pydantic import SecretStr
from redis.asyncio import Redis
from redis.asyncio.connection import ConnectionPool

from core.config import CoreConfig, PostgresConfig

__all__: tuple = ()

_ADMIN_AND_POSTGRES_VARS: str = (
    "WEATHER_API_TOKEN=tok\nADMIN_IDS=1,2,3\nPOSTGRES_DB_NAME=db\nPOSTGRES_DB_USER=user\nPOSTGRES_DB_PASS=pass\n"
)
_REQUIRED_REDIS_VARS: str = (
    "REDIS_DB_INDEX=0\nREDIS_DB_USER=user\nREDIS_DB_PASS=pass\nREDIS_HOST=host\nREDIS_PORT=6379\n"
)
_REQUIRED_VARS: str = _ADMIN_AND_POSTGRES_VARS + _REQUIRED_REDIS_VARS


def _write_env(base_dir: Path, content: str) -> None:
    """
    Writes a throwaway .env file for a test.

    :param base_dir: Directory to write the .env file into (CoreConfig's base_dir).
    :param content: Full contents of the .env file.
    :return: None
    """
    (base_dir / ".env").write_text(content, encoding="utf-8")


class TestInit:
    """Tests for CoreConfig.__init__: the .env-file existence check and the shared directories."""

    def test_missing_env_file_raises_file_not_found(self, tmp_path: Path) -> None:
        """
        No .env file at base_dir raises FileNotFoundError naming the expected path.

        :param tmp_path: pytest fixture - empty temporary directory, used as base_dir.
        :return: None
        """
        with pytest.raises(expected_exception=FileNotFoundError) as exc_info:
            CoreConfig(base_dir=tmp_path)
        assert str(tmp_path / ".env") in str(exc_info.value)

    def test_creates_log_dir(self, tmp_path: Path) -> None:
        """
        log_dir is created under base_dir and actually exists on disk.

        It's a gitignored runtime-only directory - unlike locale_dir below.

        :param tmp_path: pytest fixture - temporary directory holding the test's .env, used as base_dir.
        :return: None
        """
        _write_env(base_dir=tmp_path, content=_REQUIRED_VARS)
        config: CoreConfig = CoreConfig(base_dir=tmp_path)
        assert config.log_dir == tmp_path / "logs"
        assert config.log_dir.is_dir()

    def test_does_not_create_locale_dir(self, tmp_path: Path) -> None:
        """
        locale_dir is composed as a path but never created.

        It holds committed .po/.mo files, so a missing one is a real deployment bug that should
        surface as a FileNotFoundError, not get silently papered over with an empty directory.

        :param tmp_path: pytest fixture - temporary directory holding the test's .env, used as base_dir.
        :return: None
        """
        _write_env(base_dir=tmp_path, content=_REQUIRED_VARS)
        config: CoreConfig = CoreConfig(base_dir=tmp_path)
        assert config.locale_dir == tmp_path / "locales"
        assert not config.locale_dir.exists()

    def test_tolerates_already_existing_log_dir(self, tmp_path: Path) -> None:
        """
        _ensure_dir doesn't raise if the log directory already exists.

        :param tmp_path: pytest fixture - temporary directory holding the test's .env, used as
            base_dir; logs is pre-created under it before CoreConfig runs.
        :return: None
        """
        (tmp_path / "logs").mkdir()
        _write_env(base_dir=tmp_path, content=_REQUIRED_VARS)
        config: CoreConfig = CoreConfig(base_dir=tmp_path)
        assert config.log_dir.is_dir()


class TestDebug:
    """Tests for CoreConfig.debug."""

    def test_defaults_to_true_when_unset(self, tmp_path: Path) -> None:
        """
        DEBUG absent from .env defaults to True.

        :param tmp_path: pytest fixture - temporary directory holding the test's .env, used as base_dir.
        :return: None
        """
        _write_env(base_dir=tmp_path, content=_REQUIRED_VARS)
        assert CoreConfig(base_dir=tmp_path).debug is True

    @pytest.mark.parametrize("raw_value,expected", [("true", True), ("false", False)])
    def test_reads_explicit_value(self, tmp_path: Path, raw_value: str, expected: bool) -> None:
        """
        DEBUG=true/false in .env is parsed to the matching bool.

        :param tmp_path: pytest fixture - temporary directory holding the test's .env, used as base_dir.
        :param raw_value: Raw DEBUG value written to the .env file, e.g. "true".
        :param expected: The bool CoreConfig.debug is expected to return for raw_value.
        :return: None
        """
        _write_env(base_dir=tmp_path, content=_REQUIRED_VARS + f"DEBUG={raw_value}\n")
        assert CoreConfig(base_dir=tmp_path).debug is expected


class TestAdmins:
    """Tests for CoreConfig.admins / _get_admins."""

    def test_parses_multiple_ids(self, tmp_path: Path) -> None:
        """
        A comma-separated ADMIN_IDS is parsed into a list of ints.

        :param tmp_path: pytest fixture - temporary directory holding the test's .env, used as base_dir.
        :return: None
        """
        _write_env(
            base_dir=tmp_path,
            content="WEATHER_API_TOKEN=tok\nADMIN_IDS=111,222,333\nPOSTGRES_DB_NAME=db\nPOSTGRES_DB_USER=u\nPOSTGRES_DB_PASS=p\n"
            + _REQUIRED_REDIS_VARS,
        )
        assert CoreConfig(base_dir=tmp_path).admins == [111, 222, 333]

    def test_parses_single_id(self, tmp_path: Path) -> None:
        """
        A single-value ADMIN_IDS still parses into a one-element list, not a bare int.

        :param tmp_path: pytest fixture - temporary directory holding the test's .env, used as base_dir.
        :return: None
        """
        _write_env(
            base_dir=tmp_path,
            content="WEATHER_API_TOKEN=tok\nADMIN_IDS=111\nPOSTGRES_DB_NAME=db\nPOSTGRES_DB_USER=u\nPOSTGRES_DB_PASS=p\n"
            + _REQUIRED_REDIS_VARS,
        )
        assert CoreConfig(base_dir=tmp_path).admins == [111]

    def test_missing_raises_enverror(self, tmp_path: Path) -> None:
        """
        Missing ADMIN_IDS raises EnvError with the wrapped, more specific message.

        :param tmp_path: pytest fixture - temporary directory holding the test's .env, used as base_dir.
        :return: None
        """
        _write_env(
            base_dir=tmp_path,
            content="WEATHER_API_TOKEN=tok\nPOSTGRES_DB_NAME=db\nPOSTGRES_DB_USER=u\nPOSTGRES_DB_PASS=p\n",
        )
        with pytest.raises(expected_exception=EnvError, match="Admin IDs not found"):
            CoreConfig(base_dir=tmp_path)


class TestWeatherToken:
    """Tests for CoreConfig.weather_token / _get_weather_token."""

    def test_reads_token_as_secret_str(self, tmp_path: Path) -> None:
        """
        WEATHER_API_TOKEN is returned as a SecretStr that never shows up in its repr/str.

        :param tmp_path: pytest fixture - temporary directory holding the test's .env, used as base_dir.
        :return: None
        """
        content: str = _REQUIRED_VARS.replace("WEATHER_API_TOKEN=tok", "WEATHER_API_TOKEN=owm123")
        _write_env(base_dir=tmp_path, content=content)
        token: SecretStr = CoreConfig(base_dir=tmp_path).weather_token
        assert isinstance(token, SecretStr)
        assert token.get_secret_value() == "owm123"
        assert "owm123" not in repr(token)
        assert "owm123" not in str(token)

    def test_missing_raises_enverror(self, tmp_path: Path) -> None:
        """
        Missing WEATHER_API_TOKEN raises EnvError with the wrapped, more specific message.

        :param tmp_path: pytest fixture - temporary directory holding the test's .env, used as base_dir.
        :return: None
        """
        _write_env(base_dir=tmp_path, content=_REQUIRED_VARS.replace("WEATHER_API_TOKEN=tok\n", ""))
        with pytest.raises(expected_exception=EnvError, match="WEATHER_API_TOKEN not found"):
            CoreConfig(base_dir=tmp_path)


class TestPostgresConfigShape:
    """Tests locking down PostgresConfig's exact set of fields."""

    def test_declares_exactly_the_expected_fields(self) -> None:
        """
        PostgresConfig has exactly these fields, in this order - no more, no fewer.

        If this fails, a field was added/removed/renamed on PostgresConfig. Every place that
        builds or reads one needs reviewing, not just this test updated to match.

        :return: None
        """
        assert PostgresConfig._fields == (
            "host",
            "port",
            "database",
            "username",
            "password",
            "socket_path",
            "use_socket",
        )

    def test_declares_exactly_the_expected_field_types(self) -> None:
        """
        Each PostgresConfig field has exactly the expected annotated type.

        Catches a field's type changing without its name changing (which alone wouldn't be caught
        by test_declares_exactly_the_expected_fields).

        :return: None
        """
        assert PostgresConfig.__annotations__ == {
            "host": str | None,
            "port": int | None,
            "database": str,
            "username": str,
            "password": SecretStr,
            "socket_path": str | None,
            "use_socket": bool,
        }


class TestPostgres:
    """Tests for CoreConfig.postgres / _get_postgres."""

    def test_full_credentials_with_host_port(self, tmp_path: Path) -> None:
        """
        All Postgres fields set in .env land correctly on the returned PostgresConfig.

        :param tmp_path: pytest fixture - temporary directory holding the test's .env, used as base_dir.
        :return: None
        """
        content: str = (
            "WEATHER_API_TOKEN=tok\nADMIN_IDS=1\n"
            "POSTGRES_DB_NAME=mydb\n"
            "POSTGRES_DB_USER=myuser\n"
            "POSTGRES_DB_PASS=mypass\n"
            "POSTGRES_HOST=db.internal\n"
            "POSTGRES_PORT=6543\n" + _REQUIRED_REDIS_VARS
        )
        _write_env(base_dir=tmp_path, content=content)
        pg: PostgresConfig = CoreConfig(base_dir=tmp_path).postgres
        assert pg == PostgresConfig(
            host="db.internal",
            port=6543,
            database="mydb",
            username="myuser",
            password=SecretStr("mypass"),
            socket_path=None,
            use_socket=False,
        )

    def test_socket_mode(self, tmp_path: Path) -> None:
        """
        USE_POSTGRES_SOCKET=true switches to socket_path, leaving host/port unset.

        :param tmp_path: pytest fixture - temporary directory holding the test's .env, used as base_dir.
        :return: None
        """
        content: str = (
            "WEATHER_API_TOKEN=tok\nADMIN_IDS=1\n"
            "POSTGRES_DB_NAME=mydb\n"
            "POSTGRES_DB_USER=myuser\n"
            "POSTGRES_DB_PASS=mypass\n"
            "POSTGRES_SOCKET_PATH=/var/run/postgresql\n"
            "USE_POSTGRES_SOCKET=true\n" + _REQUIRED_REDIS_VARS
        )
        _write_env(base_dir=tmp_path, content=content)
        pg: PostgresConfig = CoreConfig(base_dir=tmp_path).postgres
        assert pg.use_socket is True
        assert pg.socket_path == "/var/run/postgresql"
        assert pg.host is None
        assert pg.port is None

    def test_host_port_socket_path_default_to_none(self, tmp_path: Path) -> None:
        """
        Optional Postgres fields default to None/False when absent from .env.

        :param tmp_path: pytest fixture - temporary directory holding the test's .env, used as
            base_dir.
        :return: None
        """
        _write_env(base_dir=tmp_path, content=_REQUIRED_VARS)
        pg: PostgresConfig = CoreConfig(base_dir=tmp_path).postgres
        assert pg.host is None
        assert pg.port is None
        assert pg.socket_path is None
        assert pg.use_socket is False

    @pytest.mark.parametrize(
        "content",
        [
            pytest.param(
                "WEATHER_API_TOKEN=tok\nADMIN_IDS=1\nPOSTGRES_DB_USER=u\nPOSTGRES_DB_PASS=p\n", id="missing_db_name"
            ),
            pytest.param(
                "WEATHER_API_TOKEN=tok\nADMIN_IDS=1\nPOSTGRES_DB_NAME=db\nPOSTGRES_DB_PASS=p\n", id="missing_db_user"
            ),
            pytest.param(
                "WEATHER_API_TOKEN=tok\nADMIN_IDS=1\nPOSTGRES_DB_NAME=db\nPOSTGRES_DB_USER=u\n", id="missing_db_pass"
            ),
        ],
    )
    def test_missing_required_field_raises_enverror(self, tmp_path: Path, content: str) -> None:
        """
        Each required Postgres field, when missing on its own, raises EnvError.

        :param tmp_path: pytest fixture - temporary directory holding the test's .env, used as base_dir.
        :param content: Full .env contents for this case, missing exactly one required POSTGRES_* field.
        :return: None
        """
        _write_env(base_dir=tmp_path, content=content)
        with pytest.raises(expected_exception=EnvError, match="Postgres credentials not found"):
            CoreConfig(base_dir=tmp_path)

    def test_password_is_a_secret_str_not_exposed_in_repr(self, tmp_path: Path) -> None:
        """
        postgres.password is a SecretStr - the real value is retrievable but never printed.

        :param tmp_path: pytest fixture - temporary directory holding the test's .env, used as base_dir.
        :return: None
        """
        _write_env(
            base_dir=tmp_path,
            content="WEATHER_API_TOKEN=tok\nADMIN_IDS=1\nPOSTGRES_DB_NAME=db\nPOSTGRES_DB_USER=u\nPOSTGRES_DB_PASS=supersecret\n"
            + _REQUIRED_REDIS_VARS,
        )
        pg: PostgresConfig = CoreConfig(base_dir=tmp_path).postgres
        assert pg.password.get_secret_value() == "supersecret"
        assert "supersecret" not in repr(pg.password)
        assert "supersecret" not in str(pg.password)


class TestRedis:
    """
    Tests for CoreConfig.redis / _get_redis.

    Redis is unconditionally required, like postgres - there's no opt-in flag to skip building a
    connection.
    """

    def test_host_port_mode(self, tmp_path: Path) -> None:
        """
        Without USE_REDIS_SOCKET, builds a TCP-mode, decode_responses=True Redis client.

        :param tmp_path: pytest fixture - temporary directory holding the test's .env, used as base_dir.
        :return: None
        """
        content: str = (
            _ADMIN_AND_POSTGRES_VARS + "REDIS_DB_INDEX=2\nREDIS_DB_USER=cacheuser\n"
            "REDIS_DB_PASS=cachepass\nREDIS_HOST=cache.internal\nREDIS_PORT=6380\n"
        )
        _write_env(base_dir=tmp_path, content=content)
        redis: Redis = CoreConfig(base_dir=tmp_path).redis
        assert isinstance(redis, Redis)
        pool: ConnectionPool | None = redis.connection_pool
        assert pool is not None
        kwargs: dict = pool.connection_kwargs
        assert pool.connection_class.__name__ == "Connection"
        assert kwargs["host"] == "cache.internal"
        assert kwargs["port"] == 6380
        assert kwargs["db"] == 2
        assert kwargs["username"] == "cacheuser"
        assert kwargs["password"] == "cachepass"
        assert kwargs["decode_responses"] is True

    def test_socket_mode(self, tmp_path: Path) -> None:
        """
        USE_REDIS_SOCKET=true builds a Unix-socket-mode Redis client.

        :param tmp_path: pytest fixture - temporary directory holding the test's .env, used as base_dir.
        :return: None
        """
        content: str = (
            _ADMIN_AND_POSTGRES_VARS + "USE_REDIS_SOCKET=true\nREDIS_DB_INDEX=3\n"
            "REDIS_DB_USER=cacheuser\nREDIS_DB_PASS=cachepass\nREDIS_SOCKET_PATH=/var/run/redis.sock\n"
        )
        _write_env(base_dir=tmp_path, content=content)
        redis: Redis = CoreConfig(base_dir=tmp_path).redis
        assert isinstance(redis, Redis)
        pool: ConnectionPool | None = redis.connection_pool
        assert pool is not None
        kwargs: dict = pool.connection_kwargs
        assert pool.connection_class.__name__ == "UnixDomainSocketConnection"
        assert kwargs["path"] == "/var/run/redis.sock"
        assert kwargs["db"] == 3
        assert kwargs["username"] == "cacheuser"
        assert kwargs["password"] == "cachepass"
        assert kwargs["decode_responses"] is True

    @pytest.mark.parametrize(
        "extra_env",
        [
            pytest.param("REDIS_DB_USER=u\nREDIS_DB_PASS=p\nREDIS_HOST=h\nREDIS_PORT=1\n", id="missing_db_index"),
            pytest.param("REDIS_DB_INDEX=0\nREDIS_DB_USER=u\nREDIS_DB_PASS=p\nREDIS_PORT=1\n", id="missing_host"),
            pytest.param("REDIS_DB_INDEX=0\nREDIS_DB_USER=u\nREDIS_DB_PASS=p\nREDIS_HOST=h\n", id="missing_port"),
            pytest.param(
                "USE_REDIS_SOCKET=true\nREDIS_DB_INDEX=0\nREDIS_DB_USER=u\nREDIS_DB_PASS=p\n",
                id="missing_socket_path",
            ),
        ],
    )
    def test_missing_required_field_raises_enverror(self, tmp_path: Path, extra_env: str) -> None:
        """
        Each required Redis field, when missing on its own, raises EnvError.

        :param tmp_path: pytest fixture - temporary directory holding the test's .env, used as base_dir.
        :param extra_env: .env lines missing exactly one required REDIS_* field.
        :return: None
        """
        _write_env(base_dir=tmp_path, content=_ADMIN_AND_POSTGRES_VARS + extra_env)
        with pytest.raises(expected_exception=EnvError, match="Redis credentials not found"):
            CoreConfig(base_dir=tmp_path)

    @pytest.mark.parametrize(
        "extra_env",
        [
            pytest.param("REDIS_DB_INDEX=0\nREDIS_HOST=h\nREDIS_PORT=1\n", id="both_absent"),
            pytest.param(
                "REDIS_DB_INDEX=0\nREDIS_DB_USER=\nREDIS_DB_PASS=\nREDIS_HOST=h\nREDIS_PORT=1\n", id="both_empty"
            ),
        ],
    )
    def test_username_and_password_are_optional(self, tmp_path: Path, extra_env: str) -> None:
        """
        REDIS_DB_USER/REDIS_DB_PASS absent or empty become None - Redis then authenticates against
        its 'default' user, as the previous bot version's setup (no username at all) expects.

        :param tmp_path: pytest fixture - temporary directory holding the test's .env, used as base_dir.
        :param extra_env: .env lines with both optional REDIS_* fields absent or empty.
        :return: None
        """
        _write_env(base_dir=tmp_path, content=_ADMIN_AND_POSTGRES_VARS + extra_env)
        redis: Redis = CoreConfig(base_dir=tmp_path).redis
        kwargs: dict = redis.connection_pool.connection_kwargs
        assert kwargs["username"] is None
        assert kwargs["password"] is None

    def test_computed_once_in_init_not_per_access(self, tmp_path: Path) -> None:
        """
        Second access returns the exact same Redis instance built during __init__, not a
        freshly-built one - there's only ever one live connection per CoreConfig.

        :param tmp_path: pytest fixture - temporary directory holding the test's .env, used as base_dir.
        :return: None
        """
        _write_env(base_dir=tmp_path, content=_REQUIRED_VARS)
        config: CoreConfig = CoreConfig(base_dir=tmp_path)
        first: Redis = config.redis
        second: Redis = config.redis
        assert first is second


class TestEnvProperty:
    """Tests for CoreConfig.env."""

    def test_returns_env_instance_with_the_same_loaded_values(self, tmp_path: Path) -> None:
        """
        env returns the same Env used internally, still able to read the loaded .env file.

        :param tmp_path: pytest fixture - temporary directory holding the test's .env, used as base_dir.
        :return: None
        """
        _write_env(base_dir=tmp_path, content=_REQUIRED_VARS + "EXTRA_VAR=hello\n")
        config: CoreConfig = CoreConfig(base_dir=tmp_path)
        assert isinstance(config.env, Env)
        assert config.env.str(name="EXTRA_VAR") == "hello"
