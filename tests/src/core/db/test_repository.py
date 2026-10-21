"""
Unit tests for src/core/db/repository.py (Database).

No real PostgreSQL: PostgresClient's own primitives (_execute/_fetch/_fetchrow/_fetchval, covered
by tests/src/core/db/test_client.py) are replaced with AsyncMocks on each Database instance. The
tests check the SQL each typed method sends (table, columns, placeholders), the arguments bound
to it, and how raw rows come back as this project's own types. The schema is shared with the
previous (aiogram 2) bot version still running on the same database, so the DDL is pinned down
column by column.
"""

import re
from datetime import datetime
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from pydantic import SecretStr

from core.config import PostgresConfig
from core.db import repository
from core.db.data_types import Units, UserSettings
from core.db.repository import Database

__all__: tuple = ()

# pylint: disable=protected-access


def _mock(method: Any) -> AsyncMock:
    """
    Types a primitive the db fixture replaced with an AsyncMock as one.

    :param method: A mocked Database primitive, e.g. db._execute.
    :return: The same object, typed as AsyncMock.
    """
    return cast(AsyncMock, method)


def _await_args(method: Any) -> tuple[Any, ...]:
    """
    Returns the positional arguments of the last await of a mocked Database primitive.

    :param method: A mocked Database primitive, e.g. db._execute.
    :return: The positional arguments, the query first.
    """
    await_args = _mock(method).await_args
    assert await_args is not None
    return tuple(await_args.args)


def _normalize(sql: str) -> str:
    """
    Collapses every run of whitespace in a SQL string into one space.

    :param sql: Raw SQL text.
    :return: Single-line SQL text.
    """
    return re.sub(r"\s+", " ", sql).strip()


def _row(units: str = "metric") -> dict[str, object]:
    """
    Builds a fake users-table row - asyncpg.Record supports the same item access as a dict.

    :param units: Raw units column value.
    :return: The fake row.
    """
    return {
        "id": 42,
        "dialog_id": 7,
        "lang": "uk",
        "city": "Kyiv",
        "latitude": 50.45,
        "longitude": 30.52,
        "units": units,
    }


@pytest.fixture(name="db")
def db_fixture() -> Database:
    """
    A Database whose PostgresClient primitives are AsyncMocks - no pool is ever created.

    :return: The Database instance.
    """
    database: Database = Database(
        pg_config=PostgresConfig(
            host="localhost",
            port=5432,
            database="db",
            username="user",
            password=SecretStr("pass"),
            socket_path=None,
            use_socket=False,
        )
    )
    database._execute = AsyncMock(return_value=None)  # type: ignore [method-assign]
    database._fetch = AsyncMock(return_value=[])  # type: ignore [method-assign]
    database._fetchrow = AsyncMock(return_value=None)  # type: ignore [method-assign]
    database._fetchval = AsyncMock(return_value=None)  # type: ignore [method-assign]
    return database


class TestCreateTables:
    """Tests for Database.create_tables: the schema shared with the previous bot version."""

    async def test_creates_both_tables_with_the_unchanged_schema(self, db: Database) -> None:
        """
        users and api_request_counters are created with exactly the previous version's columns,
        each with CREATE TABLE IF NOT EXISTS so an existing database is left untouched.

        :param db: The Database fixture.
        :return: None
        """
        await db.create_tables()
        queries: list[str] = [_normalize(call.kwargs["query"]) for call in _mock(db._execute).await_args_list]
        assert queries == [
            "CREATE TABLE IF NOT EXISTS users ( id BIGINT PRIMARY KEY, dialog_id BIGINT NOT NULL, "
            "lang VARCHAR(2), city VARCHAR(72), latitude DOUBLE PRECISION, longitude DOUBLE PRECISION, "
            "units VARCHAR(8) );",
            "CREATE TABLE IF NOT EXISTS api_request_counters ( month VARCHAR(7) PRIMARY KEY, "
            "counter INTEGER NOT NULL DEFAULT 0 );",
        ]


class TestSaveDialogId:
    """Tests for Database.save_dialog_id."""

    async def test_upserts_the_dialog_id(self, db: Database) -> None:
        """
        The row is inserted, or only its dialog_id updated if the user already exists.

        :param db: The Database fixture.
        :return: None
        """
        await db.save_dialog_id(user_id=42, dialog_id=7)
        query, *args = _await_args(db._execute)
        assert _normalize(query) == (
            "INSERT INTO users (id, dialog_id) VALUES ($1, $2) "
            "ON CONFLICT (id) DO UPDATE SET dialog_id = EXCLUDED.dialog_id"
        )
        assert args == [42, 7]


class TestGetDialogId:
    """Tests for Database.get_dialog_id."""

    async def test_returns_the_stored_value(self, db: Database) -> None:
        """
        The dialog_id column of the user's row is returned as is.

        :param db: The Database fixture.
        :return: None
        """
        _mock(db._fetchval).return_value = 7
        assert await db.get_dialog_id(user_id=42) == 7
        query, *args = _await_args(db._fetchval)
        assert _normalize(query) == "SELECT dialog_id FROM users WHERE id = $1"
        assert args == [42]

    async def test_returns_none_for_an_unknown_user(self, db: Database) -> None:
        """
        No row means None.

        :param db: The Database fixture.
        :return: None
        """
        assert await db.get_dialog_id(user_id=42) is None


class TestSaveUserSettings:
    """Tests for Database.save_user_settings."""

    async def test_upserts_every_settings_column(self, db: Database) -> None:
        """
        Every UserSettings field is bound in column order, and an existing row has all of them overwritten.

        :param db: The Database fixture.
        :return: None
        """
        settings: UserSettings = UserSettings(
            user_id=42, dialog_id=7, lang="uk", city="Kyiv", latitude=50.45, longitude=30.52, units=Units.IMPERIAL
        )
        await db.save_user_settings(settings=settings)
        query, *args = _await_args(db._execute)
        assert _normalize(query) == (
            "INSERT INTO users (id, dialog_id, lang, city, latitude, longitude, units) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7) ON CONFLICT (id) DO UPDATE SET "
            "dialog_id = EXCLUDED.dialog_id, lang = EXCLUDED.lang, city = EXCLUDED.city, "
            "latitude = EXCLUDED.latitude, longitude = EXCLUDED.longitude, units = EXCLUDED.units"
        )
        assert args == [42, 7, "uk", "Kyiv", 50.45, 30.52, Units.IMPERIAL]
        assert args[-1] == "imperial"  # stored as the same plain string the previous version wrote


class TestGetUserSettings:
    """Tests for Database.get_user_settings."""

    @pytest.mark.parametrize("raw_units,expected", [("metric", Units.METRIC), ("imperial", Units.IMPERIAL)])
    async def test_converts_the_row(self, db: Database, raw_units: str, expected: Units) -> None:
        """
        The row is converted into UserSettings, with units parsed into the Units enum.

        :param db: The Database fixture.
        :param raw_units: Raw units column value.
        :param expected: The Units member it must become.
        :return: None
        """
        _mock(db._fetchrow).return_value = _row(units=raw_units)
        result: UserSettings | None = await db.get_user_settings(user_id=42)
        assert result == UserSettings(
            user_id=42, dialog_id=7, lang="uk", city="Kyiv", latitude=50.45, longitude=30.52, units=expected
        )
        assert result is not None and result.units is expected

    async def test_only_selects_users_who_finished_the_setup(self, db: Database) -> None:
        """
        The query filters out rows without units (setup not finished) and binds the user ID.

        :param db: The Database fixture.
        :return: None
        """
        await db.get_user_settings(user_id=42)
        query, *args = _await_args(db._fetchrow)
        assert _normalize(query) == (
            "SELECT id, dialog_id, lang, city, latitude, longitude, units FROM users "
            "WHERE id = $1 AND units IS NOT NULL"
        )
        assert args == [42]

    async def test_returns_none_without_a_row(self, db: Database) -> None:
        """
        No matching row means None.

        :param db: The Database fixture.
        :return: None
        """
        assert await db.get_user_settings(user_id=42) is None


class TestGetAllUserSettings:
    """Tests for Database.get_all_user_settings."""

    async def test_converts_every_row(self, db: Database) -> None:
        """
        Every row of users who finished the setup is returned as UserSettings, in order.

        :param db: The Database fixture.
        :return: None
        """
        second: dict[str, object] = {**_row(units="imperial"), "id": 43, "dialog_id": 8}
        _mock(db._fetch).return_value = [_row(), second]
        result: list[UserSettings] = await db.get_all_user_settings()
        assert [(user.user_id, user.dialog_id, user.units) for user in result] == [
            (42, 7, Units.METRIC),
            (43, 8, Units.IMPERIAL),
        ]
        query: str = _await_args(db._fetch)[0]
        assert _normalize(query) == (
            "SELECT id, dialog_id, lang, city, latitude, longitude, units FROM users WHERE units IS NOT NULL"
        )

    async def test_returns_an_empty_list_without_rows(self, db: Database) -> None:
        """
        No rows means an empty list.

        :param db: The Database fixture.
        :return: None
        """
        assert await db.get_all_user_settings() == []


class TestDeleteUser:
    """Tests for Database.delete_user."""

    async def test_deletes_the_users_row(self, db: Database) -> None:
        """
        The user's row is deleted by ID.

        :param db: The Database fixture.
        :return: None
        """
        await db.delete_user(user_id=42)
        query, *args = _await_args(db._execute)
        assert _normalize(query) == "DELETE FROM users WHERE id = $1"
        assert args == [42]


class TestGetNumberOfUsers:
    """Tests for Database.get_number_of_users."""

    async def test_returns_the_count(self, db: Database) -> None:
        """
        COUNT(*) over the whole users table is returned.

        :param db: The Database fixture.
        :return: None
        """
        _mock(db._fetchval).return_value = 12
        assert await db.get_number_of_users() == 12
        assert _normalize(_await_args(db._fetchval)[0]) == "SELECT COUNT(*) FROM users"

    async def test_none_becomes_zero(self, db: Database) -> None:
        """
        A None result is reported as 0.

        :param db: The Database fixture.
        :return: None
        """
        assert await db.get_number_of_users() == 0


class TestApiCounter:
    """Tests for Database.get_api_counter_value / increase_api_counter and their month key."""

    def test_month_key_has_the_previous_versions_format(self) -> None:
        """
        The month key is 'YYYY.MM' of the local time - the exact format the previous version wrote,
        so both versions count into the same row.

        :return: None
        """
        key: str = Database._current_month()
        assert re.fullmatch(r"\d{4}\.\d{2}", key)
        assert key == datetime.now().strftime("%Y.%m")

    async def test_get_reads_the_current_month(self, db: Database, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        The counter of the current month is read and returned.

        :param db: The Database fixture.
        :param monkeypatch: pytest's monkeypatch fixture, to pin the current month.
        :return: None
        """
        monkeypatch.setattr(target=repository.Database, name="_current_month", value=staticmethod(lambda: "2026.10"))
        _mock(db._fetchval).return_value = 1500
        assert await db.get_api_counter_value() == 1500
        query, *args = _await_args(db._fetchval)
        assert _normalize(query) == "SELECT counter FROM api_request_counters WHERE month = $1"
        assert args == ["2026.10"]

    async def test_get_returns_zero_for_a_month_without_requests(self, db: Database) -> None:
        """
        No row for the current month means 0.

        :param db: The Database fixture.
        :return: None
        """
        assert await db.get_api_counter_value() == 0

    @pytest.mark.parametrize("kwargs,expected", [({}, 1), ({"count": 5}, 5)])
    async def test_increase_upserts_by_count(
        self, db: Database, monkeypatch: pytest.MonkeyPatch, kwargs: dict[str, int], expected: int
    ) -> None:
        """
        The counter of the current month is created with, or increased by, count (default 1).

        :param db: The Database fixture.
        :param monkeypatch: pytest's monkeypatch fixture, to pin the current month.
        :param kwargs: Arguments passed to increase_api_counter.
        :param expected: The count expected to be bound.
        :return: None
        """
        monkeypatch.setattr(target=repository.Database, name="_current_month", value=staticmethod(lambda: "2026.10"))
        await db.increase_api_counter(**kwargs)
        query, *args = _await_args(db._execute)
        assert _normalize(query) == (
            "INSERT INTO api_request_counters (month, counter) VALUES ($1, $2) "
            "ON CONFLICT (month) DO UPDATE SET counter = api_request_counters.counter + EXCLUDED.counter"
        )
        assert args == ["2026.10", expected]


class TestClose:
    """Tests for Database.close."""

    async def test_delegates_to_the_client(self, db: Database) -> None:
        """
        close() closes the underlying pool through PostgresClient._close.

        :param db: The Database fixture.
        :return: None
        """
        db._close = AsyncMock(return_value=None)  # type: ignore [method-assign]
        await db.close()
        _mock(db._close).assert_awaited_once_with()
