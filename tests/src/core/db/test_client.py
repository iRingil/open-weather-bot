"""
Tests for src/core/db/client.py (PostgresClient).

The DSN is checked as a plain string; the pool and the query primitives run against the test PostgreSQL
(see tests/conftest.py), on the users table of the database fixture - a Database is a PostgresClient.
"""

# ruff: noqa: PLR2004, S101, SLF001

from typing import TYPE_CHECKING

import pytest
from asyncpg import Connection
from pydantic import SecretStr

from core.config import PostgresConfig
from core.db.client import PostgresClient
from core.db.repository import Database

if TYPE_CHECKING:
    from asyncpg import Pool, Record

__all__: tuple = ()


def _pg_config(*, use_socket: bool) -> PostgresConfig:
    """
    Builds a throwaway PostgresConfig for the DSN tests - never connected to.

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


@pytest.fixture(name="client")
def client_fixture(database: Database) -> PostgresClient:
    """
    The database fixture as a plain PostgresClient: connected to the test database, with empty tables.

    :param database: The Database fixture.
    :return: The client.
    """
    return database


async def _insert_rows(conn: Connection) -> None:
    """
    Fills the users table with two rows.

    :param conn: The plain connection to the test database.
    :return: None
    """
    await conn.execute("INSERT INTO users (id, dialog_id) VALUES ($1, $2), ($3, $4)", 1, 10, 2, 20)


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
        A socket config builds a socket DSN.

        A socket config builds a DSN with an empty host and a host= query param instead, ignoring
        the config's own host/port fields entirely.

        :return: None
        """
        dsn: str = PostgresClient._build_dsn(pg_config=_pg_config(use_socket=True))
        assert dsn == "postgresql://testuser:testpass@/testdb?host=/var/run/postgresql"

    def test_percent_encodes_special_characters_in_credentials(self) -> None:
        """
        Credentials with DSN-special characters are percent-encoded.

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

    async def test_creates_the_pool_lazily_and_reuses_it(self, pg_config: PostgresConfig) -> None:
        """
        No pool exists before the first call; the first call creates and caches it, later calls reuse it.

        :param pg_config: The test database configuration.
        :return: None
        """
        client: PostgresClient = PostgresClient(pg_config=pg_config)
        assert client._pool is None
        pool: Pool = await client._get_pool()
        assert client._pool is pool
        assert await client._get_pool() is pool
        await client._close()


class TestQueries:
    """Tests for PostgresClient._execute / _fetch / _fetchrow / _fetchval."""

    async def test_execute_changes_the_data(self, client: PostgresClient, pg_conn: Connection) -> None:
        """
        _execute runs the command with its positional arguments bound.

        :param client: The client under test.
        :param pg_conn: The plain connection to the test database.
        :return: None
        """
        await _insert_rows(conn=pg_conn)
        await client._execute("UPDATE users SET dialog_id = $2 WHERE id = $1", 2, 21)
        assert await client._fetchval("SELECT dialog_id FROM users WHERE id = $1", 2) == 21

    async def test_fetch_returns_every_row(self, client: PostgresClient, pg_conn: Connection) -> None:
        """
        _fetch returns every matching row as an asyncpg Record.

        :param client: The client under test.
        :param pg_conn: The plain connection to the test database.
        :return: None
        """
        await _insert_rows(conn=pg_conn)
        rows: list[Record] = await client._fetch("SELECT id, dialog_id FROM users ORDER BY id")
        assert [tuple(row) for row in rows] == [(1, 10), (2, 20)]

    async def test_fetch_returns_an_empty_list_without_rows(self, client: PostgresClient) -> None:
        """
        A query matching no row gives an empty list.

        :param client: The client under test.
        :return: None
        """
        assert await client._fetch("SELECT id FROM users") == []

    async def test_fetchrow_returns_the_row(self, client: PostgresClient, pg_conn: Connection) -> None:
        """
        _fetchrow returns the matching row, its columns accessible by name.

        :param client: The client under test.
        :param pg_conn: The plain connection to the test database.
        :return: None
        """
        await _insert_rows(conn=pg_conn)
        row: Record | None = await client._fetchrow("SELECT id, dialog_id FROM users WHERE id = $1", 1)
        assert row is not None
        assert (row["id"], row["dialog_id"]) == (1, 10)

    async def test_fetchrow_returns_none_without_a_row(self, client: PostgresClient) -> None:
        """
        A query matching no row gives None.

        :param client: The client under test.
        :return: None
        """
        assert await client._fetchrow("SELECT id FROM users WHERE id = $1", 999) is None

    async def test_fetchval_returns_the_first_column(self, client: PostgresClient, pg_conn: Connection) -> None:
        """
        _fetchval returns the first column of the first row.

        :param client: The client under test.
        :param pg_conn: The plain connection to the test database.
        :return: None
        """
        await _insert_rows(conn=pg_conn)
        assert await client._fetchval("SELECT COUNT(*) FROM users") == 2

    async def test_fetchval_returns_none_without_a_row(self, client: PostgresClient) -> None:
        """
        A query matching no row gives None.

        :param client: The client under test.
        :return: None
        """
        assert await client._fetchval("SELECT dialog_id FROM users WHERE id = $1", 999) is None


class TestClose:
    """Tests for PostgresClient._close."""

    async def test_closes_and_clears_an_existing_pool(self, pg_config: PostgresConfig) -> None:
        """
        An open pool is closed and forgotten, so the next query opens a new one.

        :param pg_config: The test database configuration.
        :return: None
        """
        client: PostgresClient = PostgresClient(pg_config=pg_config)
        pool: Pool = await client._get_pool()
        await client._close()
        assert pool.is_closing()
        assert client._pool is None
        assert await client._fetchval("SELECT 1") == 1
        assert client._pool is not pool
        await client._close()

    async def test_is_a_no_op_without_a_pool(self, pg_config: PostgresConfig) -> None:
        """
        Closing a client that never opened a pool does nothing and raises nothing.

        :param pg_config: The test database configuration.
        :return: None
        """
        client: PostgresClient = PostgresClient(pg_config=pg_config)
        await client._close()
        assert client._pool is None
