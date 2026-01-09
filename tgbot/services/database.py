"""Model describing the work with the database"""

from datetime import datetime
from typing import Any

# pylint: disable=unused-import
from asyncpg import Connection, Pool, Record, create_pool

from tgbot.config import load_config
from tgbot.services.classes import User, UserWeatherSettings


__all__: tuple[str, ...] = ("Database", "User", "database")


class Database:
    """A class for working with the database"""

    def __init__(self, db_dsn: str) -> None:
        """
        Defines the parameters of the database.

        :param db_dsn: PgDB connection string.
        """
        self._db_dsn: str = db_dsn
        self._pool: Pool | None = None

    async def _get_pool(self) -> Pool:
        """
        Creates and returns a pool of database connections.

        :return: An instance of asyncpg.pool.Pool
        """
        if self._pool is None:
            # noinspection PyUnresolvedReferences
            self._pool = await create_pool(dsn=self._db_dsn, max_size=50)
        return self._pool

    async def _execute(self, query: str, *args: Any) -> None:
        """
        Executes a command in the database.

        :param query: The database query to execute.
        :param args: Positional arguments for the query.
        :return: None
        """
        pool: Pool = await self._get_pool()
        async with pool.acquire() as conn:  # type: Connection
            await conn.execute(query, *args)

    async def _fetchrow(self, query: str, *args: Any) -> Record | None:
        """
        Fetches a single record from the database.

        :param query: The database query to execute.
        :param args: Positional arguments for the query.
        :return: A single database record or None if no record found.
        """
        pool: Pool = await self._get_pool()
        async with pool.acquire() as conn:  # type: Connection
            return await conn.fetchrow(query, *args)

    async def _fetch(self, query: str, *args: Any) -> list[Record]:
        """
        Fetches multiple records from the database.

        :param query: The database query to execute.
        :param args: Positional arguments for the query.
        :return: A list of database records.
        """
        pool: Pool = await self._get_pool()
        async with pool.acquire() as conn:  # type: Connection
            result: list[Record] = await conn.fetch(query, *args)
            return result

    async def _fetchval(self, query: str, *args: Any) -> Any | None:
        """
        Fetches a single value from the database.

        :param query: The database query to execute.
        :param args: Positional arguments for the query.
        :return: A single database value or None if no value found.
        """
        pool: Pool = await self._get_pool()
        async with pool.acquire() as conn:  # type: Connection
            return await conn.fetchval(query, *args)

    async def create_tables(self) -> None:
        """
        Creates tables in the database.

        :return: None
        """
        create_table_users: str = """
            CREATE TABLE IF NOT EXISTS users (
                id BIGINT PRIMARY KEY,
                dialog_id BIGINT NOT NULL,
                lang VARCHAR(2),
                city VARCHAR(72),
                latitude DOUBLE PRECISION,
                longitude DOUBLE PRECISION,
                units VARCHAR(8)
            );
        """
        api_request_counters: str = """
            CREATE TABLE IF NOT EXISTS api_request_counters (
                month VARCHAR(7) PRIMARY KEY,
                counter INTEGER NOT NULL DEFAULT 0
            );
        """
        await self._execute(query=create_table_users)
        await self._execute(query=api_request_counters)

    async def save_dialog_id(self, user_id: int, dialog_id: int) -> None:
        """
        Saves the identifier of the dialog message with the user in the database.

        :param user_id: Telegram user id.
        :param dialog_id: Last dialogue message id.
        :return: None
        """
        query: str = """
            INSERT INTO users (id, dialog_id) VALUES ($1, $2)
            ON CONFLICT (id) DO UPDATE SET dialog_id=excluded.dialog_id;
        """
        await self._execute(query, user_id, dialog_id)

    async def save_city_coords(self, user_id: int, city: str, latitude: float, longitude: float) -> None:
        """
        Saves the coordinates of the selected city in the database.

        :param user_id: Telegram user id.
        :param city: Selected city name.
        :param latitude: Selected city latitude.
        :param longitude: Selected city longitude.
        :return: None
        """
        query: str = """UPDATE users SET city=$1, latitude=$2, longitude=$3 WHERE id=$4;"""
        await self._execute(query, city, latitude, longitude, user_id)

    async def save_user_settings(self, user_id: int, lang_code: str, measure_units: str) -> None:
        """
        Saves the user's weather settings in the database.

        :param user_id: Telegram user id.
        :param lang_code: User language code.
        :param measure_units: Measurement units ('metric' or 'imperial').
        :return: None
        """
        query: str = """UPDATE users SET lang=$1, units=$2 WHERE id=$3;"""
        await self._execute(query, lang_code, measure_units, user_id)

    async def get_dialog_id_if_exists(self, user_id: int) -> int | None:
        """
        Returns the id of the dialog message with the user from the database.

        :param user_id: Telegram user id.
        :return: Last dialogue message id or None.
        """
        query: str = """SELECT dialog_id FROM users WHERE id=$1;"""
        row: Record | None = await self._fetchrow(query, user_id)
        return row["dialog_id"] if row else None

    async def get_user_settings(self, user_id: int) -> UserWeatherSettings:
        """
        Returns the user's weather settings.

        :param user_id: Telegram user id.
        :return: User weather settings as UserWeatherSettings object.
        """
        query: str = """SELECT lang, city, latitude, longitude, units FROM users WHERE id=$1;"""
        row: Record = await self._fetchrow(query, user_id)
        return UserWeatherSettings(
            lang=row["lang"], city=row["city"], latitude=row["latitude"], longitude=row["longitude"], units=row["units"]
        )

    async def get_list_all_users(self) -> list[User]:
        """
        Returns the list of all users.

        :return: List of all bot users as User objects.
        """
        query: str = """SELECT id, dialog_id FROM users WHERE units IS NOT NULL;"""
        return [User(id=row["id"], dialog_id=row["dialog_id"]) for row in await self._fetch(query=query)]

    async def delete_user(self, user_id: int) -> None:
        """
        Deletes a user from the database.

        :param user_id: Telegram user id.
        :return: None
        """
        query: str = """DELETE FROM users WHERE id=$1;"""
        await self._execute(query, user_id)

    async def get_number_of_users(self) -> int:
        """
        Returns the number of users in the database.

        :return: Number of users in the database.
        """
        query: str = """SELECT COUNT(*) FROM users;"""
        users_count: int | None = await self._fetchval(query=query)
        return users_count if users_count is not None else 0

    async def get_api_counter_value(self) -> int:
        """
        Returns the number of requests to OpenWeatherAPI made since the beginning of the month.

        :return: Number of requests to OpenWeatherAPI.
        """
        query: str = """SELECT counter FROM api_request_counters WHERE month=$1;"""
        requests_count: int | None = await self._fetchval(query, datetime.now().strftime("%Y.%m"))
        return requests_count if requests_count is not None else 0

    async def increase_api_counter(self) -> None:
        """
        Increases OpenWeatherMap API request counter value.

        :return: None
        """
        query: str = """
            INSERT INTO api_request_counters (month, counter) VALUES ($1, $2)
            ON CONFLICT (month) DO UPDATE SET counter=api_request_counters.counter+1;
        """
        await self._execute(query, datetime.now().strftime("%Y.%m"), 1)

    async def close(self) -> None:
        """
        Closes the database connection pool.

        :return: None
        """
        if self._pool:
            await self._pool.close()
            self._pool = None


database: Database = Database(db_dsn=load_config().pg_dsn)
