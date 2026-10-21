"""
Unit tests for src/core/scheduler.py (Scheduler).

The underlying AsyncIOScheduler is replaced with a MagicMock after construction, so no event
loop or real job store is involved - the tests only check what Scheduler asks of it.
"""

from datetime import timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from core.scheduler import Scheduler

__all__: tuple = ()

# pylint: disable=protected-access


@pytest.fixture(name="update_weather")
def update_weather_fixture() -> AsyncMock:
    """
    The coroutine function the scheduler is given to run.

    :return: The mocked coroutine function.
    """
    return AsyncMock(return_value=None)


@pytest.fixture(name="scheduler")
def scheduler_fixture(update_weather: AsyncMock) -> Scheduler:
    """
    A Scheduler whose AsyncIOScheduler is a MagicMock.

    :param update_weather: The update_weather fixture.
    :return: The Scheduler instance.
    """
    instance: Scheduler = Scheduler(update_weather=update_weather)
    instance._instance = MagicMock(spec=AsyncIOScheduler)
    return instance


class TestInit:
    """Tests for Scheduler.__init__."""

    def test_builds_a_utc_asyncio_scheduler(self, update_weather: AsyncMock) -> None:
        """
        The underlying scheduler is an AsyncIOScheduler running in UTC, not the server's zone.

        :param update_weather: The update_weather fixture.
        :return: None
        """
        scheduler: Scheduler = Scheduler(update_weather=update_weather)
        assert isinstance(scheduler._instance, AsyncIOScheduler)
        assert scheduler._instance.timezone == timezone.utc


class TestStart:
    """Tests for Scheduler.start."""

    def test_adds_the_weather_job_every_three_hours_and_starts(
        self, scheduler: Scheduler, update_weather: AsyncMock
    ) -> None:
        """
        The weather update runs at minute 0 of every third hour (UTC), never overlapping itself,
        and the scheduler is started after the job is added.

        :param scheduler: The Scheduler fixture.
        :param update_weather: The update_weather fixture.
        :return: None
        """
        scheduler.start()
        mock: MagicMock = scheduler._instance  # type: ignore [assignment]
        mock.add_job.assert_called_once_with(
            func=update_weather,
            trigger="cron",
            hour="*/3",
            minute=0,
            second=0,
            max_instances=1,
            coalesce=True,
        )
        mock.start.assert_called_once_with()
        assert [name for name, *_ in mock.method_calls] == ["add_job", "start"]


class TestShutdown:
    """Tests for Scheduler.shutdown."""

    @pytest.mark.parametrize("kwargs,expected", [({}, True), ({"wait": False}, False)])
    def test_passes_wait_through(self, scheduler: Scheduler, kwargs: dict[str, bool], expected: bool) -> None:
        """
        shutdown() waits for a running job by default, or not if asked.

        :param scheduler: The Scheduler fixture.
        :param kwargs: Arguments passed to shutdown.
        :param expected: The wait value expected to reach the underlying scheduler.
        :return: None
        """
        scheduler.shutdown(**kwargs)
        scheduler._instance.shutdown.assert_called_once_with(wait=expected)  # type: ignore [attr-defined]
