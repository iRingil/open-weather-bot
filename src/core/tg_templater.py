"""Module for rendering Jinja2 templates used to display messages to users."""

from contextvars import ContextVar, Token
from decimal import Decimal
from gettext import NullTranslations
from pathlib import Path

from babel.support import Translations
from jinja2 import Environment, FileSystemLoader

__all__: tuple[str] = ("TgTemplater",)

_locale_ctx: ContextVar[str] = ContextVar("locale")


class TgTemplater:
    """Returns the rendered template, based on the passed data."""

    def __init__(self, templates_dir: Path, locale_dir: Path) -> None:
        """
        Initializes the necessary parameters.

        :param templates_dir: Path to the folder containing Jinja2 templates.
        :param locale_dir: Path to the folder containing localization files.
        """
        self._env: Environment = Environment(
            trim_blocks=True,
            lstrip_blocks=True,
            extensions=["jinja2.ext.i18n"],
            loader=FileSystemLoader(searchpath=templates_dir),
            enable_async=True,
        )
        self._locale: Path = locale_dir
        self._translations: dict[str, NullTranslations] = {}
        self._env.install_gettext_callables(  # type: ignore[attr-defined]  # pylint: disable=no-member
            gettext=self._gettext, ngettext=self._ngettext
        )
        self._env.filters["group_digits"] = self._group_digits

    def _load_translations(self, locale: str) -> NullTranslations:
        """
        Lazily loads and caches the Translations object for the given locale.

        :param locale: Language code.
        :return: Translations object for the given locale.
        """
        if locale not in self._translations:
            self._translations[locale] = Translations.load(dirname=self._locale, locales=locale)
        return self._translations[locale]

    def _gettext(self, string: str) -> str:
        """
        Translates a string using the locale stored in the current async context.

        :param string: String to translate.
        :return: Translated string.
        """
        return self._load_translations(locale=_locale_ctx.get()).gettext(message=string)

    def _ngettext(self, singular: str, plural: str, n: int) -> str:
        """
        Translates a plural string using the locale stored in the current async context.

        :param singular: Singular form of the string.
        :param plural: Plural form of the string.
        :param n: Count used to determine the plural form.
        :return: Translated string.
        """
        return self._load_translations(locale=_locale_ctx.get()).ngettext(msgid1=singular, msgid2=plural, n=n)

    def get_locales(self) -> list[str]:
        """
        Returns the list containing available localization languages.

        :return: List of available localization languages.
        """
        return [folder.name for folder in self._locale.iterdir() if folder.is_dir()]

    @staticmethod
    def _smart_trunc(html: str, max_len: int = 4096) -> str:
        """
        Trims the HTML string to the first unclosed tag if it exceeds max_len, or truncates plain text.

        :param html: HTML code string.
        :param max_len: Maximum length of the rendered text.
        :return: Trimmed string.
        """
        suffix: str = "..."
        if len(html) <= max_len:
            return html
        # If there are no tags, just trim the text
        if "<" not in html:
            return html[: max_len - len(suffix)] + suffix
        # Text processing with tags
        html = html[: max_len - len(suffix)]
        tag_stack: list[tuple[str, int]] = []  # Stack (tag name, opening tag start position)
        pos: int = 0
        while pos < len(html):
            if html[pos] == "<":
                is_closing: bool = pos + 1 < len(html) and html[pos + 1] == "/"
                end_pos: int = pos + (2 if is_closing else 1)
                while end_pos < len(html) and html[end_pos] != ">":
                    end_pos += 1
                if end_pos < len(html):  # Full Tag
                    tag_text: str = html[pos : end_pos + 1]
                    tag_name_start: int = 2 if is_closing else 1
                    tag_name: str = ""
                    for i in range(pos + tag_name_start, end_pos):
                        if html[i].isspace():
                            break
                        tag_name += html[i]
                    if not is_closing and not tag_text.endswith("/>"):
                        tag_stack.append((tag_name, pos))
                    elif is_closing and tag_stack and tag_stack[-1][0] == tag_name:
                        tag_stack.pop()
                    pos = end_pos + 1
                else:  # Incomplete tag
                    return html[:pos] + suffix if not tag_stack else html[: tag_stack[-1][1]] + suffix
            else:
                pos += 1
        return html + suffix if not tag_stack else html[: tag_stack[0][1]] + suffix

    @staticmethod
    def _group_digits(value: int | float | Decimal) -> str:
        """
        Jinja2 filter grouping a whole number's digits in 3s with underscores, e.g.
        100000 -> "100_000".

        Underscores, not spaces: a plain space is a normal line-break point, so Telegram happily
        wraps a long number (or a "min-max" range of them) mid-digit-group - underscores don't
        break, so the whole number stays on one line regardless of the chat window's width.

        :param value: Value to format - must be a whole number.
        :return: Underscore-grouped digit string.
        """
        number: int = int(Decimal(str(value)))
        sign: str = "-" if number < 0 else ""
        return f"{sign}{abs(number):,}".replace(",", "_")

    async def render(self, tmpl: str, locale: str, data: dict | None = None, max_len: int = 4096) -> str:
        """
        Returns the rendered template, based on the passed data, truncated if necessary.

        :param tmpl: Template name.
        :param locale: Language code.
        :param data: Data to pass to the template.
        :param max_len: Maximum length of the rendered text (default: 4096).
        :return: Rendered template as string, truncated if longer than max_len.
        """
        data_to_render: dict = data or {}
        token: Token[str] = _locale_ctx.set(locale)
        try:
            rendered_data: str = await self._env.get_template(name=tmpl).render_async(**data_to_render)
        finally:
            _locale_ctx.reset(token)  # positional-only in CPython
        if len(rendered_data) > max_len:
            rendered_data = self._smart_trunc(html=rendered_data, max_len=max_len)
        return rendered_data
