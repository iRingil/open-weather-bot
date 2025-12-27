"""Enables localization."""

from aiogram.contrib.middlewares.i18n import I18nMiddleware

from tgbot.config import LOCALES_DIR

__all__: tuple[str] = ("i18n",)

i18n: I18nMiddleware = I18nMiddleware(domain="tgbot", path=str(LOCALES_DIR))
