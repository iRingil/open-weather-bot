"""Module for configuring logging in the application."""

import logging
from pathlib import Path
from sys import stderr

from loguru import logger

__all__: tuple[str, ...] = ("LoggingManager", "InterceptHandler")


class InterceptHandler(logging.Handler):
    """Intercepts standard logging messages and redirects them to Loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        """
        Redirects a standard logging message to Loguru.

        :param record: Standard logging record.
        :return: None
        """
        try:
            level: str | int = logger.level(name=record.levelname).name
        except ValueError:
            level = record.levelno
        # emit()'s own frame is already inside logging.__file__, so the walk must start at its
        # caller (always Handler.handle) or every record gets attributed to logging/__init__.py
        # instead of the real caller; depth starts at 1 to count that first hop.
        frame, depth = logging.currentframe().f_back, 1
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


class LoggingManager:
    """Performs logging settings in the application."""

    def __init__(self, debug: bool, log_dir: Path, project_name: str) -> None:
        """
        Initializes the logging manager.

        :param debug: Enables debug-level logging and detailed formatting if True.
        :param log_dir: Path to the directory where logs will be stored.
        :param project_name: Name of the project, used as the log file name.
        :return: None
        """
        logger.remove()
        # Forming the log format
        time_format: str = "<green>{time:YYYY-MM-DD HH:mm:ss}</green>"
        level_format: str = "<level>{level: <8}</level>"
        # Add detailed information only in DEBUG mode
        debug_info_format: str = "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | " if debug else ""
        message_format: str = "<level>{message}</level>"
        # Assembling the final format for the console
        console_format: str = f"{time_format} | {level_format} | {debug_info_format}{message_format}"
        # Determine the logging level depending on the mode
        log_level: int = logging.DEBUG if debug else logging.INFO
        # Configuring the 'receiver' for the console
        logger.add(sink=stderr, level=log_level, format=console_format, colorize=True)
        # Configuring the 'receiver' for the file
        log_dir.mkdir(parents=True, exist_ok=True)
        logger.add(
            sink=log_dir / f"{project_name.replace(' ', '-')}.log",
            level=log_level,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
            encoding="utf-8",
            enqueue=True,  # Makes logging asynchronous
            backtrace=True,
            diagnose=debug,  # Enables detailed error diagnosis in DEBUG mode
        )
        self._setup_intercept_handler(log_level=log_level)

    @staticmethod
    def _setup_intercept_handler(log_level: int) -> None:
        """
        Sets up the InterceptHandler to redirect standard logging to Loguru.

        :param log_level: The logging level to set for the standard logger.
        :return: None
        """
        standard_logger: logging.Logger = logging.getLogger()
        intercept_handler: InterceptHandler = InterceptHandler()
        standard_logger.handlers = [intercept_handler]
        standard_logger.setLevel(level=log_level)
        # Pillow logs a DEBUG line per PNG chunk on every forecast image it opens or saves.
        logging.getLogger("PIL").setLevel(logging.INFO)
