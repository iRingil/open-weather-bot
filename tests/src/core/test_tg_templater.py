"""
Unit tests for src/core/tg_templater.py (TgTemplater).

Real Jinja2 templates and real compiled Babel .mo catalogs are built on disk under pytest's
tmp_path fixture for every render() test - nothing about Jinja2's i18n extension or Babel's
gettext lookup is mocked, since TgTemplater's whole value is in wiring those two together
correctly. Catalogs are compiled in-process via babel.messages (Catalog + write_mo), so the suite
never shells out to msgfmt/pybabel and stays fast and self-contained.
"""

import asyncio
from collections.abc import Callable
from decimal import Decimal
from gettext import NullTranslations
from pathlib import Path

import pytest
from babel.messages.catalog import Catalog
from babel.messages.mofile import write_mo
from babel.support import Translations
from jinja2 import TemplateNotFound

from core.tg_templater import TgTemplater

__all__: tuple = ()


def _write_template(templates_dir: Path, name: str, content: str) -> None:
    """
    Writes a throwaway Jinja2 template file, creating templates_dir if needed.

    :param templates_dir: Directory to write the template under.
    :param name: Template filename, e.g. "greet.jinja2".
    :param content: Full template source.
    :return: None
    """
    templates_dir.mkdir(parents=True, exist_ok=True)
    (templates_dir / name).write_text(content, encoding="utf-8")


def _compile_translations(locale_dir: Path, locale: str, translations: dict[str, str]) -> None:
    """
    Compiles a throwaway Babel .mo catalog for one locale, in the dirname/locale/LC_MESSAGES/
    messages.mo layout babel.support.Translations.load expects.

    :param locale_dir: Locale root directory (mirrors src/locales/).
    :param locale: Language code, e.g. "en" or "ru".
    :param translations: Maps each msgid to its translated string.
    :return: None
    """
    catalog: Catalog = Catalog(locale=locale)
    for msgid, msgstr in translations.items():
        catalog.add(id=msgid, string=msgstr)
    mo_dir: Path = locale_dir / locale / "LC_MESSAGES"
    mo_dir.mkdir(parents=True, exist_ok=True)
    with (mo_dir / "messages.mo").open(mode="wb") as fh:
        write_mo(fileobj=fh, catalog=catalog)


class TestGroupDigits:
    """Tests for the group_digits Jinja2 filter's thousands-separator rules."""

    @pytest.mark.parametrize(
        "value,expected",
        [
            (15, "15"),
            (999, "999"),
            (1000, "1_000"),
            (100000, "100_000"),
            (1000000000, "1_000_000_000"),
            (0, "0"),
            (-12345, "-12_345"),
            (Decimal("1.000E+7"), "10_000_000"),
        ],
    )
    def test_groups_digits_in_threes_with_underscores(self, value: int | Decimal, expected: str) -> None:
        """
        A whole number's digits are grouped in 3s from the right, separated by underscores (not
        spaces, which Telegram would happily wrap a long number across) - including one already
        in scientific notation (e.g. asyncpg's NUMERIC decoding can hand back Decimal('1.000E+7')
        for a plain 10000000).

        :param value: Input value (int or Decimal).
        :param expected: Expected underscore-grouped string.
        :return: None
        """
        assert TgTemplater._group_digits(value=value) == expected  # pylint: disable=protected-access


class TestSmartTrunc:
    """
    Tests for _smart_trunc's HTML-aware truncation, exercised directly since it's the most
    complex pure logic in this module.
    """

    def test_returns_short_html_unchanged(self) -> None:
        """
        HTML at or under max_len is returned as-is, with no "..." appended.

        :return: None
        """
        result: str = TgTemplater._smart_trunc(html="<b>hi</b>", max_len=4096)  # pylint: disable=protected-access
        assert result == "<b>hi</b>"

    def test_truncates_plain_text_with_no_tags(self) -> None:
        """
        Text with no "<" at all is truncated to max_len - len("...") characters plus the suffix.

        :return: None
        """
        result: str = TgTemplater._smart_trunc(  # pylint: disable=protected-access
            html="plain text no tags at all", max_len=10
        )
        assert result == "plain t..."

    def test_keeps_balanced_tags_that_fit_exactly_at_the_cut(self) -> None:
        """
        Regression test: when the cut boundary lands exactly after a complete, balanced tag pair
        (no dangling open tag), the trimmed content must be kept, not discarded - a prior bug in
        the final `return suffix if not tag_stack else ...` line dropped the entire trimmed HTML
        and returned a bare "..." whenever the cut happened to land on a fully-balanced boundary.

        :return: None
        """
        html: str = "<b>Hello</b><i>World</i>"
        result: str = TgTemplater._smart_trunc(html=html, max_len=15)  # pylint: disable=protected-access
        assert result == "<b>Hello</b>..."

    def test_backs_up_before_a_tag_left_open_by_the_cut(self) -> None:
        """
        When the cut lands inside an unclosed tag's content, the result backs up to before that
        tag started, rather than emitting a dangling open tag.

        :return: None
        """
        html: str = "<b>Hello</b><i>World</i>"
        result: str = TgTemplater._smart_trunc(html=html, max_len=20)  # pylint: disable=protected-access
        assert result == "<b>Hello</b>..."

    def test_backs_up_to_nothing_when_the_very_first_tag_is_left_open(self) -> None:
        """
        An opening tag that's never closed anywhere in the trimmed text backs all the way up to
        before it started, leaving just the suffix.

        :return: None
        """
        result: str = TgTemplater._smart_trunc(html="<b>unterminated", max_len=10)  # pylint: disable=protected-access
        assert result == "..."

    def test_ignores_self_closing_tags(self) -> None:
        """
        A self-closing tag (ending in "/>") never gets pushed onto the open-tag stack, so it
        doesn't force a back-up on its own.

        :return: None
        """
        html: str = "<br/>Hello World, this is a long line of text"
        result: str = TgTemplater._smart_trunc(html=html, max_len=15)  # pylint: disable=protected-access
        assert result == "<br/>Hello W..."

    def test_stops_the_tag_name_at_the_first_attribute_space(self) -> None:
        """
        A tag with attributes has its name parsed only up to the first space.

        E.g. "<a href=...>" - not the whole "a href=..." text. Otherwise, its later matching
        "</a>" close tag would never compare equal, and back-up would trigger even though the
        pair is fully balanced within the cut.

        :return: None
        """
        html: str = '<a href="x">Link</a> and some trailing padding text here'
        result: str = TgTemplater._smart_trunc(html=html, max_len=25)  # pylint: disable=protected-access
        assert result == '<a href="x">Link</a> a...'

    def test_backs_up_to_the_tag_start_when_the_cut_lands_inside_an_unclosed_tag(self) -> None:
        """
        The cut can also land before a tag's own closing ">", not just before its close tag.

        Unlike test_backs_up_before_a_tag_left_open_by_the_cut, the cut here lands inside the
        opening tag itself. With no earlier open tag on the stack, the result backs up to that
        tag's own start.

        :return: None
        """
        html: str = 'plain text <a href="https://example.com/very/long/path/keeps/going">link</a>'
        result: str = TgTemplater._smart_trunc(html=html, max_len=23)  # pylint: disable=protected-access
        assert result == "plain text ..."

    def test_backs_up_to_the_earlier_open_tag_when_the_cut_lands_inside_a_nested_unclosed_tag(self) -> None:
        """
        Same as the previous test, but with an earlier tag still open on the stack.

        E.g. "<b>", already open when the cut hits the nested unclosed tag. The result backs up
        to that earlier tag's start instead, discarding the whole nested fragment.

        :return: None
        """
        html: str = '<b>Hello <a href="https://example.com/very/long/path/keeps/going">link</a></b>'
        result: str = TgTemplater._smart_trunc(html=html, max_len=23)  # pylint: disable=protected-access
        assert result == "..."


class TestGetLocales:
    """Tests for get_locales, listing the available localization languages."""

    def test_lists_only_subdirectories(self, tmp_path: Path) -> None:
        """
        Only directories under locale_dir are returned, not stray files.

        :param tmp_path: pytest fixture - temporary directory used as locale_dir.
        :return: None
        """
        locale_dir: Path = tmp_path / "locales"
        locale_dir.mkdir()
        (locale_dir / "ru").mkdir()
        (locale_dir / "en").mkdir()
        (locale_dir / "README.txt").write_text("not a locale", encoding="utf-8")
        templates_dir: Path = tmp_path / "templates"
        _write_template(templates_dir=templates_dir, name="noop.jinja2", content="noop")
        tmpl: TgTemplater = TgTemplater(templates_dir=templates_dir, locale_dir=locale_dir)
        assert set(tmpl.get_locales()) == {"ru", "en"}


class TestLoadTranslationsCaching:
    """Tests for _load_translations' per-locale caching, exercised through render()."""

    async def test_loads_a_locale_only_once_across_renders(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """
        Rendering the same locale twice only loads its Translations catalog from disk once.

        :param tmp_path: pytest fixture - temporary directory for templates/locale dirs.
        :param monkeypatch: pytest fixture used to spy on Translations.load.
        :return: None
        """
        templates_dir: Path = tmp_path / "templates"
        locale_dir: Path = tmp_path / "locales"
        _write_template(templates_dir=templates_dir, name="greet.jinja2", content="{% trans %}Hello{% endtrans %}")
        _compile_translations(locale_dir=locale_dir, locale="ru", translations={"Hello": "Privet"})

        original_load: Callable[..., NullTranslations] = Translations.load
        load_calls: list[str] = []

        def _counting_load(dirname: Path, locales: str, domain: str | None = None) -> NullTranslations:
            """
            Records every call before delegating to the real Translations.load.

            :param dirname: Locale root directory, forwarded unchanged.
            :param locales: Language code, forwarded unchanged and recorded.
            :param domain: Gettext domain, forwarded unchanged.
            :return: Whatever the real Translations.load returns.
            """
            load_calls.append(locales)
            return original_load(dirname=dirname, locales=locales, domain=domain)

        monkeypatch.setattr(target=Translations, name="load", value=_counting_load)

        tmpl: TgTemplater = TgTemplater(templates_dir=templates_dir, locale_dir=locale_dir)
        first: str = await tmpl.render(tmpl="greet.jinja2", locale="ru")
        second: str = await tmpl.render(tmpl="greet.jinja2", locale="ru")

        assert first == second == "Privet"
        assert load_calls == ["ru"]


class TestRender:
    """Integration tests for render(): data substitution, i18n, filters, and truncation."""

    async def test_substitutes_plain_data(self, tmp_path: Path) -> None:
        """
        Template variables are substituted from the data dict.

        :param tmp_path: pytest fixture - temporary directory for templates/locale dirs.
        :return: None
        """
        templates_dir: Path = tmp_path / "templates"
        _write_template(templates_dir=templates_dir, name="greet.jinja2", content="Hello, {{ name }}!")
        tmpl: TgTemplater = TgTemplater(templates_dir=templates_dir, locale_dir=tmp_path / "locales")
        result: str = await tmpl.render(tmpl="greet.jinja2", locale="en", data={"name": "Ringil"})
        assert result == "Hello, Ringil!"

    async def test_renders_with_no_data(self, tmp_path: Path) -> None:
        """
        A template needing no variables renders fine with data omitted (defaults to {}).

        :param tmp_path: pytest fixture - temporary directory for templates/locale dirs.
        :return: None
        """
        templates_dir: Path = tmp_path / "templates"
        _write_template(templates_dir=templates_dir, name="static.jinja2", content="Nothing to see here.")
        tmpl: TgTemplater = TgTemplater(templates_dir=templates_dir, locale_dir=tmp_path / "locales")
        assert await tmpl.render(tmpl="static.jinja2", locale="en") == "Nothing to see here."

    async def test_translates_via_trans_block_for_the_given_locale(self, tmp_path: Path) -> None:
        """
        A {% trans %} block is translated using the requested locale's catalog.

        :param tmp_path: pytest fixture - temporary directory for templates/locale dirs.
        :return: None
        """
        templates_dir: Path = tmp_path / "templates"
        locale_dir: Path = tmp_path / "locales"
        _write_template(templates_dir=templates_dir, name="greet.jinja2", content="{% trans %}Hello{% endtrans %}")
        _compile_translations(locale_dir=locale_dir, locale="ru", translations={"Hello": "Privet"})
        tmpl: TgTemplater = TgTemplater(templates_dir=templates_dir, locale_dir=locale_dir)
        assert await tmpl.render(tmpl="greet.jinja2", locale="ru") == "Privet"

    async def test_falls_back_to_the_source_string_for_an_untranslated_locale(self, tmp_path: Path) -> None:
        """
        A locale with no compiled catalog at all renders the original {% trans %} text unchanged.

        :param tmp_path: pytest fixture - temporary directory for templates/locale dirs.
        :return: None
        """
        templates_dir: Path = tmp_path / "templates"
        _write_template(templates_dir=templates_dir, name="greet.jinja2", content="{% trans %}Hello{% endtrans %}")
        tmpl: TgTemplater = TgTemplater(templates_dir=templates_dir, locale_dir=tmp_path / "locales")
        assert await tmpl.render(tmpl="greet.jinja2", locale="en") == "Hello"

    async def test_pluralizes_via_ngettext(self, tmp_path: Path) -> None:
        """
        A {% trans %}...{% pluralize %}...{% endtrans %} block picks the singular/plural form
        based on the bound count, routed through the installed ngettext callable.

        :param tmp_path: pytest fixture - temporary directory for templates/locale dirs.
        :return: None
        """
        templates_dir: Path = tmp_path / "templates"
        locale_dir: Path = tmp_path / "locales"
        _write_template(
            templates_dir=templates_dir,
            name="plural.jinja2",
            content="{% trans count=count %}{{ count }} apple{% pluralize %}{{ count }} apples{% endtrans %}",
        )
        catalog: Catalog = Catalog(locale="en")
        catalog.add(id=("%(count)s apple", "%(count)s apples"), string=("one %(count)s", "many %(count)s"))
        mo_dir: Path = locale_dir / "en" / "LC_MESSAGES"
        mo_dir.mkdir(parents=True)
        with (mo_dir / "messages.mo").open(mode="wb") as fh:
            write_mo(fileobj=fh, catalog=catalog)
        tmpl: TgTemplater = TgTemplater(templates_dir=templates_dir, locale_dir=locale_dir)

        assert await tmpl.render(tmpl="plural.jinja2", locale="en", data={"count": 1}) == "one 1"
        assert await tmpl.render(tmpl="plural.jinja2", locale="en", data={"count": 3}) == "many 3"

    async def test_group_digits_filter_is_wired_into_the_environment(self, tmp_path: Path) -> None:
        """
        The group_digits filter is registered on the Jinja2 environment and usable from a
        template with the |group_digits syntax, not just as a direct Python call.

        :param tmp_path: pytest fixture - temporary directory for templates/locale dirs.
        :return: None
        """
        templates_dir: Path = tmp_path / "templates"
        _write_template(templates_dir=templates_dir, name="volume.jinja2", content="{{ volume|group_digits }}")
        tmpl: TgTemplater = TgTemplater(templates_dir=templates_dir, locale_dir=tmp_path / "locales")
        result: str = await tmpl.render(tmpl="volume.jinja2", locale="en", data={"volume": 1000000})
        assert result == "1_000_000"

    async def test_leaves_output_under_max_len_untouched(self, tmp_path: Path) -> None:
        """
        Rendered output at or under max_len is returned without going through _smart_trunc.

        :param tmp_path: pytest fixture - temporary directory for templates/locale dirs.
        :return: None
        """
        templates_dir: Path = tmp_path / "templates"
        _write_template(templates_dir=templates_dir, name="short.jinja2", content="short")
        tmpl: TgTemplater = TgTemplater(templates_dir=templates_dir, locale_dir=tmp_path / "locales")
        assert await tmpl.render(tmpl="short.jinja2", locale="en", max_len=10) == "short"

    async def test_truncates_output_over_max_len(self, tmp_path: Path) -> None:
        """
        Rendered output over max_len is truncated (via _smart_trunc) before being returned.

        :param tmp_path: pytest fixture - temporary directory for templates/locale dirs.
        :return: None
        """
        templates_dir: Path = tmp_path / "templates"
        _write_template(templates_dir=templates_dir, name="long.jinja2", content="a very long piece of text")
        tmpl: TgTemplater = TgTemplater(templates_dir=templates_dir, locale_dir=tmp_path / "locales")
        result: str = await tmpl.render(tmpl="long.jinja2", locale="en", max_len=10)
        assert result == "a very ..."

    async def test_raises_template_not_found_for_a_missing_template(self, tmp_path: Path) -> None:
        """
        Rendering a template name that doesn't exist under templates_dir raises TemplateNotFound.

        :param tmp_path: pytest fixture - temporary directory for templates/locale dirs.
        :return: None
        """
        templates_dir: Path = tmp_path / "templates"
        templates_dir.mkdir()
        tmpl: TgTemplater = TgTemplater(templates_dir=templates_dir, locale_dir=tmp_path / "locales")
        with pytest.raises(expected_exception=TemplateNotFound):
            await tmpl.render(tmpl="missing.jinja2", locale="en")

    async def test_concurrent_renders_do_not_leak_locale_across_each_other(self, tmp_path: Path) -> None:
        """
        _locale_ctx is a module-level ContextVar shared by every TgTemplater instance, so this
        confirms concurrent render() calls each keep their own locale instead of one call's
        locale leaking into another's.

        :param tmp_path: pytest fixture - temporary directory for templates/locale dirs.
        :return: None
        """
        templates_dir: Path = tmp_path / "templates"
        locale_dir: Path = tmp_path / "locales"
        _write_template(templates_dir=templates_dir, name="greet.jinja2", content="{% trans %}Hello{% endtrans %}")
        _compile_translations(locale_dir=locale_dir, locale="ru", translations={"Hello": "Privet"})
        tmpl: TgTemplater = TgTemplater(templates_dir=templates_dir, locale_dir=locale_dir)

        results: list[str] = await asyncio.gather(
            *(tmpl.render(tmpl="greet.jinja2", locale="ru" if i % 2 == 0 else "en") for i in range(20))
        )

        assert all(result == "Privet" for result in results[0::2])
        assert all(result == "Hello" for result in results[1::2])
