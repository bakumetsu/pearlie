import logging
from pathlib import Path

import pytest

from app.config import ConfigError, Settings, load_settings
from app.main import create_app


def test_mode_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PEARLIE_MODE", raising=False)
    with pytest.raises(ConfigError) as exc:
        load_settings(_env_file=None)
    assert str(exc.value) == "PEARLIE_MODE must be set to 'fixture' or 'real' (got: unset)"


def test_mode_bogus(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PEARLIE_MODE", "bogus")
    with pytest.raises(ConfigError) as exc:
        load_settings(_env_file=None)
    assert "got: bogus" in str(exc.value)


def test_mode_fixture_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PEARLIE_MODE", "fixture")
    s = load_settings(_env_file=None)
    assert s.mode == "fixture"


def test_secrets_not_leaked(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    settings = Settings(
        mode="fixture",
        db_path=tmp_path / "p.db",
        static_dir=tmp_path / "nostatic",
        stash_api_key="SECRET-STASH-123",
        nhentai_cookies="COOKIE-456",
        stash_url="http://stash.local",
        _env_file=None,  # pyright: ignore[reportCallIssue]
    )
    summary_str = str(settings.safe_summary())
    assert "SECRET-STASH-123" not in summary_str
    assert "COOKIE-456" not in summary_str
    assert "http://stash.local" not in summary_str

    r = repr(settings)
    assert "SECRET-STASH-123" not in r
    assert "COOKIE-456" not in r

    caplog.set_level(logging.INFO, logger="pearlie")
    create_app(settings)
    assert "SECRET-STASH-123" not in caplog.text
    assert "COOKIE-456" not in caplog.text
    assert "http://stash.local" not in caplog.text
    assert "set" in caplog.text


def test_invalid_port() -> None:
    with pytest.raises(ConfigError) as exc:
        load_settings(mode="fixture", port="abc", _env_file=None)
    msg = str(exc.value)
    assert "port" in msg
    assert "abc" not in msg


def test_non_loopback_host_refused() -> None:
    with pytest.raises(ConfigError) as exc:
        load_settings(mode="fixture", host="0.0.0.0", _env_file=None)
    assert "loopback only" in str(exc.value)


def test_loopback_hosts_allowed() -> None:
    for host in ("127.0.0.1", "localhost", "::1"):
        assert load_settings(mode="fixture", host=host, _env_file=None).host == host
