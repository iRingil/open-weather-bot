"""Enables logging."""

import logging
import sys

from tgbot.config import LOG_FILE

__all__: tuple[str] = ("logger",)

sys.tracebacklimit = 0

logger: logging.Logger = logging.getLogger(__name__)
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
