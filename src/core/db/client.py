"""
Low-level async PostgreSQL client with connection pooling.

Implements only generic execute/fetch primitives over a connection pool.
"""

from typing import cast
from urllib.parse import quote

from asyncpg import Pool, Record, create_pool

from core.config import PostgresConfig

__all__: tuple[str, ...] = ("PostgresClient",)


class PostgresClient:
    """Low-level async PostgreSQL client with connection pooling."""

    def __init__(self, pg_config: PostgresConfig) -> None:
        """:param pg_config: PostgreSQL connection configuration."""
        self._db_dsn: str = self._build_dsn(pg_config=pg_config)
        self._pool: Pool | None = None

    @staticmethod
    def _build_dsn(pg_config: PostgresConfig) -> str:
        """
        Builds a PostgreSQL DSN string from the configuration.

        Username/password are percent encoded so credentials containing DSN-special characters (@, :, /, ?, #) don't get
        misparsed.

        :param pg_config: PostgreSQL connection configuration.
        :return: PostgreSQL connection string.
        """
        username: str = quote(pg_config.username, safe="")
        password: str = quote(pg_config.password.get_secret_value(), safe="")
        if pg_config.use_socket:
            return f"postgresql://{username}:{password}@/{pg_config.database}?host={pg_config.socket_path}"
        return f"postgresql://{username}:{password}@{pg_config.host}:{pg_config.port}/{pg_config.database}"

    async def _get_pool(self) -> Pool:
        """
        Creates and returns a pool of database connections.

        :return: An instance of asyncpg.pool.Pool.
        """
        pool: Pool | None = self._pool
        if pool is None:
            pool = await create_pool(dsn=self._db_dsn)
            self._pool = pool
        return pool

    async def _execute(self, query: str, *args: object) -> None:
        """
        Executes a command in the database.

        :param query: The database query to execute.
        :param args: Positional arguments for the query.
        :return: None
        """
        pool: Pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(query, *args)

    async def _fetch(self, query: str, *args: object) -> list[Record]:
        """
        Fetches multiple records from the database.

        :param query: The database query to execute.
        :param args: Positional arguments for the query.
        :return: A list of database records.
        """
        pool: Pool = await self._get_pool()
        async with pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def _fetchrow(self, query: str, *args: object) -> Record | None:
        """
        Fetches a single record from the database.

        :param query: The database query to execute.
        :param args: Positional arguments for the query.
        :return: A single database record or None if no record found.
        """
        pool: Pool = await self._get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def _fetchval(self, query: str, *args: object) -> object:
        """
        Fetches a single value from the database.

        :param query: The database query to execute.
        :param args: Positional arguments for the query.
        :return: The value of the first column of the first row, or None if no row found.
        """
        pool: Pool = await self._get_pool()
        async with pool.acquire() as conn:
            value: object = cast("object", await conn.fetchval(query, *args))
            return value

    async def _close(self) -> None:
        """
        Closes the database connection pool.

        :return: None
        """
        if self._pool:
            await self._pool.close()
            self._pool = None
