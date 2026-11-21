"""
Shared pytest fixtures for the whole test suite.

The integration fixtures connect to the throwaway test PostgreSQL / Redis: locally the WSL ones, in CI the
pytest workflow's service containers, both with the same credentials. 127.0.0.1, never localhost: localhost
resolves to ::1 first, and the WSL port relay is IPv4 only.
"""

# ruff: noqa: S105

import os
from collections.abc import AsyncIterator

import pytest
from asyncpg import Connection, connect
from pydantic import SecretStr
from redis.asyncio import Redis

from core.config import PostgresConfig
from core.db.repository import Database

__all__: tuple[str, ...] = ()

_TEST_HOST: str = "127.0.0.1"
_TEST_USER: str = "test_user"
_TEST_PASSWORD: str = "test_password"
_TEST_REDIS_DB: int = 15


@pytest.fixture(autouse=True)
def isolated_environ(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Replaces os.environ with an empty dict for the duration of each test.

    environs.Env checks the real os.environ before falling back to a test's own throwaway
    .env file. Without this, a variable left over from one test (via monkeypatch.setenv, or a
    real env var set on the host) could shadow another test's .env value for the same key.

    :param monkeypatch: pytest's monkeypatch fixture, which restores the original os.environ
        object automatically once the test finishes.
    :return: None
    """
    monkeypatch.setattr(target=os, name="environ", value={})


@pytest.fixture(name="pg_config")
def pg_config_fixture() -> PostgresConfig:
    """
    The connection configuration of the test PostgreSQL database.

    :return: The config.
    """
    return PostgresConfig(
        host=_TEST_HOST,
        port=5432,
        database="test_db",
        username=_TEST_USER,
        password=SecretStr(_TEST_PASSWORD),
        socket_path=None,
        use_socket=False,
    )


@pytest.fixture(name="pg_conn")
async def pg_conn_fixture(pg_config: PostgresConfig) -> AsyncIterator[Connection]:
    """
    A plain asyncpg connection to the test database, for the tests' own setup and checks.

    :param pg_config: The test database configuration.
    :return: The connection.
    """
    conn: Connection = await connect(
        host=pg_config.host,
        port=pg_config.port,
        user=pg_config.username,
        password=pg_config.password.get_secret_value(),
        database=pg_config.database,
    )
    yield conn
    await conn.close()


@pytest.fixture(name="database")
async def database_fixture(pg_config: PostgresConfig, pg_conn: Connection) -> AsyncIterator[Database]:
    """
    A Database over the test PostgreSQL with freshly created, empty tables, dropped again after the test.

    :param pg_config: The test database configuration.
    :param pg_conn: The plain connection, to drop the tables.
    :return: The Database.
    """
    drop_tables: str = "DROP TABLE IF EXISTS users, api_request_counters"
    database: Database = Database(pg_config=pg_config)
    await pg_conn.execute(drop_tables)
    await database.create_tables()
    yield database
    await database.close()
    await pg_conn.execute(drop_tables)


@pytest.fixture(name="redis")
async def redis_fixture() -> AsyncIterator[Redis]:
    """
    A connection to the test Redis database, emptied before and after the test.

    decode_responses=True, as in production (core.config.CoreConfig._get_redis).

    :return: The Redis connection.
    """
    redis: Redis = Redis(
        host=_TEST_HOST,
        port=6379,
        db=_TEST_REDIS_DB,
        username=_TEST_USER,
        password=_TEST_PASSWORD,
        decode_responses=True,
    )
    await redis.flushdb()
    yield redis
    await redis.flushdb()
    await redis.aclose()
