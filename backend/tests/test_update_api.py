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

from app.db import SCHEMA_VERSION, connect
from app.update import runner
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
        "rollback",
        "jobs_running",
        "started_at",
        "can_restart",
    }
    assert payload["rollback"] is None
    assert payload["jobs_running"] == 0
    assert payload["can_restart"] is False
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
            "Origin": "http://localhost",
            "Content-Type": "text/plain",
        },
    )
    assert resp.status_code == 415


def _add_previous(
    root: Path, schema: int | None, *, backup: bool = True, version: str = "0.9.2"
) -> None:
    prev = root / "previous" / "app"
    prev.mkdir(parents=True)
    data: dict[str, Any] = {"version": version, "channel": "main", "commit": None}
    if schema is not None:
        data["schema"] = schema
    (prev / "VERSION.json").write_text(json.dumps(data), encoding="utf-8")
    if backup:
        (root / "backups" / "current").mkdir(parents=True)


def _add_running_job(client: TestClient) -> None:
    app = cast(FastAPI, client.app)
    conn = connect(app.state.settings.db_path)
    conn.execute("INSERT INTO jobs (source, post_id, status) VALUES ('danbooru', '1', 'running')")
    conn.commit()
    conn.close()


def test_status_rollback_schema_verdicts(client: TestClient, tmp_path: Path) -> None:
    _enable_real_mode(client, tmp_path, _FakeRun())
    assert client.get("/api/update/status").json()["rollback"] is None

    _add_previous(tmp_path, None)
    data = cast(dict[str, Any], client.get("/api/update/status").json())
    assert data["can_restart"] is True
    assert data["rollback"]["version"] == "0.9.2"
    assert data["rollback"]["schema"] == "unknown"
    assert data["rollback"]["backup_at"] is not None

    (tmp_path / "previous" / "app" / "VERSION.json").write_text(
        json.dumps({"version": "0.9.2", "channel": "main", "commit": None, "schema": SCHEMA_VERSION}),
        encoding="utf-8",
    )
    assert client.get("/api/update/status").json()["rollback"]["schema"] == "same"

    (tmp_path / "previous" / "app" / "VERSION.json").write_text(
        json.dumps(
            {"version": "0.9.2", "channel": "main", "commit": None, "schema": SCHEMA_VERSION - 1}
        ),
        encoding="utf-8",
    )
    assert client.get("/api/update/status").json()["rollback"]["schema"] == "changed"


def test_restart_unsupported_in_fixture_mode(client: TestClient) -> None:
    resp = client.post("/api/update/restart", json={})
    assert resp.status_code == 503
    assert _error_code(resp.json()) == "unsupported"


def test_restart_starts_transient_unit(client: TestClient, tmp_path: Path) -> None:
    fake_run = _FakeRun()
    _enable_real_mode(client, tmp_path, fake_run)
    resp = client.post("/api/update/restart", json={})
    assert resp.status_code == 202
    assert resp.json() == {"state": "restarting"}
    assert any(
        argv[:2] == ["systemd-run", "--unit=pearlie-restart"] and argv[-3:] == ["systemctl", "restart", "pearlie"]
        for argv in fake_run.calls
    )


def test_restart_blocked_by_running_jobs_unless_forced(client: TestClient, tmp_path: Path) -> None:
    fake_run = _FakeRun()
    _enable_real_mode(client, tmp_path, fake_run)
    _add_running_job(client)
    assert client.get("/api/update/status").json()["jobs_running"] == 1

    resp = client.post("/api/update/restart", json={})
    assert resp.status_code == 409
    assert _error_code(resp.json()) == "jobs_running"
    assert resp.json()["count"] == 1
    assert not any("systemd-run" in argv[0] for argv in fake_run.calls)

    assert client.post("/api/update/restart", json={"force": True}).status_code == 202


def test_restart_blocked_while_update_runs(client: TestClient, tmp_path: Path) -> None:
    _enable_real_mode(client, tmp_path, _FakeRun())
    (tmp_path / "update-status.json").write_text(json.dumps({"state": "running"}), encoding="utf-8")
    resp = client.post("/api/update/restart", json={})
    assert resp.status_code == 409
    assert _error_code(resp.json()) == "already_running"


def test_restart_start_failure(client: TestClient, tmp_path: Path) -> None:
    _enable_real_mode(client, tmp_path, _FakeRun(systemd_returncode=1))
    resp = client.post("/api/update/restart", json={})
    assert resp.status_code == 500
    assert _error_code(resp.json()) == "start_failed"


def test_rollback_unsupported_in_fixture_mode(client: TestClient) -> None:
    resp = client.post("/api/update/rollback", json={})
    assert resp.status_code == 503


def test_rollback_no_previous(client: TestClient, tmp_path: Path) -> None:
    _enable_real_mode(client, tmp_path, _FakeRun())
    resp = client.post("/api/update/rollback", json={})
    assert resp.status_code == 409
    assert _error_code(resp.json()) == "no_previous"


def test_rollback_code_only_and_restore_args(client: TestClient, tmp_path: Path) -> None:
    fake_run = _FakeRun()
    _enable_real_mode(client, tmp_path, fake_run)
    _add_previous(tmp_path, None)

    resp = client.post("/api/update/rollback", json={})
    assert resp.status_code == 202
    assert resp.json() == {"state": "running"}
    call = next(argv for argv in fake_run.calls if argv and argv[0] == "systemd-run")
    assert call[-3:] == ["/usr/local/bin/pearlie-update", "--rollback", "--from-ui"]

    fake_run.calls.clear()
    assert client.post("/api/update/rollback", json={"restore_db": True}).status_code == 202
    call = next(argv for argv in fake_run.calls if argv and argv[0] == "systemd-run")
    assert call[-3:] == ["--rollback", "--restore-db", "--from-ui"]


def test_rollback_restore_needs_backup(client: TestClient, tmp_path: Path) -> None:
    fake_run = _FakeRun()
    _enable_real_mode(client, tmp_path, fake_run)
    _add_previous(tmp_path, None, backup=False)
    resp = client.post("/api/update/rollback", json={"restore_db": True})
    assert resp.status_code == 409
    assert _error_code(resp.json()) == "no_backup"
    assert not any("systemd-run" in argv[0] for argv in fake_run.calls)
    assert client.post("/api/update/rollback", json={}).status_code == 202


def test_rollback_blocked_by_jobs_and_running_update(client: TestClient, tmp_path: Path) -> None:
    _enable_real_mode(client, tmp_path, _FakeRun())
    _add_previous(tmp_path, None)
    _add_running_job(client)
    resp = client.post("/api/update/rollback", json={})
    assert resp.status_code == 409
    assert _error_code(resp.json()) == "jobs_running"
    assert client.post("/api/update/rollback", json={"force": True}).status_code == 202

    (tmp_path / "update-status.json").write_text(json.dumps({"state": "running"}), encoding="utf-8")
    resp = client.post("/api/update/rollback", json={"force": True})
    assert _error_code(resp.json()) == "already_running"


def test_read_previous_reads_version_schema_backup(tmp_path: Path) -> None:
    assert runner.read_previous(tmp_path) is None
    (tmp_path / "current").mkdir()
    _add_previous(tmp_path, 3, version="0.9.2+abc")
    version, schema, backup_at = cast(tuple[str, int | None, str | None], runner.read_previous(tmp_path))
    assert (version, schema) == ("0.9.2", 3)
    assert backup_at is not None
