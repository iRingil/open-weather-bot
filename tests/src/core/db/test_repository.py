"""
Tests for src/core/db/repository.py (Database) against the test PostgreSQL (see tests/conftest.py).

Every test starts with freshly created, empty tables. The schema is shared with the previous (aiogram 2) bot
version still running on the same database, so it is checked column by column in information_schema.
"""

# ruff: noqa: PLR2004, S101, SLF001

import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from asyncpg import Connection

from core.db.data_types import Units, UserSettings
from core.db.repository import Database

if TYPE_CHECKING:
    from asyncpg import Record

__all__: tuple = ()

_KYIV: UserSettings = UserSettings(
    user_id=42, dialog_id=7, lang="uk", city="Kyiv", latitude=50.45, longitude=30.52, units=Units.METRIC
)
_BOSTON: UserSettings = UserSettings(
    user_id=43, dialog_id=8, lang="en", city="Boston", latitude=42.36, longitude=-71.06, units=Units.IMPERIAL
)


async def _columns(conn: Connection, table: str) -> list[tuple[object, ...]]:
    """
    Describes the columns of a table.

    :param conn: The plain connection to the test database.
    :param table: Table name.
    :return: (name, type, max length, nullable, default) of every column, in column order.
    """
    query: str = """
        SELECT column_name, data_type, character_maximum_length, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = $1
        ORDER BY ordinal_position
    """
    rows: list[Record] = await conn.fetch(query, table)
    return [tuple(row) for row in rows]


async def _primary_key(conn: Connection, table: str) -> list[object]:
    """
    Returns the primary key columns of a table.

    :param conn: The plain connection to the test database.
    :param table: Table name.
    :return: Names of the primary key columns.
    """
    query: str = """
        SELECT kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON kcu.constraint_name = tc.constraint_name AND kcu.table_schema = tc.table_schema
        WHERE tc.table_schema = current_schema() AND tc.table_name = $1 AND tc.constraint_type = 'PRIMARY KEY'
    """
    rows: list[Record] = await conn.fetch(query, table)
    return [row["column_name"] for row in rows]


class TestCreateTables:
    """Tests for Database.create_tables: the schema shared with the previous bot version."""

    @pytest.mark.usefixtures("database")
    async def test_users_table_keeps_the_previous_schema(self, pg_conn: Connection) -> None:
        """
        The users table has exactly the previous version's columns, keyed by id.

        :param pg_conn: The plain connection to the test database.
        :return: None
        """
        assert await _columns(conn=pg_conn, table="users") == [
            ("id", "bigint", None, "NO", None),
            ("dialog_id", "bigint", None, "NO", None),
            ("lang", "character varying", 2, "YES", None),
            ("city", "character varying", 72, "YES", None),
            ("latitude", "double precision", None, "YES", None),
            ("longitude", "double precision", None, "YES", None),
            ("units", "character varying", 8, "YES", None),
        ]
        assert await _primary_key(conn=pg_conn, table="users") == ["id"]

    @pytest.mark.usefixtures("database")
    async def test_api_request_counters_table_keeps_the_previous_schema(self, pg_conn: Connection) -> None:
        """
        The api_request_counters table has exactly the previous version's columns, keyed by month.

        :param pg_conn: The plain connection to the test database.
        :return: None
        """
        assert await _columns(conn=pg_conn, table="api_request_counters") == [
            ("month", "character varying", 7, "NO", None),
            ("counter", "integer", None, "NO", "0"),
        ]
        assert await _primary_key(conn=pg_conn, table="api_request_counters") == ["month"]

    async def test_leaves_existing_tables_and_data_untouched(self, database: Database) -> None:
        """
        A second run (every bot start, or the previous version's database) keeps the existing rows.

        :param database: The Database under test.
        :return: None
        """
        await database.save_user_settings(settings=_KYIV)
        await database.increase_api_counter(count=3)
        await database.create_tables()
        assert await database.get_user_settings(user_id=_KYIV.user_id) == _KYIV
        assert await database.get_api_counter_value() == 3


class TestDialogId:
    """Tests for Database.save_dialog_id / get_dialog_id."""

    async def test_creates_a_row_with_only_the_dialog_id(self, database: Database) -> None:
        """
        An unknown user gets a row with the dialog ID and no settings - not a finished setup.

        :param database: The Database under test.
        :return: None
        """
        await database.save_dialog_id(user_id=42, dialog_id=7)
        assert await database.get_dialog_id(user_id=42) == 7
        assert await database.get_user_settings(user_id=42) is None
        assert await database.get_number_of_users() == 1

    async def test_updates_only_the_dialog_id_of_an_existing_user(self, database: Database) -> None:
        """
        An existing user keeps their settings, only the dialog ID changes.

        :param database: The Database under test.
        :return: None
        """
        await database.save_user_settings(settings=_KYIV)
        await database.save_dialog_id(user_id=_KYIV.user_id, dialog_id=99)
        assert await database.get_user_settings(user_id=_KYIV.user_id) == _KYIV._replace(dialog_id=99)
        assert await database.get_number_of_users() == 1

    async def test_get_returns_none_for_an_unknown_user(self, database: Database) -> None:
        """
        No row means None.

        :param database: The Database under test.
        :return: None
        """
        assert await database.get_dialog_id(user_id=42) is None


class TestUserSettings:
    """Tests for Database.save_user_settings / get_user_settings / get_all_user_settings."""

    @pytest.mark.parametrize("settings", [_KYIV, _BOSTON])
    async def test_round_trips_the_settings(self, database: Database, settings: UserSettings) -> None:
        """
        Saved settings come back equal, units as the Units enum.

        :param database: The Database under test.
        :param settings: The settings to save.
        :return: None
        """
        await database.save_user_settings(settings=settings)
        result: UserSettings | None = await database.get_user_settings(user_id=settings.user_id)
        assert result == settings
        assert result is not None
        assert result.units is settings.units

    async def test_stores_units_as_the_plain_string_of_the_previous_version(
        self, database: Database, pg_conn: Connection
    ) -> None:
        """
        The units column holds the same plain string the previous version wrote.

        :param database: The Database under test.
        :param pg_conn: The plain connection to the test database.
        :return: None
        """
        await database.save_user_settings(settings=_BOSTON)
        raw: object = await pg_conn.fetchval("SELECT units FROM users WHERE id = $1", _BOSTON.user_id)
        assert type(raw) is str
        assert raw == "imperial"

    async def test_overwrites_every_column_of_an_existing_user(self, database: Database) -> None:
        """
        Saving again replaces the whole previous setup.

        :param database: The Database under test.
        :return: None
        """
        await database.save_user_settings(settings=_KYIV)
        changed: UserSettings = _BOSTON._replace(user_id=_KYIV.user_id)
        await database.save_user_settings(settings=changed)
        assert await database.get_user_settings(user_id=_KYIV.user_id) == changed
        assert await database.get_number_of_users() == 1

    async def test_completes_a_row_holding_only_the_dialog_id(self, database: Database) -> None:
        """
        Finishing the setup fills in the row that /start created.

        :param database: The Database under test.
        :return: None
        """
        await database.save_dialog_id(user_id=_KYIV.user_id, dialog_id=1)
        await database.save_user_settings(settings=_KYIV)
        assert await database.get_user_settings(user_id=_KYIV.user_id) == _KYIV

    async def test_get_returns_none_for_an_unknown_user(self, database: Database) -> None:
        """
        No row means None.

        :param database: The Database under test.
        :return: None
        """
        assert await database.get_user_settings(user_id=42) is None

    async def test_get_all_returns_only_users_who_finished_the_setup(self, database: Database) -> None:
        """
        Every user with settings is returned; a user with only a dialog ID is not.

        :param database: The Database under test.
        :return: None
        """
        await database.save_user_settings(settings=_KYIV)
        await database.save_user_settings(settings=_BOSTON)
        await database.save_dialog_id(user_id=44, dialog_id=9)
        result: list[UserSettings] = await database.get_all_user_settings()
        assert sorted(result) == [_KYIV, _BOSTON]

    async def test_get_all_returns_an_empty_list_without_users(self, database: Database) -> None:
        """
        An empty table gives an empty list.

        :param database: The Database under test.
        :return: None
        """
        assert await database.get_all_user_settings() == []


class TestDeleteUser:
    """Tests for Database.delete_user."""

    async def test_deletes_only_that_users_row(self, database: Database) -> None:
        """
        The user's row is gone, other users stay.

        :param database: The Database under test.
        :return: None
        """
        await database.save_user_settings(settings=_KYIV)
        await database.save_user_settings(settings=_BOSTON)
        await database.delete_user(user_id=_KYIV.user_id)
        assert await database.get_dialog_id(user_id=_KYIV.user_id) is None
        assert await database.get_all_user_settings() == [_BOSTON]

    async def test_an_unknown_user_is_a_no_op(self, database: Database) -> None:
        """
        Deleting a user without a row raises nothing.

        :param database: The Database under test.
        :return: None
        """
        await database.delete_user(user_id=42)
        assert await database.get_number_of_users() == 0


class TestGetNumberOfUsers:
    """Tests for Database.get_number_of_users."""

    async def test_counts_every_row(self, database: Database) -> None:
        """
        Users with and without a finished setup are all counted.

        :param database: The Database under test.
        :return: None
        """
        await database.save_user_settings(settings=_KYIV)
        await database.save_dialog_id(user_id=44, dialog_id=9)
        assert await database.get_number_of_users() == 2

    async def test_an_empty_table_counts_zero(self, database: Database) -> None:
        """
        An empty table counts 0.

        :param database: The Database under test.
        :return: None
        """
        assert await database.get_number_of_users() == 0


class TestApiCounter:
    """Tests for Database.get_api_counter_value / increase_api_counter and their month key."""

    def test_month_key_has_the_previous_versions_format(self) -> None:
        """
        The month key is 'YYYY.MM' of the UTC time - the exact format the previous version wrote.

        :return: None
        """
        key: str = Database._current_month()
        assert re.fullmatch(r"\d{4}\.\d{2}", key)
        assert key == datetime.now(UTC).strftime("%Y.%m")

    async def test_a_month_without_requests_counts_zero(self, database: Database) -> None:
        """
        No row for the current month means 0.

        :param database: The Database under test.
        :return: None
        """
        assert await database.get_api_counter_value() == 0

    async def test_increase_creates_and_then_adds_to_the_months_row(
        self, database: Database, pg_conn: Connection
    ) -> None:
        """
        The first increase creates the month's row (by 1 by default), later ones add to it.

        :param database: The Database under test.
        :param pg_conn: The plain connection to the test database.
        :return: None
        """
        await database.increase_api_counter()
        assert await database.get_api_counter_value() == 1
        await database.increase_api_counter(count=5)
        assert await database.get_api_counter_value() == 6
        rows: list[Record] = await pg_conn.fetch("SELECT month, counter FROM api_request_counters")
        assert [tuple(row) for row in rows] == [(Database._current_month(), 6)]

    async def test_counts_only_the_current_month(self, database: Database, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Requests of another month are counted in that month's row.

        :param database: The Database under test.
        :param monkeypatch: pytest's monkeypatch fixture, to switch the current month.
        :return: None
        """
        monkeypatch.setattr(target=Database, name="_current_month", value=staticmethod(lambda: "2026.10"))
        await database.increase_api_counter(count=100)
        monkeypatch.setattr(target=Database, name="_current_month", value=staticmethod(lambda: "2026.11"))
        await database.increase_api_counter(count=2)
        assert await database.get_api_counter_value() == 2
        monkeypatch.setattr(target=Database, name="_current_month", value=staticmethod(lambda: "2026.10"))
        assert await database.get_api_counter_value() == 100


class TestClose:
    """Tests for Database.close."""

    async def test_closes_the_pool(self, database: Database) -> None:
        """
        close() closes the pool; the next query opens a new one.

        :param database: The Database under test.
        :return: None
        """
        await database.get_number_of_users()
        await database.close()
        assert database._pool is None
        assert await database.get_number_of_users() == 0
