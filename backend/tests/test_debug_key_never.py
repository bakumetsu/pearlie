"""Debug key with no expiry: "never" lives until Revoke (D-34). Mocks only."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app import debug_key
from app import logs as logs_mod
from app.config import Settings
from app.db import connect
from app.main import create_app


@pytest.fixture(autouse=True)
def _reset_secrets():
    os.environ.pop(logs_mod.ENV_DEBUG, None)
    logs_mod.clear_secrets()
    yield
    logs_mod.clear_secrets()


@pytest.fixture
def app_client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


def _make_key(client: TestClient, ttl: str) -> str:
    r = client.post("/api/options/debug-key", json={"ttl": ttl})
    assert r.status_code == 200
    return r.json()["key"]


def _auth(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def test_never_key_has_no_expiry_and_revoke_ends_it(app_client: TestClient) -> None:
    r = app_client.post("/api/options/debug-key", json={"ttl": "never"})
    assert r.status_code == 200
    assert r.json()["expires_at"] is None
    key = r.json()["key"]
    status = app_client.get("/api/options/debug-key").json()
    assert status["state"] == "active"
    assert status["expires_at"] is None
    who = app_client.get("/api/debug/whoami", headers=_auth(key))
    assert who.status_code == 200
    assert who.json()["expires_at"] is None
    settings = app_client.app.state.settings  # type: ignore[attr-defined]
    assert key not in json.dumps(debug_key.read_record(settings.db_path))  # hash only
    app_client.delete("/api/options/debug-key")
    assert app_client.get("/api/debug/whoami", headers=_auth(key)).status_code == 401
    assert app_client.get("/api/options/debug-key").json()["state"] == "off"


def test_never_key_works_far_in_the_future(
    app_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = _make_key(app_client, "never")
    monkeypatch.setattr(debug_key, "_now", lambda: datetime(2099, 1, 1, tzinfo=UTC))
    assert app_client.get("/api/debug/whoami", headers=_auth(key)).status_code == 200


def test_null_expiry_without_never_flag_fails_closed(app_client: TestClient) -> None:
    key = _make_key(app_client, "24h")
    settings = app_client.app.state.settings  # type: ignore[attr-defined]
    rec = debug_key.read_record(settings.db_path)
    assert rec is not None
    rec["expires_at"] = None
    conn = connect(settings.db_path)
    try:
        conn.execute("UPDATE settings SET value=? WHERE key='debug_key'", (json.dumps(rec),))
        conn.commit()
    finally:
        conn.close()
    assert app_client.get("/api/debug/whoami", headers=_auth(key)).status_code == 401
    assert app_client.get("/api/options/debug-key").json()["state"] == "expired"


def test_existing_ttls_still_expire(app_client: TestClient) -> None:
    for ttl in ("1h", "24h", "7d"):
        r = app_client.post("/api/options/debug-key", json={"ttl": ttl})
        assert r.status_code == 200
        assert r.json()["expires_at"] is not None
    assert app_client.post("/api/options/debug-key", json={"ttl": "2d"}).status_code == 422
