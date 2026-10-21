"""
Unit tests for src/core/log_setup.py (InterceptHandler, LoggingManager).

Both classes configure process-wide singletons - loguru's own sink registry and the stdlib
logging module's root logger - so the autouse _restore_logging_state fixture below undoes those
mutations after every test, the same way tests/conftest.py's isolated_environ fixture keeps
os.environ hermetic. Without it, a sink or handler left behind by one test would leak into every
test that runs after it, in this file and beyond.
"""

import io
import logging
import sys
from pathlib import Path
from typing import Iterator

import pytest
from loguru import logger

from core import log_setup
from core.log_setup import InterceptHandler, LoggingManager

__all__: tuple = ()


@pytest.fixture(autouse=True)
def _restore_logging_state(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """
    Restores the stdlib root logger's handlers/level, and clears every loguru sink added during
    the test.

    :param monkeypatch: pytest fixture used to restore the root logger's handlers/level.
    :return: None
    """
    monkeypatch.setattr(target=logging.root, name="handlers", value=logging.root.handlers[:])
    monkeypatch.setattr(target=logging.root, name="level", value=logging.root.level)
    yield
    logger.remove()


@pytest.fixture(name="captured_records")
def captured_records_fixture() -> Iterator[list]:
    """
    Adds a loguru sink that records every emitted record's structured data, regardless of level.

    :return: The list every record loguru receives while this fixture is active gets appended to.
    """
    records: list = []
    sink_id: int = logger.add(sink=lambda message: records.append(message.record), level=0)
    yield records
    logger.remove(sink_id)


class TestInterceptHandlerEmit:
    """Tests for InterceptHandler.emit: level mapping, message forwarding, and exception info."""

    def test_forwards_a_known_level_and_formatted_message(self, captured_records: list) -> None:
        """
        A levelname loguru already knows (e.g. WARNING) is forwarded by name, and the record's
        message is formatted with its args before being logged.

        :param captured_records: Fixture capturing every record loguru receives.
        :return: None
        """
        record: logging.LogRecord = logging.LogRecord(
            name="some.library",
            level=logging.WARNING,
            pathname=__file__,
            lineno=1,
            msg="disk at %d%%",
            args=(90,),
            exc_info=None,
        )
        InterceptHandler().emit(record)
        assert len(captured_records) == 1
        assert captured_records[0]["level"].name == "WARNING"
        assert captured_records[0]["message"] == "disk at 90%"

    def test_falls_back_to_the_numeric_level_for_an_unregistered_levelname(self, captured_records: list) -> None:
        """
        A levelname loguru has no matching level for (logger.level() raises ValueError) is logged
        by its raw numeric levelno instead of raising out of emit().

        :param captured_records: Fixture capturing every record loguru receives.
        :return: None
        """
        record: logging.LogRecord = logging.LogRecord(
            name="some.library",
            level=15,
            pathname=__file__,
            lineno=1,
            msg="custom",
            args=None,
            exc_info=None,
        )
        InterceptHandler().emit(record)
        assert len(captured_records) == 1
        assert captured_records[0]["level"].no == 15

    def test_forwards_exception_info(self, captured_records: list) -> None:
        """
        A record carrying exc_info has the exception itself forwarded to loguru, not just the
        message text.

        :param captured_records: Fixture capturing every record loguru receives.
        :return: None
        """
        try:
            raise ValueError("boom")
        except ValueError:
            record: logging.LogRecord = logging.LogRecord(
                name="some.library",
                level=logging.ERROR,
                pathname=__file__,
                lineno=1,
                msg="failed",
                args=None,
                exc_info=sys.exc_info(),
            )
            InterceptHandler().emit(record)
        assert len(captured_records) == 1
        exception = captured_records[0]["exception"]
        assert exception is not None
        assert str(exception.value) == "boom"

    def test_reports_the_real_callers_location_not_loggings_internals(self, captured_records: list) -> None:
        """
        Depth is computed by skipping every frame inside the logging module itself, so the
        location loguru reports is this test function's own call site, not somewhere inside
        logging/__init__.py's Logger.warning/callHandlers/Handler.handle chain.

        :param captured_records: Fixture capturing every record loguru receives.
        :return: None
        """
        std_logger: logging.Logger = logging.getLogger("test.intercept_handler.depth")
        std_logger.handlers = [InterceptHandler()]
        std_logger.setLevel(logging.WARNING)
        std_logger.propagate = False

        std_logger.warning("boom")

        assert len(captured_records) == 1
        assert captured_records[0]["file"].path == __file__
        assert captured_records[0]["function"] == "test_reports_the_real_callers_location_not_loggings_internals"


class TestLoggingManagerConsoleSink:
    """Tests for the console sink's level threshold and format, keyed on the debug flag."""

    @staticmethod
    def _build(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, debug: bool) -> io.StringIO:
        """
        Constructs a LoggingManager with the console sink redirected to an in-memory stream.

        log_setup.stderr (not sys.stderr) is patched, since LoggingManager's __init__ passes that
        module-level name straight to logger.add() as the console sink.

        :param monkeypatch: pytest fixture used to redirect log_setup's stderr binding.
        :param tmp_path: Temporary directory used as the log directory.
        :param debug: The debug flag to construct LoggingManager with.
        :return: The stream the console sink now writes to.
        """
        stream: io.StringIO = io.StringIO()
        monkeypatch.setattr(target=log_setup, name="stderr", value=stream)
        LoggingManager(debug=debug, log_dir=tmp_path, project_name="test-project")
        return stream

    def test_debug_mode_emits_debug_level_messages(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """
        With debug=True, a DEBUG-level message reaches the console sink.

        :param monkeypatch: pytest fixture used to redirect the console sink's stream.
        :param tmp_path: pytest fixture - temporary directory used as the log directory.
        :return: None
        """
        stream: io.StringIO = self._build(monkeypatch=monkeypatch, tmp_path=tmp_path, debug=True)
        logger.debug("debug detail")
        assert "debug detail" in stream.getvalue()

    def test_non_debug_mode_drops_debug_level_messages(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """
        With debug=False, a DEBUG-level message never reaches the console sink.

        :param monkeypatch: pytest fixture used to redirect the console sink's stream.
        :param tmp_path: pytest fixture - temporary directory used as the log directory.
        :return: None
        """
        stream: io.StringIO = self._build(monkeypatch=monkeypatch, tmp_path=tmp_path, debug=False)
        logger.debug("debug detail")
        assert "debug detail" not in stream.getvalue()

    def test_non_debug_mode_still_emits_info_level_messages(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """
        With debug=False, an INFO-level message still reaches the console sink - the non-debug
        floor is INFO, not WARNING, so scheduled-job heartbeats stay visible without full DEBUG.

        :param monkeypatch: pytest fixture used to redirect the console sink's stream.
        :param tmp_path: pytest fixture - temporary directory used as the log directory.
        :return: None
        """
        stream: io.StringIO = self._build(monkeypatch=monkeypatch, tmp_path=tmp_path, debug=False)
        logger.info("heartbeat")
        assert "heartbeat" in stream.getvalue()

    def test_debug_mode_format_includes_source_location(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """
        With debug=True, the console format includes the emitting function's name.

        :param monkeypatch: pytest fixture used to redirect the console sink's stream.
        :param tmp_path: pytest fixture - temporary directory used as the log directory.
        :return: None
        """
        stream: io.StringIO = self._build(monkeypatch=monkeypatch, tmp_path=tmp_path, debug=True)
        logger.debug("debug detail")
        assert "test_debug_mode_format_includes_source_location" in stream.getvalue()

    def test_non_debug_mode_format_omits_source_location(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """
        With debug=False, the console format omits the emitting function's name.

        :param monkeypatch: pytest fixture used to redirect the console sink's stream.
        :param tmp_path: pytest fixture - temporary directory used as the log directory.
        :return: None
        """
        stream: io.StringIO = self._build(monkeypatch=monkeypatch, tmp_path=tmp_path, debug=False)
        logger.info("heartbeat")
        assert "test_non_debug_mode_format_omits_source_location" not in stream.getvalue()


class TestLoggingManagerFileSink:
    """Tests for the file sink: directory creation, filename derivation, and level threshold."""

    def test_creates_the_log_dir_if_missing(self, tmp_path: Path) -> None:
        """
        log_dir is created, including any missing parents, if it doesn't already exist.

        :param tmp_path: pytest fixture - temporary directory to nest a missing log_dir under.
        :return: None
        """
        log_dir: Path = tmp_path / "nested" / "logs"
        assert not log_dir.exists()
        LoggingManager(debug=True, log_dir=log_dir, project_name="test-project")
        assert log_dir.is_dir()

    def test_log_file_name_replaces_spaces_with_hyphens(self, tmp_path: Path) -> None:
        """
        A project_name containing spaces is hyphenated to build the log file's name.

        :param tmp_path: pytest fixture - temporary directory used as the log directory.
        :return: None
        """
        LoggingManager(debug=True, log_dir=tmp_path, project_name="My Cool Bot")
        assert (tmp_path / "My-Cool-Bot.log").exists()

    def test_non_debug_mode_still_writes_info_level_messages(self, tmp_path: Path) -> None:
        """
        With debug=False, an INFO-level message still reaches the log file.

        :param tmp_path: pytest fixture - temporary directory used as the log directory.
        :return: None
        """
        LoggingManager(debug=False, log_dir=tmp_path, project_name="test-project")
        logger.info("heartbeat")
        logger.complete()
        assert "heartbeat" in (tmp_path / "test-project.log").read_text(encoding="utf-8")

    def test_non_debug_mode_drops_debug_level_messages(self, tmp_path: Path) -> None:
        """
        With debug=False, a DEBUG-level message never reaches the log file.

        :param tmp_path: pytest fixture - temporary directory used as the log directory.
        :return: None
        """
        LoggingManager(debug=False, log_dir=tmp_path, project_name="test-project")
        logger.debug("debug detail")
        logger.complete()
        assert "debug detail" not in (tmp_path / "test-project.log").read_text(encoding="utf-8")

    def test_file_format_always_includes_source_location_regardless_of_debug(self, tmp_path: Path) -> None:
        """
        Unlike the console sink, the file sink's format always includes name/function/line, even
        with debug=False - unlike the console, the file isn't shown to an interactive user, so
        full detail costs nothing.

        :param tmp_path: pytest fixture - temporary directory used as the log directory.
        :return: None
        """
        LoggingManager(debug=False, log_dir=tmp_path, project_name="test-project")
        logger.info("heartbeat")
        logger.complete()
        content: str = (tmp_path / "test-project.log").read_text(encoding="utf-8")
        assert "test_file_format_always_includes_source_location_regardless_of_debug" in content

    def test_removes_previously_configured_sinks(self, tmp_path: Path) -> None:
        """
        Constructing a LoggingManager clears any sinks configured before it, so re-initializing
        logging doesn't duplicate output onto whatever was already listening.

        :param tmp_path: pytest fixture - temporary directory used as the log directory.
        :return: None
        """
        stale_records: list = []
        logger.add(sink=stale_records.append, level=0)
        LoggingManager(debug=True, log_dir=tmp_path, project_name="test-project")
        logger.info("after re-init")
        assert not stale_records


class TestLoggingManagerRootLoggerWiring:
    """Tests for LoggingManager's stdlib root-logger wiring: the InterceptHandler bridge."""

    def test_installs_intercept_handler_as_the_only_root_handler(self, tmp_path: Path) -> None:
        """
        The stdlib root logger's handlers are replaced with a single InterceptHandler instance,
        discarding whatever handlers (e.g. a library's own logging.basicConfig) were there before.

        :param tmp_path: pytest fixture - temporary directory used as the log directory.
        :return: None
        """
        logging.root.handlers = [logging.NullHandler()]
        LoggingManager(debug=True, log_dir=tmp_path, project_name="test-project")
        assert len(logging.root.handlers) == 1
        assert isinstance(logging.root.handlers[0], InterceptHandler)

    def test_sets_the_root_logger_level_to_debug_when_debug_is_true(self, tmp_path: Path) -> None:
        """
        debug=True sets the stdlib root logger's level to DEBUG, so every stdlib record reaches
        InterceptHandler regardless of the level a third-party library logs it at.

        :param tmp_path: pytest fixture - temporary directory used as the log directory.
        :return: None
        """
        LoggingManager(debug=True, log_dir=tmp_path, project_name="test-project")
        assert logging.root.level == logging.DEBUG

    def test_sets_the_root_logger_level_to_info_when_debug_is_false(self, tmp_path: Path) -> None:
        """
        debug=False sets the stdlib root logger's level to INFO, matching the non-debug loguru
        floor set on the console/file sinks.

        :param tmp_path: pytest fixture - temporary directory used as the log directory.
        :return: None
        """
        LoggingManager(debug=False, log_dir=tmp_path, project_name="test-project")
        assert logging.root.level == logging.INFO

    def test_silences_pillow_debug_noise_even_in_debug_mode(self, tmp_path: Path) -> None:
        """
        Pillow's own logger (a DEBUG line per PNG chunk on every forecast image) is floored at INFO
        regardless of debug=True, even though the root logger itself is set to DEBUG.

        :param tmp_path: pytest fixture - temporary directory used as the log directory.
        :return: None
        """
        LoggingManager(debug=True, log_dir=tmp_path, project_name="test-project")
        assert logging.getLogger("PIL").level == logging.INFO

    def test_stdlib_logging_is_forwarded_to_loguru(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """
        A message logged through the stdlib logging module - the way a third-party library
        (aiogram, apscheduler, asyncpg) would - is forwarded through InterceptHandler and
        reaches loguru's own console sink end-to-end.

        :param monkeypatch: pytest fixture used to redirect the console sink's stream.
        :param tmp_path: pytest fixture - temporary directory used as the log directory.
        :return: None
        """
        stream: io.StringIO = io.StringIO()
        monkeypatch.setattr(target=log_setup, name="stderr", value=stream)
        LoggingManager(debug=True, log_dir=tmp_path, project_name="test-project")
        logging.getLogger("some.library").warning("third-party warning")
        assert "third-party warning" in stream.getvalue()
