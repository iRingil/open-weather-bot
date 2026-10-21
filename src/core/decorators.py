"""The module implements the decorators used in the application."""

from functools import wraps
from typing import Any, Callable

from loguru import logger

__all__: tuple[str, ...] = ("handle_exc",)


def handle_exc(func: Callable[..., Any]) -> Callable[..., Any]:
    """
    A decorator that catches exceptions in an async function.

    :param func: The asynchronous function to decorate.
    :return: The decorated function with error handling.
    """

    @wraps(wrapped=func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        """
        Wraps the decorated async function and handles exceptions.

        :param args: Positional arguments passed to the wrapped function.
        :param kwargs: Keyword arguments passed to the wrapped function.
        :return: The result of the wrapped async function, or None if it raised.
        """
        try:
            return await func(*args, **kwargs)
        except Exception as exc:
            logger.exception(f"Task '{func.__name__}' caused an exception: {exc}")
        return None

    return wrapper
