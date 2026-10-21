"""
Unit tests for src/core/db/client.py (PostgresClient) - pure connection-pool plumbing, no SQL of
its own, unlike core.db.repository.Database. create_pool is monkeypatched at module level;
Pool/Connection are autospecced - never a real database call.
"""

# pylint: disable=protected-access

from unittest.mock import AsyncMock, MagicMock, create_autospec

import pytest
from asyncpg import Connection, Pool
from pydantic import SecretStr

import core.db.client as client_module
from core.config import PostgresConfig
from core.db.client import PostgresClient

__all__: tuple = ()


def _pg_config(use_socket: bool = False) -> PostgresConfig:
    """
    Builds a throwaway PostgresConfig.

    :param use_socket: Whether to build a socket-based config or a host/port one.
    :return: The config under test.
    """
    if use_socket:
        return PostgresConfig(
            host=None,
            port=None,
            database="testdb",
            username="testuser",
            password=SecretStr("testpass"),
            socket_path="/var/run/postgresql",
            use_socket=True,
        )
    return PostgresConfig(
        host="db.example.com",
        port=5432,
        database="testdb",
        username="testuser",
        password=SecretStr("testpass"),
        socket_path=None,
        use_socket=False,
    )


def _connection() -> MagicMock:
    """
    Builds an autospecced Connection - .execute/.fetch/.fetchrow are AsyncMocks, signature-checked
    against the real class.

    :return: The mocked Connection instance.
    """
    mock: MagicMock = create_autospec(spec=Connection, instance=True)
    return mock


def _pool_yielding(conn: MagicMock) -> MagicMock:
    """
    Builds an autospecced Pool whose acquire() async context manager yields the given connection.

    :param conn: The connection acquire() should yield.
    :return: The mocked Pool instance.
    """
    pool: MagicMock = create_autospec(spec=Pool, instance=True)
    acquire_cm: MagicMock = MagicMock()
    acquire_cm.__aenter__ = AsyncMock(return_value=conn)
    acquire_cm.__aexit__ = AsyncMock(return_value=False)
    pool.acquire = MagicMock(return_value=acquire_cm)
    return pool


class TestBuildDsn:
    """Tests for PostgresClient._build_dsn's host/port vs. socket branching and percent-encoding."""

    def test_builds_a_host_port_dsn(self) -> None:
        """
        A non-socket config builds a DSN pointing at host:port/database.

        :return: None
        """
        dsn: str = PostgresClient._build_dsn(pg_config=_pg_config(use_socket=False))
        assert dsn == "postgresql://testuser:testpass@db.example.com:5432/testdb"

    def test_builds_a_socket_dsn(self) -> None:
        """
        A socket config builds a DSN with an empty host and a host= query param instead, ignoring
        the config's own host/port fields entirely.

        :return: None
        """
        dsn: str = PostgresClient._build_dsn(pg_config=_pg_config(use_socket=True))
        assert dsn == "postgresql://testuser:testpass@/testdb?host=/var/run/postgresql"

    def test_percent_encodes_special_characters_in_credentials(self) -> None:
        """
        Username/password containing DSN-special characters (@, :, /, ?, #) are percent-encoded,
        so they can't be misparsed as DSN structure.

        :return: None
        """
        config: PostgresConfig = PostgresConfig(
            host="db.example.com",
            port=5432,
            database="testdb",
            username="user@name",
            password=SecretStr("p:a/s?s#w"),
            socket_path=None,
            use_socket=False,
        )
        dsn: str = PostgresClient._build_dsn(pg_config=config)
        assert dsn == "postgresql://user%40name:p%3Aa%2Fs%3Fs%23w@db.example.com:5432/testdb"


class TestGetPool:
    """Tests for PostgresClient._get_pool's lazy creation and caching."""

    async def test_creates_and_caches_the_pool_on_first_call(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        The first call has no cached pool, so it calls create_pool with the client's own DSN and
        caches the result on self._pool.

        :param monkeypatch: pytest's monkeypatch fixture.
        :return: None
        """
        fake_pool: MagicMock = create_autospec(spec=Pool, instance=True)
        create_pool_mock: AsyncMock = AsyncMock(return_value=fake_pool)
        monkeypatch.setattr(target=client_module, name="create_pool", value=create_pool_mock)
        client: PostgresClient = PostgresClient(pg_config=_pg_config())
        pool: Pool = await client._get_pool()
        assert pool is fake_pool
        assert client._pool is fake_pool
        create_pool_mock.assert_awaited_once_with(dsn=client._db_dsn)

    async def test_reuses_the_cached_pool_on_a_later_call(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        A second call with an already-cached pool returns it directly, without calling
        create_pool again.

        :param monkeypatch: pytest's monkeypatch fixture.
        :return: None
        """
        create_pool_mock: AsyncMock = AsyncMock()
        monkeypatch.setattr(target=client_module, name="create_pool", value=create_pool_mock)
        client: PostgresClient = PostgresClient(pg_config=_pg_config())
        cached_pool: MagicMock = create_autospec(spec=Pool, instance=True)
        client._pool = cached_pool
        pool: Pool = await client._get_pool()
        assert pool is cached_pool
        create_pool_mock.assert_not_awaited()


class TestExecute:
    """Tests for PostgresClient._execute."""

    async def test_acquires_a_connection_and_executes_the_query(self) -> None:
        """
        _execute acquires a connection from the pool and awaits conn.execute with the query and
        positional args, returning nothing.

        :return: None
        """
        conn: MagicMock = _connection()
        client: PostgresClient = PostgresClient(pg_config=_pg_config())
        client._pool = _pool_yielding(conn=conn)
        await client._execute("UPDATE t SET x = $2 WHERE id = $1", 1, "y")
        conn.execute.assert_awaited_once_with("UPDATE t SET x = $2 WHERE id = $1", 1, "y")


class TestFetch:
    """Tests for PostgresClient._fetch."""

    async def test_acquires_a_connection_and_returns_every_row(self) -> None:
        """
        _fetch acquires a connection from the pool, awaits conn.fetch with the query and
        positional args, and returns its result as-is.

        :return: None
        """
        conn: MagicMock = _connection()
        rows: list[MagicMock] = [MagicMock(), MagicMock()]
        conn.fetch = AsyncMock(return_value=rows)
        client: PostgresClient = PostgresClient(pg_config=_pg_config())
        client._pool = _pool_yielding(conn=conn)
        result = await client._fetch("SELECT * FROM t WHERE id = $1", 1)
        assert result is rows
        conn.fetch.assert_awaited_once_with("SELECT * FROM t WHERE id = $1", 1)


class TestFetchrow:
    """Tests for PostgresClient._fetchrow."""

    async def test_acquires_a_connection_and_returns_the_row(self) -> None:
        """
        _fetchrow acquires a connection from the pool, awaits conn.fetchrow with the query and
        positional args, and returns its result.

        :return: None
        """
        conn: MagicMock = _connection()
        row: MagicMock = MagicMock()
        conn.fetchrow = AsyncMock(return_value=row)
        client: PostgresClient = PostgresClient(pg_config=_pg_config())
        client._pool = _pool_yielding(conn=conn)
        result = await client._fetchrow("SELECT * FROM t WHERE id = $1", 1)
        assert result is row
        conn.fetchrow.assert_awaited_once_with("SELECT * FROM t WHERE id = $1", 1)

    async def test_returns_none_when_no_row_matches(self) -> None:
        """
        A query matching no row returns None, exactly as conn.fetchrow itself reports it.

        :return: None
        """
        conn: MagicMock = _connection()
        conn.fetchrow = AsyncMock(return_value=None)
        client: PostgresClient = PostgresClient(pg_config=_pg_config())
        client._pool = _pool_yielding(conn=conn)
        result = await client._fetchrow("SELECT * FROM t WHERE id = $1", 999)
        assert result is None


class TestFetchval:
    """Tests for PostgresClient._fetchval."""

    async def test_acquires_a_connection_and_returns_the_value(self) -> None:
        """
        _fetchval acquires a connection from the pool, awaits conn.fetchval with the query and
        positional args, and returns its result.

        :return: None
        """
        conn: MagicMock = _connection()
        conn.fetchval = AsyncMock(return_value=42)
        client: PostgresClient = PostgresClient(pg_config=_pg_config())
        client._pool = _pool_yielding(conn=conn)
        result = await client._fetchval("SELECT counter FROM t WHERE month = $1", "2026.10")
        assert result == 42
        conn.fetchval.assert_awaited_once_with("SELECT counter FROM t WHERE month = $1", "2026.10")

    async def test_returns_none_when_no_row_matches(self) -> None:
        """
        A query matching no row returns None, exactly as conn.fetchval itself reports it.

        :return: None
        """
        conn: MagicMock = _connection()
        conn.fetchval = AsyncMock(return_value=None)
        client: PostgresClient = PostgresClient(pg_config=_pg_config())
        client._pool = _pool_yielding(conn=conn)
        result = await client._fetchval("SELECT counter FROM t WHERE month = $1", "1999.01")
        assert result is None


class TestClose:
    """Tests for PostgresClient._close."""

    async def test_closes_and_clears_an_existing_pool(self) -> None:
        """
        An existing pool is closed and self._pool is reset to None.

        :return: None
        """
        pool: MagicMock = create_autospec(spec=Pool, instance=True)
        client: PostgresClient = PostgresClient(pg_config=_pg_config())
        client._pool = pool
        await client._close()
        pool.close.assert_awaited_once_with()
        assert client._pool is None

    async def test_is_a_no_op_without_a_pool(self) -> None:
        """
        Closing a client that never opened a pool does nothing and raises nothing.

        :return: None
        """
        client: PostgresClient = PostgresClient(pg_config=_pg_config())
        await client._close()
        assert client._pool is None
