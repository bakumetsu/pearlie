"""Tests for backend/app/api/update.py."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.update import version as update_version


@dataclass(frozen=True)
class _Latest:
    version: str
    commit: str | None = None
    url: str = "https://example.invalid/"


@dataclass(frozen=True)
class _CheckResult:
    latest: _Latest | None = None
    error: str | None = None
    checked_at: str | None = None
    retry_after: int | None = None


class _FakeChecker:
    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.check_calls = 0
        self.cached_calls = 0

    def check(self, channel: str, *, force: bool = False) -> _CheckResult | None:
        self.check_calls += 1
        return self._result()

    def cached(self, channel: str) -> _CheckResult | None:
        self.cached_calls += 1
        return self._result()

    def _result(self) -> _CheckResult | None:
        if self.mode == "available":
            return _CheckResult(
                latest=_Latest(version="9.9.9"),
                checked_at="2026-01-01T00:00:00Z",
            )
        if self.mode == "current":
            current = update_version.current_version()
            return _CheckResult(
                latest=_Latest(version=current.version),
                checked_at="2026-01-01T00:00:00Z",
            )
        if self.mode == "unreachable":
            return _CheckResult(
                error="unreachable",
                checked_at="2026-01-01T00:00:00Z",
            )
        return None


def _error_code(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("error") or payload.get("code") or "")


def test_status_fixture_mode(client: TestClient) -> None:
    resp = client.get("/api/update/status")
    assert resp.status_code == 200

    payload = cast(dict[str, Any], resp.json())
    assert set(payload) == {
        "installed",
        "latest",
        "available",
        "checked_at",
        "check_enabled",
        "channel",
        "state",
        "step",
        "error",
        "retry_after",
        "can_apply",
    }
    assert payload["can_apply"] is False
    assert payload["channel"] == "main"
    assert payload["state"] == "idle"
    assert payload["check_enabled"] is True


def test_status_refresh_with_fake_checker_modes(client: TestClient) -> None:
    app = cast(FastAPI, client.app)

    app.state.update_checker = _FakeChecker("available")
    resp = client.get("/api/update/status?refresh=1")
    assert resp.status_code == 200
    payload = cast(dict[str, Any], resp.json())
    assert payload["latest"]["version"] == "9.9.9"
    assert payload["available"] is True

    app.state.update_checker = _FakeChecker("current")
    resp = client.get("/api/update/status?refresh=1")
    assert resp.status_code == 200
    payload = cast(dict[str, Any], resp.json())
    assert payload["available"] is False

    app.state.update_checker = _FakeChecker("unreachable")
    resp = client.get("/api/update/status?refresh=1")
    assert resp.status_code == 200
    payload = cast(dict[str, Any], resp.json())
    assert payload["error"] == "unreachable"


def test_disable_check_blocks_refresh_but_manual_still_checks(client: TestClient) -> None:
    app = cast(FastAPI, client.app)

    resp = client.put("/api/update/settings", json={"check_enabled": False})
    assert resp.status_code == 200
    assert cast(dict[str, Any], resp.json())["check_enabled"] is False

    counter = _FakeChecker("current")
    app.state.update_checker = counter

    resp = client.get("/api/update/status?refresh=1")
    assert resp.status_code == 200
    assert counter.check_calls == 0

    resp = client.get("/api/update/status?refresh=1&manual=1")
    assert resp.status_code == 200
    assert counter.check_calls == 1


def test_update_settings_validation(client: TestClient) -> None:
    resp = client.put("/api/update/settings", json={"channel": "dev"})
    assert resp.status_code == 200
    assert cast(dict[str, Any], resp.json())["channel"] == "dev"

    resp = client.put("/api/update/settings", json={"channel": "beta"})
    assert resp.status_code == 422

    resp = client.put("/api/update/settings", json={})
    assert resp.status_code == 422

    resp = client.put("/api/update/settings", json={"check_enabled": "yes"})
    assert resp.status_code == 422


def test_update_settings_writes_conf_only_when_supported(
    client: TestClient, tmp_path: Path
) -> None:
    app = cast(FastAPI, client.app)

    supported_root = tmp_path / "supported"
    supported_root.mkdir()
    (supported_root / "current").mkdir()
    app.state.update_root = supported_root

    resp = client.put("/api/update/settings", json={"channel": "dev"})
    assert resp.status_code == 200

    conf = supported_root / "update.conf"
    assert conf.is_file()
    assert "channel=dev" in conf.read_text(encoding="utf-8")

    unsupported_root = tmp_path / "unsupported"
    unsupported_root.mkdir()
    app.state.update_root = unsupported_root

    resp = client.put("/api/update/settings", json={"channel": "dev"})
    assert resp.status_code == 200
    assert not (unsupported_root / "update.conf").exists()


class _FakeRun:
    def __init__(self, systemd_returncode: int = 0) -> None:
        self.calls: list[list[str]] = []
        self.systemd_returncode = systemd_returncode

    def __call__(self, argv: list[str], *args: object, **kwargs: object) -> CompletedProcess[str]:
        self.calls.append(list(argv))
        if not argv:
            return CompletedProcess(str(argv), 0, "", "")

        first = str(argv[0])
        if "is-active" in first or "is-active" in " ".join(str(x) for x in argv):
            return CompletedProcess(str(argv), 3, "", "")
        if "systemd-run" in first or "systemd-run" in " ".join(str(x) for x in argv):
            return CompletedProcess(str(argv), self.systemd_returncode, "", "")

        return CompletedProcess(str(argv), 0, "", "")


def _enable_real_mode(client: TestClient, tmp_path: Path, fake_run: _FakeRun) -> None:
    app = cast(FastAPI, client.app)
    current_settings = app.state.settings
    app.state.settings = current_settings.model_copy(update={"mode": "real"})
    app.state.update_root = tmp_path
    (tmp_path / "current").mkdir(exist_ok=True)
    app.state.update_run = fake_run


def test_apply_real_mode_starts_update(client: TestClient, tmp_path: Path) -> None:
    fake_run = _FakeRun(systemd_returncode=0)
    _enable_real_mode(client, tmp_path, fake_run)
    app = cast(FastAPI, client.app)
    app.state.update_checker = _FakeChecker("available")

    resp = client.post("/api/update/apply")
    assert resp.status_code == 202
    assert cast(dict[str, Any], resp.json()) == {"state": "running"}
    assert any("systemd-run" in str(argv[0]) for argv in fake_run.calls if argv)


def test_apply_real_mode_up_to_date(client: TestClient, tmp_path: Path) -> None:
    fake_run = _FakeRun(systemd_returncode=0)
    _enable_real_mode(client, tmp_path, fake_run)
    app = cast(FastAPI, client.app)
    app.state.update_checker = _FakeChecker("current")

    resp = client.post("/api/update/apply")
    assert resp.status_code == 409
    assert _error_code(resp.json()) == "up_to_date"


def test_apply_real_mode_already_running(client: TestClient, tmp_path: Path) -> None:
    fake_run = _FakeRun(systemd_returncode=0)
    _enable_real_mode(client, tmp_path, fake_run)
    app = cast(FastAPI, client.app)
    app.state.update_checker = _FakeChecker("available")

    (tmp_path / "update-status.json").write_text(json.dumps({"state": "running"}), encoding="utf-8")

    resp = client.post("/api/update/apply")
    assert resp.status_code == 409
    assert _error_code(resp.json()) == "already_running"


def test_apply_real_mode_start_failure(client: TestClient, tmp_path: Path) -> None:
    fake_run = _FakeRun(systemd_returncode=1)
    _enable_real_mode(client, tmp_path, fake_run)
    app = cast(FastAPI, client.app)
    app.state.update_checker = _FakeChecker("available")

    resp = client.post("/api/update/apply")
    assert resp.status_code == 500
    assert _error_code(resp.json()) == "start_failed"


def test_apply_unsupported_in_fixture_mode(client: TestClient) -> None:
    resp = client.post("/api/update/apply")
    assert resp.status_code == 503
    assert _error_code(resp.json()) == "unsupported"


@pytest.mark.no_default_origin
def test_write_guard_rejects_missing_or_bad_origin(client: TestClient) -> None:
    resp = client.post("/api/update/apply")
    assert resp.status_code == 403
    assert _error_code(resp.json()) == "forbidden"

    resp = client.put("/api/update/settings", json={"channel": "dev"})
    assert resp.status_code == 403
    assert _error_code(resp.json()) == "forbidden"

    resp = client.post(
        "/api/update/apply",
        headers={"Origin": "http://evil.example"},
    )
    assert resp.status_code == 403
    assert _error_code(resp.json()) == "forbidden"

    resp = client.put(
        "/api/update/settings",
        headers={"Origin": "http://evil.example"},
        json={"channel": "dev"},
    )
    assert resp.status_code == 403
    assert _error_code(resp.json()) == "forbidden"


@pytest.mark.no_default_origin
def test_write_guard_rejects_non_json_content_type(client: TestClient) -> None:
    resp = client.put(
        "/api/update/settings",
        content="{}",
        headers={
            "Origin": "http://testserver",
            "Content-Type": "text/plain",
        },
    )
    assert resp.status_code == 415
