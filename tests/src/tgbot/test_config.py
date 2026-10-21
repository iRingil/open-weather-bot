"""Unit tests for src/tgbot/config.py (Config).

Config wraps a CoreConfig (see src/core/config.py) and reads its own extra keys off the same
shared .env. Every test here builds a real, throwaway CoreConfig backed by its own temporary
directory under pytest's tmp_path, matching how the running application composes the two.

Nothing here touches the real project .env (gitignored, won't exist on a fresh CI checkout) or
the real Redis/Postgres - CoreConfig only builds a lazy redis.asyncio.Redis client object, it
never connects. Combined with tests/conftest.py's isolated_environ fixture, each test is hermetic
regardless of run order.
"""

from pathlib import Path

import pytest
from environs import EnvError
from redis.asyncio import Redis

from tgbot.config import Config
from tgbot.misc.data_types import Paths, WebhookCredentials
from core.config import CoreConfig

__all__: tuple = ()

_CORE_REQUIRED_VARS: str = (
    "ADMIN_IDS=1\nWEATHER_API_TOKEN=owm\nPOSTGRES_DB_NAME=db\nPOSTGRES_DB_USER=user\nPOSTGRES_DB_PASS=pass\n"
    "REDIS_DB_INDEX=0\nREDIS_DB_USER=user\nREDIS_DB_PASS=pass\nREDIS_HOST=host\nREDIS_PORT=6379\n"
)
_BOT_TOKEN_VAR: str = "BOT_TOKEN=test-token\n"


def _write_env(base_dir: Path, content: str) -> None:
    """
    Writes a throwaway .env file for a test.

    :param base_dir: Directory to write the .env file into.
    :param content: Full contents of the .env file.
    :return: None
    """
    (base_dir / ".env").write_text(content, encoding="utf-8")


def _make_config(tmp_path: Path, extra_env: str = "") -> tuple[Config, CoreConfig]:
    """
    Builds a real Config on top of a real CoreConfig, using throwaway directories under tmp_path.

    CoreConfig's own base_dir gets the minimum vars it requires (ADMIN_IDS, WEATHER_API_TOKEN,
    POSTGRES_*, REDIS_*) plus extra_env; Config's own base_dir is a separate, empty directory, so paths it composes are
    never accidentally confused with CoreConfig's.

    :param tmp_path: pytest fixture - temporary directory to build the throwaway layout under.
    :param extra_env: Additional .env lines (BOT_TOKEN, REDIS_* overrides, USE_WEBHOOK/WEBHOOK_*)
        appended after the required CoreConfig vars.
    :return: A tuple of (the Config under test, the CoreConfig it was built from).
    """
    core_base: Path = tmp_path / "core"
    core_base.mkdir(exist_ok=True)
    _write_env(base_dir=core_base, content=_CORE_REQUIRED_VARS + extra_env)
    core: CoreConfig = CoreConfig(base_dir=core_base)
    tgbot_base: Path = tmp_path / "tgbot"
    tgbot_base.mkdir(exist_ok=True)
    return Config(core=core, base_dir=tgbot_base), core


class TestAdmins:
    """Tests for Config.admins."""

    def test_forwards_admins_from_core(self, tmp_path: Path) -> None:
        """
        admins returns exactly what the underlying CoreConfig.admins returns.

        :param tmp_path: pytest fixture - temporary directory to build the throwaway layout under.
        :return: None
        """
        config, core = _make_config(tmp_path=tmp_path, extra_env=_BOT_TOKEN_VAR)
        assert config.admins == core.admins == [1]


class TestPaths:
    """Tests for Config.paths / _get_paths."""

    def test_composes_paths(self, tmp_path: Path) -> None:
        """
        bot_logo/templates are composed under Config's own base_dir (templates as a sibling of
        it, matching the real tgbot/../templates layout).

        :param tmp_path: pytest fixture - temporary directory to build the throwaway layout under.
        :return: None
        """
        config, _ = _make_config(tmp_path=tmp_path, extra_env=_BOT_TOKEN_VAR)
        tgbot_base: Path = tmp_path / "tgbot"
        assert config.paths == Paths(
            bot_logo=tgbot_base / "assets/img/bot_logo.jpg",
            templates=tmp_path / "templates",
        )


class TestRedis:
    """
    Tests for Config.redis.

    Config.redis just forwards CoreConfig.redis, the same way admins does (see TestAdmins above).
    """

    def test_forwards_redis_from_core(self, tmp_path: Path) -> None:
        """
        redis returns exactly what the underlying CoreConfig.redis returns.

        :param tmp_path: pytest fixture - temporary directory to build the throwaway layout under.
        :return: None
        """
        extra_env: str = (
            _BOT_TOKEN_VAR
            + "REDIS_DB_INDEX=2\n"
            + "REDIS_DB_USER=redis_user\n"
            + "REDIS_DB_PASS=redis_pass\n"
            + "REDIS_HOST=redis.internal\n"
            + "REDIS_PORT=6380\n"
        )
        config, core = _make_config(tmp_path=tmp_path, extra_env=extra_env)
        assert config.redis is core.redis
        assert isinstance(config.redis, Redis)


class TestToken:
    """Tests for Config.token / _get_token."""

    def test_reads_token(self, tmp_path: Path) -> None:
        """
        BOT_TOKEN in .env is returned as-is.

        :param tmp_path: pytest fixture - temporary directory to build the throwaway layout under.
        :return: None
        """
        config, _ = _make_config(tmp_path=tmp_path, extra_env="BOT_TOKEN=abc123\n")
        assert config.token == "abc123"

    def test_missing_raises_enverror(self, tmp_path: Path) -> None:
        """
        Missing BOT_TOKEN raises EnvError with the wrapped, more specific message.

        :param tmp_path: pytest fixture - temporary directory to build the throwaway layout under.
        :return: None
        """
        with pytest.raises(expected_exception=EnvError, match="BOT_TOKEN not found"):
            _make_config(tmp_path=tmp_path, extra_env="")


class TestWebhook:
    """Tests for Config.webhook / _get_webhook."""

    def test_defaults_to_none_when_use_webhook_unset(self, tmp_path: Path) -> None:
        """
        USE_WEBHOOK absent from .env keeps the bot on the default long-polling mode.

        :param tmp_path: pytest fixture - temporary directory to build the throwaway layout under.
        :return: None
        """
        config, _ = _make_config(tmp_path=tmp_path, extra_env=_BOT_TOKEN_VAR)
        assert config.webhook is None

    def test_full_credentials(self, tmp_path: Path) -> None:
        """
        USE_WEBHOOK=true with all required fields set builds a matching WebhookCredentials.

        :param tmp_path: pytest fixture - temporary directory to build the throwaway layout under.
        :return: None
        """
        extra_env: str = (
            _BOT_TOKEN_VAR
            + "USE_WEBHOOK=true\n"
            + "WEBHOOK_HOST=https://example.com\n"
            + "WEBHOOK_PATH=hook\n"
            + "WEBHOOK_TOKEN=secret-token\n"
            + "WEBAPP_HOST=0.0.0.0\n"
            + "WEBAPP_PORT=8080\n"
        )
        config, _ = _make_config(tmp_path=tmp_path, extra_env=extra_env)
        assert config.webhook == WebhookCredentials(
            wh_host="https://example.com",
            wh_path="hook",
            wh_token="secret-token",
            app_host="0.0.0.0",
            app_port=8080,
        )

    @pytest.mark.parametrize(
        "extra_env",
        [
            pytest.param(
                "USE_WEBHOOK=true\nWEBHOOK_PATH=p\nWEBHOOK_TOKEN=t\nWEBAPP_HOST=h\nWEBAPP_PORT=1\n",
                id="missing_webhook_host",
            ),
            pytest.param(
                "USE_WEBHOOK=true\nWEBHOOK_HOST=hst\nWEBHOOK_TOKEN=t\nWEBAPP_HOST=h\nWEBAPP_PORT=1\n",
                id="missing_webhook_path",
            ),
            pytest.param(
                "USE_WEBHOOK=true\nWEBHOOK_HOST=hst\nWEBHOOK_PATH=p\nWEBAPP_HOST=h\nWEBAPP_PORT=1\n",
                id="missing_webhook_token",
            ),
            pytest.param(
                "USE_WEBHOOK=true\nWEBHOOK_HOST=hst\nWEBHOOK_PATH=p\nWEBHOOK_TOKEN=t\nWEBAPP_PORT=1\n",
                id="missing_webapp_host",
            ),
            pytest.param(
                "USE_WEBHOOK=true\nWEBHOOK_HOST=hst\nWEBHOOK_PATH=p\nWEBHOOK_TOKEN=t\nWEBAPP_HOST=h\n",
                id="missing_webapp_port",
            ),
        ],
    )
    def test_missing_required_field_raises_enverror(self, tmp_path: Path, extra_env: str) -> None:
        """
        Each required webhook field, when missing on its own, raises EnvError.

        :param tmp_path: pytest fixture - temporary directory to build the throwaway layout under.
        :param extra_env: .env lines enabling the webhook but missing exactly one required field.
        :return: None
        """
        with pytest.raises(expected_exception=EnvError, match="Webhook credentials not found"):
            _make_config(tmp_path=tmp_path, extra_env=_BOT_TOKEN_VAR + extra_env)
