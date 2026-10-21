"""The module contains middlewares used by the bot."""

from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from time import monotonic
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User

__all__: tuple[str] = ("AntiFloodMiddleware",)


class AntiFloodMiddleware(BaseMiddleware):
    """
    Drops updates from a user who exceeds a fixed number of updates within a sliding time window.

    :cvar _limit: Maximum number of updates allowed from one user within the time window.
    :cvar _period: Length of the sliding time window, in seconds.
    """

    _limit: int = 3
    _period: float = 2.0

    def __init__(self) -> None:
        """Initializes the per-user history of update timestamps."""
        self._hits: dict[int, deque[float]] = defaultdict(deque)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """
        Drops the update if the sending user has exceeded the rate limit, otherwise calls the handler.

        :param handler: Wrapped handler in the middlewares chain.
        :param event: Incoming event.
        :param data: Contextual data, expected to already contain "event_from_user".
        :return: The handler's result, or None if the update was dropped.
        """
        # No user to key the rate limit by, so nothing to throttle.
        user: User | None = data.get("event_from_user")
        if user is None:
            return await handler(event, data)
        now: float = monotonic()
        hits: deque[float] = self._hits[user.id]
        # Drop hits that fell out of the sliding window.
        while hits and now - hits[0] > self._period:
            hits.popleft()
        # Rate limit exceeded within the window - drop the update.
        if len(hits) >= self._limit:
            return None
        hits.append(now)
        return await handler(event, data)
