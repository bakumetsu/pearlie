from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from app.update.runner import (
    is_running,
    read_conf,
    read_status,
    start_update,
    supported,
    write_conf,
)


def test_supported(tmp_path: Path) -> None:
    assert supported(tmp_path) is False
    (tmp_path / "current").mkdir()
    assert supported(tmp_path) is True


def _write_status(root: Path, text: str) -> None:
    (root / "update-status.json").write_text(text, encoding="utf-8")


def test_read_status_missing(tmp_path: Path) -> None:
    assert read_status(tmp_path) == {"state": "idle", "step": None, "error": None}


def test_read_status_valid_running(tmp_path: Path) -> None:
    _write_status(tmp_path, json.dumps({"state": "running", "step": "download"}))
    assert read_status(tmp_path) == {
        "state": "running",
        "step": "download",
        "error": None,
    }


def test_read_status_current_maps_to_idle(tmp_path: Path) -> None:
    _write_status(tmp_path, json.dumps({"state": "current"}))
    assert read_status(tmp_path) == {"state": "idle", "step": None, "error": None}


def test_read_status_invalid_returns_idle(tmp_path: Path) -> None:
    idle = {"state": "idle", "step": None, "error": None}
    for content in (
        "not json",
        json.dumps([1, 2]),
        json.dumps({"state": "bogus", "step": "x"}),
    ):
        _write_status(tmp_path, content)
        assert read_status(tmp_path) == idle


def test_read_status_non_string_step_is_none(tmp_path: Path) -> None:
    _write_status(
        tmp_path,
        json.dumps({"state": "running", "step": 42, "error": "bad"}),
    )
    assert read_status(tmp_path) == {"state": "running", "step": None, "error": "bad"}


def test_read_conf_missing(tmp_path: Path) -> None:
    assert read_conf(tmp_path) == {}


def test_read_conf_parses(tmp_path: Path) -> None:
    (tmp_path / "update.conf").write_text(
        "# comment\n\nhost=localhost\nport=8080\nnoequals\nchannel=main\n",
        encoding="utf-8",
    )
    assert read_conf(tmp_path) == {
        "host": "localhost",
        "port": "8080",
        "channel": "main",
    }


def test_write_conf_replaces_existing_and_appends_missing(tmp_path: Path) -> None:
    (tmp_path / "update.conf").write_text(
        "# keep\nhost=localhost\nport=8080\nchannel=main\n",
        encoding="utf-8",
    )
    write_conf(tmp_path, channel="dev", check="off")
    lines = (tmp_path / "update.conf").read_text(encoding="utf-8").splitlines()
    assert lines == [
        "# keep",
        "host=localhost",
        "port=8080",
        "channel=dev",
        "check=off",
    ]
    assert not (tmp_path / "update.conf.tmp").exists()


def test_write_conf_appends_missing_channel(tmp_path: Path) -> None:
    (tmp_path / "update.conf").write_text("# keep\nhost=localhost\n", encoding="utf-8")
    write_conf(tmp_path, channel="main", check="on")
    lines = (tmp_path / "update.conf").read_text(encoding="utf-8").splitlines()
    assert lines == ["# keep", "host=localhost", "channel=main", "check=on"]
    assert not (tmp_path / "update.conf.tmp").exists()


def test_write_conf_invalid_raises(tmp_path: Path) -> None:
    original = "host=localhost\nchannel=main\n"
    (tmp_path / "update.conf").write_text(original, encoding="utf-8")

    with pytest.raises(ValueError):
        write_conf(tmp_path, channel="beta")
    with pytest.raises(ValueError):
        write_conf(tmp_path, check="yes")

    assert (tmp_path / "update.conf").read_text(encoding="utf-8") == original
    assert not (tmp_path / "update.conf.tmp").exists()


def _run_with_returncode(returncode: int) -> Callable[..., subprocess.CompletedProcess[bytes]]:
    def _run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(args=b"systemctl", returncode=returncode)

    return _run


def _run_oserror(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
    raise OSError("boom")


def _run_timeout(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
    raise subprocess.TimeoutExpired("x", 1)


def test_is_running_true() -> None:
    assert is_running(_run_with_returncode(0)) is True


def test_is_running_false_nonzero() -> None:
    assert is_running(_run_with_returncode(3)) is False


def test_is_running_false_oserror() -> None:
    assert is_running(_run_oserror) is False


def test_is_running_false_timeout() -> None:
    assert is_running(_run_timeout) is False


def test_start_update_true_and_argv() -> None:
    captured: list[object] = []

    def _run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        if args:
            captured.append(args[0])
        return subprocess.CompletedProcess(args=b"systemd-run", returncode=0)

    assert start_update(_run) is True
    assert len(captured) == 1
    argv = captured[0]
    assert isinstance(argv, list)
    assert argv[0] == "systemd-run"
    assert "--unit=pearlie-update" in argv
    assert "--from-ui" in argv


def test_start_update_false_nonzero() -> None:
    assert start_update(_run_with_returncode(1)) is False


def test_start_update_false_oserror() -> None:
    assert start_update(_run_oserror) is False
