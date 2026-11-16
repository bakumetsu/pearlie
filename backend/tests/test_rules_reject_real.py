"""Tests for POST/DELETE /api/rules/reject (real router)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from app.config import Settings
from app.db import init_db
from app.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    """Real-mode client with an empty rules store."""
    db_path = tmp_path / "p.db"
    init_db(db_path)
    settings = Settings(
        mode="real",
        real="rules",
        db_path=db_path,
        static_dir=tmp_path / "nostatic",
        worker_enabled=False,
        _env_file=None,  # pyright: ignore[reportCallIssue]
    )
    return TestClient(create_app(settings))


def _reject(client: TestClient, method: str, tag: str) -> Response:
    return client.request(method, "/api/rules/reject", json={"tag": tag})


def _put_keep(client: TestClient) -> None:
    client.put(
        "/api/rules",
        json={"version": 1, "reject": ["keep"], "warn": [], "require": [], "mapping": []},
    )


def test_reject_add_and_undo(client: TestClient) -> None:
    """POST adds a tag, a second POST is a no-op, DELETE removes only that tag."""
    _put_keep(client)
    r = _reject(client, "POST", " new ")
    assert r.status_code == 200
    assert r.json() == {"added": True, "version": 3}
    assert _reject(client, "POST", "new").json() == {"added": False, "version": 3}
    assert client.get("/api/rules").json()["reject"] == ["keep", "new"]
    assert _reject(client, "DELETE", "new").json() == {"removed": True, "version": 4}
    assert _reject(client, "DELETE", "new").json() == {"removed": False, "version": 4}
    assert client.get("/api/rules").json()["reject"] == ["keep"]


def test_reject_invalid_tag(client: TestClient) -> None:
    """An empty or long tag gives 422 with the field."""
    for tag in ("  ", "x" * 65):
        r = _reject(client, "POST", tag)
        assert r.status_code == 422
        assert r.json()["field"] == "tag"


def test_reject_retries_stale(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """A concurrent change between read and save is retried and kept."""
    from app.api import rules_real

    real_save = rules_real.save_rules
    calls = {"n": 0}

    def racing(db_path, version, new):
        calls["n"] += 1
        if calls["n"] == 1:
            real_save(db_path, version, rules_real.RuleSet(version, ["other"], [], [], []))
        return real_save(db_path, version, new)

    monkeypatch.setattr(rules_real, "save_rules", racing)
    assert _reject(client, "POST", "mine").json()["added"] is True
    assert client.get("/api/rules").json()["reject"] == ["other", "mine"]


def test_reject_gives_up_after_three_stale(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Three stale saves in a row give 409 stale_version."""
    from app.api import rules_real

    def stale(*_a, **_k):
        raise rules_real.StaleVersion()

    monkeypatch.setattr(rules_real, "save_rules", stale)
    r = _reject(client, "POST", "x")
    assert r.status_code == 409
    assert r.json()["code"] == "stale_version"
