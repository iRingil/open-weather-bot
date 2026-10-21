"""Typed query layer over PostgreSQL.

Wraps PostgresClient's protected _execute/_fetch/etc. primitives in typed methods that
convert asyncpg.Record rows into this project's own types.

The schema is shared with the previous (aiogram 2) version of the bot and must stay
compatible with it: tables, columns and the api_request_counters month format are unchanged.
"""

from datetime import datetime

from asyncpg import Record

from core.config import PostgresConfig
from core.db.client import PostgresClient
from core.db.data_types import Units, UserSettings

__all__: tuple[str] = ("Database",)


class Database(PostgresClient):
    """Typed query layer over PostgreSQL."""

    def __init__(self, pg_config: PostgresConfig) -> None:
        """
        Initializes the database.

        :param pg_config: PostgreSQL connection configuration.
        """
        PostgresClient.__init__(self, pg_config=pg_config)

    # region Create Tables
    async def create_tables(self) -> None:
        """
        Creates every table in the schema, if it doesn't exist yet.

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
        create_table_api_request_counters: str = """
            CREATE TABLE IF NOT EXISTS api_request_counters (
                month VARCHAR(7) PRIMARY KEY,
                counter INTEGER NOT NULL DEFAULT 0
            );
        """
        for query in (create_table_users, create_table_api_request_counters):
            await self._execute(query=query)

    # endregion

    # region Users
    async def save_dialog_id(self, user_id: int, dialog_id: int) -> None:
        """
        Saves the ID of the user's dialog message, creating the user's row if it doesn't exist yet.

        :param user_id: Telegram user ID.
        :param dialog_id: ID of the user's dialog message.
        :return: None
        """
        query: str = """
            INSERT INTO users (id, dialog_id) VALUES ($1, $2)
            ON CONFLICT (id) DO UPDATE SET dialog_id = EXCLUDED.dialog_id
        """
        await self._execute(query, user_id, dialog_id)

    async def get_dialog_id(self, user_id: int) -> int | None:
        """
        Returns the ID of the user's dialog message.

        :param user_id: Telegram user ID.
        :return: ID of the dialog message, or None if the user has no row.
        """
        dialog_id: int | None = await self._fetchval("SELECT dialog_id FROM users WHERE id = $1", user_id)
        return dialog_id

    async def save_user_settings(self, settings: UserSettings) -> None:
        """
        Saves the result of the weather setup dialog, creating the user's row if it doesn't exist
        (e.g. it was deleted by /stop in another window while the dialog was still open).

        :param settings: The user's weather settings.
        :return: None
        """
        query: str = """
            INSERT INTO users (id, dialog_id, lang, city, latitude, longitude, units)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (id) DO UPDATE SET
                dialog_id = EXCLUDED.dialog_id,
                lang = EXCLUDED.lang,
                city = EXCLUDED.city,
                latitude = EXCLUDED.latitude,
                longitude = EXCLUDED.longitude,
                units = EXCLUDED.units
        """
        await self._execute(
            query,
            settings.user_id,
            settings.dialog_id,
            settings.lang,
            settings.city,
            settings.latitude,
            settings.longitude,
            settings.units,
        )

    @staticmethod
    def _settings_from_row(row: Record) -> UserSettings:
        """
        Converts a users-table row into UserSettings.

        :param row: Raw database record from the users table.
        :return: The row as a typed UserSettings.
        """
        return UserSettings(
            user_id=row["id"],
            dialog_id=row["dialog_id"],
            lang=row["lang"],
            city=row["city"],
            latitude=row["latitude"],
            longitude=row["longitude"],
            units=Units(row["units"]),
        )

    async def get_user_settings(self, user_id: int) -> UserSettings | None:
        """
        Returns the weather settings of one user.

        :param user_id: Telegram user ID.
        :return: The user's settings, or None if the user hasn't finished the setup dialog.
        """
        query: str = """
            SELECT id, dialog_id, lang, city, latitude, longitude, units FROM users WHERE id = $1 AND units IS NOT NULL
        """
        row: Record | None = await self._fetchrow(query, user_id)
        return self._settings_from_row(row=row) if row is not None else None

    async def get_all_user_settings(self) -> list[UserSettings]:
        """
        Returns the weather settings of every user who finished the setup dialog.

        :return: List of user settings.
        """
        rows: list[Record] = await self._fetch(
            "SELECT id, dialog_id, lang, city, latitude, longitude, units FROM users WHERE units IS NOT NULL"
        )
        return [self._settings_from_row(row=row) for row in rows]

    async def delete_user(self, user_id: int) -> None:
        """
        Deletes a user's row.

        :param user_id: Telegram user ID.
        :return: None
        """
        await self._execute("DELETE FROM users WHERE id = $1", user_id)

    async def get_number_of_users(self) -> int:
        """
        Returns the number of rows in the users table.

        :return: Number of users.
        """
        users_count: int | None = await self._fetchval("SELECT COUNT(*) FROM users")
        return users_count or 0

    # endregion

    # region API request counter
    @staticmethod
    def _current_month() -> str:
        """
        Returns the key of the current month in the api_request_counters table.

        :return: Current month as 'YYYY.MM'.
        """
        return datetime.now().strftime("%Y.%m")

    async def get_api_counter_value(self) -> int:
        """
        Returns the number of OpenWeatherMap API requests made since the beginning of the month.

        :return: Number of requests.
        """
        query: str = "SELECT counter FROM api_request_counters WHERE month = $1"
        requests_count: int | None = await self._fetchval(query, self._current_month())
        return requests_count or 0

    async def increase_api_counter(self, count: int = 1) -> None:
        """
        Increases the OpenWeatherMap API request counter of the current month.

        :param count: Number of requests to add.
        :return: None
        """
        query: str = """
            INSERT INTO api_request_counters (month, counter) VALUES ($1, $2)
            ON CONFLICT (month) DO UPDATE SET counter = api_request_counters.counter + EXCLUDED.counter
        """
        await self._execute(query, self._current_month(), count)

    # endregion

    async def close(self) -> None:
        """
        Closes the database connection pool.

        :return: None
        """
        await self._close()
