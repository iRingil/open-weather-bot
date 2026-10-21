"""Thin APScheduler wrapper running the scheduled weather update."""

from datetime import timezone
from typing import Awaitable, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler

__all__: tuple[str] = ("Scheduler",)


class Scheduler:
    """
    Thin wrapper around a single AsyncIOScheduler instance.

    :cvar _UPDATE_HOURS: Cron 'hour' field of the weather update (UTC).
    """

    _UPDATE_HOURS: str = "*/3"

    def __init__(self, update_weather: Callable[[], Awaitable[None]]) -> None:
        """
        Initializes the underlying scheduler.

        :param update_weather: Coroutine function sending fresh weather to every user.
        """
        self._instance: AsyncIOScheduler = AsyncIOScheduler(timezone=timezone.utc)
        self._update_weather: Callable[[], Awaitable[None]] = update_weather

    def start(self) -> None:
        """
        Starts the scheduler.

        :return: None
        """
        self._instance.add_job(
            func=self._update_weather,
            trigger="cron",
            hour=self._UPDATE_HOURS,
            minute=0,
            second=0,
            max_instances=1,
            coalesce=True,
        )
        self._instance.start()

    def shutdown(self, wait: bool = True) -> None:
        """
        Stops the scheduler.

        :param wait: If True, waits for running jobs to finish before returning.
        :return: None
        """
        self._instance.shutdown(wait=wait)
