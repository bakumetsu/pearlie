import logging
import os
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
    assert "PEARLIE_TRUSTED_NETWORK" in str(exc.value)


def test_non_loopback_host_allowed_when_trusted() -> None:
    s = load_settings(mode="fixture", host="10.0.0.5", trusted_network=True, _env_file=None)
    assert s.host == "10.0.0.5"


def test_trusted_network_does_not_change_loopback_default() -> None:
    assert load_settings(mode="fixture", _env_file=None).trusted_network is False


def test_loopback_hosts_allowed() -> None:
    for host in ("127.0.0.1", "localhost", "::1"):
        assert load_settings(mode="fixture", host=host, _env_file=None).host == host


def test_env_example_covers_every_setting_and_loads(monkeypatch: pytest.MonkeyPatch) -> None:
    example = Path(__file__).resolve().parents[2] / ".env.example"
    for name in list(os.environ):
        if name.startswith("PEARLIE_"):
            monkeypatch.delenv(name)
    keys = {
        line.split("=", 1)[0]
        for line in example.read_text(encoding="utf-8").splitlines()
        if line.startswith("PEARLIE_")
    }
    expected = {f"PEARLIE_{name.upper()}" for name in Settings.model_fields} - {"PEARLIE_REAL"}
    assert keys == expected
    s = load_settings(_env_file=example)
    assert s.mode == "fixture"
    assert s.secret_key.get_secret_value() == ""
