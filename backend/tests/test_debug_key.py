"""Debug key: store, guard, read-only router (D-34). Mocks only; no real Stash, Stump or sites."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app import debug_key
from app import logs as logs_mod
from app.config import Settings
from app.db import connect
from app.main import create_app

SENTINEL = "SENTINELSECRET1234567890"


@pytest.fixture(autouse=True)
def _reset_logging():
    os.environ.pop(logs_mod.ENV_DEBUG, None)
    logs_mod.clear_secrets()
    yield
    if logs_mod._handler is not None:
        logging.getLogger().removeHandler(logs_mod._handler)
        logs_mod._handler.close()
    logs_mod._handler = None
    logs_mod.clear_secrets()


@pytest.fixture
def app_client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


def _make_key(client: TestClient, ttl: str = "24h") -> str:
    r = client.post("/api/options/debug-key", json={"ttl": ttl})
    assert r.status_code == 200
    return r.json()["key"]


def _auth(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def test_create_shows_key_once_and_stores_hash_only(
    app_client: TestClient, settings: Settings
) -> None:
    r = app_client.post("/api/options/debug-key", json={"ttl": "1h"})
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    key = r.json()["key"]
    assert key.startswith("pdk_") and len(key) == 4 + 43
    status = app_client.get("/api/options/debug-key").json()
    assert status["state"] == "active" and status["id"] == r.json()["id"]
    assert key not in json.dumps(status)
    conn = connect(settings.db_path)
    try:
        raw = conn.execute("SELECT value FROM settings WHERE key = 'debug_key'").fetchone()[0]
    finally:
        conn.close()
    assert key not in raw
    assert json.loads(raw)["hash"] == debug_key._digest(key)
    assert key.encode() not in Path(settings.db_path).read_bytes()


def test_bad_ttl_is_422(app_client: TestClient) -> None:
    assert app_client.post("/api/options/debug-key", json={"ttl": "2d"}).status_code == 422


def test_key_accepted_on_debug_router(app_client: TestClient) -> None:
    key = _make_key(app_client)
    r = app_client.get("/api/debug/whoami", headers=_auth(key))
    assert r.status_code == 200
    assert r.json()["scope"]
    for path in ("/api/debug/state", "/api/debug/jobs", "/api/debug/rules", "/api/debug/trash"):
        assert app_client.get(path, headers=_auth(key)).status_code == 200, path
    assert app_client.get("/api/debug/saved", headers=_auth(key)).status_code == 200


def test_401_same_body_for_none_wrong_off_expired_revoked(app_client: TestClient) -> None:
    bodies = []
    r = app_client.get("/api/debug/whoami")  # off, no header
    bodies.append(r.json())
    assert r.status_code == 401
    bodies.append(app_client.get("/api/debug/whoami", headers=_auth("pdk_wrong")).json())
    key = _make_key(app_client)
    bodies.append(app_client.get("/api/debug/whoami", headers=_auth("pdk_wrong")).json())
    app_client.delete("/api/options/debug-key")
    r = app_client.get("/api/debug/whoami", headers=_auth(key))  # revoked
    assert r.status_code == 401
    bodies.append(r.json())
    key2 = _make_key(app_client)
    settings = app_client.app.state.settings  # type: ignore[attr-defined]
    rec = debug_key.read_record(settings.db_path)
    assert rec is not None
    rec["expires_at"] = "2000-01-01T00:00:00Z"
    conn = connect(settings.db_path)
    try:
        conn.execute("UPDATE settings SET value=? WHERE key='debug_key'", (json.dumps(rec),))
        conn.commit()
    finally:
        conn.close()
    r = app_client.get("/api/debug/whoami", headers=_auth(key2))  # expired
    assert r.status_code == 401
    bodies.append(r.json())
    assert all(b == bodies[0] for b in bodies)
    assert app_client.get("/api/options/debug-key").json()["state"] == "expired"


def test_replace_acts_on_next_request(app_client: TestClient) -> None:
    old = _make_key(app_client)
    new = _make_key(app_client)
    assert app_client.get("/api/debug/whoami", headers=_auth(old)).status_code == 401
    assert app_client.get("/api/debug/whoami", headers=_auth(new)).status_code == 200


def test_header_forms(app_client: TestClient) -> None:
    key = _make_key(app_client)
    for value in (key, f"bearer {key}", f"Basic {key}", f"Bearer  {key}", "Bearer "):
        r = app_client.get("/api/debug/whoami", headers={"Authorization": value})
        assert r.status_code == 401, value
    r = app_client.get("/api/debug/whoami", params={"key": key, "api_key": key})
    assert r.status_code == 401


def test_key_ignored_on_other_routes(app_client: TestClient) -> None:
    key = _make_key(app_client)
    for path in ("/api/options", "/api/jobs", "/api/logs"):
        plain = app_client.get(path)
        keyed = app_client.get(path, headers=_auth(key))
        assert plain.status_code == keyed.status_code, path


def test_debug_routes_are_get_only(app_client: TestClient) -> None:
    for route in app_client.app.routes:  # type: ignore[attr-defined]
        if isinstance(route, APIRoute) and route.path.startswith("/api/debug"):
            assert (route.methods or set()) <= {"GET", "HEAD"}, route.path
    key = _make_key(app_client)
    for method in ("post", "put", "patch", "delete"):
        r = getattr(app_client, method)("/api/debug/jobs", headers=_auth(key))
        assert r.status_code == 405, method


def _raw_get(app, path: str, key: str) -> tuple[int, bytes]:
    """Call the ASGI app with an exact decoded path (an HTTP client would normalise it)."""
    sent: list[dict] = []

    async def receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "query_string": b"",
        "headers": [(b"host", b"localhost"), (b"authorization", f"Bearer {key}".encode())],
        "client": ("testclient", 50000),
        "server": ("localhost", 80),
        "app": app,
    }
    asyncio.run(app(scope, receive, send))
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return status, body


@pytest.mark.parametrize(
    "path",
    [
        "/api/debug/../options",
        "/api/debug/%2e%2e/options",
        "/api/debug%2Foptions",
        "//api/debug/whoami",
        "/API/DEBUG/whoami",
        "/api/debug/whoami;x",
        "/api/debug/..\\options",
        "/api/debugx",
        "/api/debug//whoami",
    ],
)
def test_path_confusion_never_reaches_other_route(app_client: TestClient, path: str) -> None:
    key = _make_key(app_client)
    status, body = _raw_get(app_client.app, path, key)
    assert status in (401, 404, 405), (status, body[:80])
    assert b"debug_key" not in body


def test_failure_limit_gives_429_even_with_valid_key(app_client: TestClient) -> None:
    key = _make_key(app_client)
    for _ in range(debug_key.FAIL_LIMIT):
        assert app_client.get("/api/debug/whoami", headers=_auth("pdk_bad")).status_code == 401
    r = app_client.get("/api/debug/whoami", headers=_auth(key))
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) >= 1


def test_unknown_route_with_valid_key_does_not_count(app_client: TestClient) -> None:
    key = _make_key(app_client)
    for _ in range(debug_key.FAIL_LIMIT + 2):
        assert app_client.get("/api/debug/nope", headers=_auth(key)).status_code == 404
    assert app_client.get("/api/debug/whoami", headers=_auth(key)).status_code == 200


def test_audit_line_fields_and_no_values(
    app_client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    key = _make_key(app_client)
    with caplog.at_level(logging.INFO, logger="pearlie.debugkey"):
        app_client.get(
            "/api/debug/jobs", params={"state": "SECRETVALUE", "limit": 5}, headers=_auth(key)
        )
        app_client.get("/api/debug/whoami", headers=_auth("pdk_" + "x" * 43))
    text = "\n".join(r.getMessage() for r in caplog.records)
    kid = key and debug_key._digest(key)[:8]
    assert f"kid={kid} GET /api/debug/jobs params=state,limit status=200" in text
    assert "ms=" in text and "peer=" in text and "xff=" in text
    assert "SECRETVALUE" not in text
    assert key not in text


def test_scrub_removes_pdk_string() -> None:
    assert "pdk_" not in logs_mod.scrub("saw pdk_" + "A" * 43 + " here")


def test_sentinels_scrubbed_and_secrets_absent(app_client: TestClient, settings: Settings) -> None:
    key = _make_key(app_client)
    conn = connect(settings.db_path)
    try:
        conn.execute(
            "INSERT INTO jobs (source, post_id, status, error, title, post_json, thumb_url, "
            "notices, dest_path) VALUES ('danbooru', '1', 'failed', ?, ?, '{\"s\":\"POSTJSONX\"}', "
            "'http://t/THUMBX', ?, ?)",
            (
                f"GET https://h/x?api_key={SENTINEL} failed",
                f"t https://u:{SENTINEL}@h/",
                json.dumps([f"token={SENTINEL}"]),
                f"/data/x?password={SENTINEL}",
            ),
        )
        conn.commit()
    finally:
        conn.close()
    bodies = [
        app_client.get("/api/debug/jobs", headers=_auth(key)).text,
        app_client.get("/api/debug/jobs/1", headers=_auth(key)).text,
        app_client.get("/api/debug/state", headers=_auth(key)).text,
    ]
    for body in bodies:
        assert SENTINEL not in body
        assert "POSTJSONX" not in body and "THUMBX" not in body
        assert "post_json" not in body and "thumb_url" not in body
