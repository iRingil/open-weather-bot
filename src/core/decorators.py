"""The module implements the decorators used in the application."""

from collections.abc import Awaitable, Callable, Coroutine
from functools import wraps

from loguru import logger

__all__: tuple[str, ...] = ("handle_exc",)


def handle_exc[**P, R](func: Callable[P, Awaitable[R]]) -> Callable[P, Coroutine[None, None, R | None]]:
    """
    A decorator that catches exceptions in an async function.

    :param func: The asynchronous function to decorate.
    :return: The decorated function with error handling.
    """

    @wraps(wrapped=func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R | None:
        """
        Wraps the decorated async function and handles exceptions.

        :param args: Positional arguments passed to the wrapped function.
        :param kwargs: Keyword arguments passed to the wrapped function.
        :return: The result of the wrapped async function, or None if it raised.
        """
        try:
            return await func(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - logs any failure of a background task
            logger.exception(f"Task '{wrapper.__name__}' caused an exception: {exc}")
        return None

    return wrapper
