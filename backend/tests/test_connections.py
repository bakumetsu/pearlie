"""Connections API security tests."""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import Any

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.config import Settings
from app.komga import Komga
from app.main import create_app
from app.targets.stash_client import StashClient

pytestmark = pytest.mark.no_default_origin

HDR: dict[str, str] = {
    "Origin": "http://testserver",
    "Content-Type": "application/json",
}


def master_key() -> str:
    return Fernet.generate_key().decode()


def make_client(
    tmp_path: Path,
    *,
    mode: str = "fixture",
    secret_key: str = "",
    env: dict[str, Any] | None = None,
    transport: httpx.BaseTransport | None = None,
) -> TestClient:
    kwargs: dict[str, Any] = {
        "mode": mode,
        "db_path": tmp_path / "p.db",
        "static_dir": tmp_path / "nostatic",
        "secret_key": secret_key,
    }
    if env:
        kwargs.update(env)
    settings = Settings(**kwargs, _env_file=None)  # pyright: ignore[reportCallIssue]
    app = create_app(settings)
    if transport is not None:
        app.state.connection_transport = transport
    return TestClient(app, base_url="http://testserver")


# ---------------------------------------------------------------------------
# 1. GET lists names in order; key state
# ---------------------------------------------------------------------------


def test_list_names_and_key_state(tmp_path: Path) -> None:
    c = make_client(tmp_path)
    r = c.get("/api/connections")
    assert r.status_code == 200
    data = r.json()
    assert data["can_store"] is True
    names = [x["name"] for x in data["connections"]]
    assert names == ["stash", "komga", "danbooru", "gelbooru", "rule34", "nhentai"]
    for conn in data["connections"]:
        assert conn["key"] == "missing"

    c2 = make_client(tmp_path, secret_key=master_key())
    assert c2.get("/api/connections").json()["can_store"] is True


# ---------------------------------------------------------------------------
# 1b. Auto-generated key file
# ---------------------------------------------------------------------------


def test_auto_key_file_created_and_reused(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    key_file = tmp_path / "secret.key"
    assert not key_file.exists()
    with caplog.at_level(logging.DEBUG):
        c = make_client(tmp_path, mode="real", env={"real": "search"})
        assert c.get("/api/connections").json()["can_store"] is True
        first = key_file.read_text(encoding="utf-8").strip()
        Fernet(first)
        r = c.put(
            "/api/connections/stash",
            json={"address": "http://stash.local:9999", "secret": "s3cret-value"},
            headers=HDR,
        )
        assert r.status_code == 200
        listing = c.get("/api/connections")
    if os.name == "posix":
        assert key_file.stat().st_mode & 0o077 == 0
    assert first not in listing.text
    assert first not in caplog.text

    c2 = make_client(tmp_path, mode="real", env={"real": "search"})
    assert c2.get("/api/connections").json()["can_store"] is True
    assert key_file.read_text(encoding="utf-8").strip() == first
    assert c2.get("/api/connections").json()["connections"][0]["key"] == "set"


def test_env_key_wins_no_file(tmp_path: Path) -> None:
    c = make_client(tmp_path, secret_key=master_key())
    assert c.get("/api/connections").json()["can_store"] is True
    assert not (tmp_path / "secret.key").exists()


def test_invalid_env_key_falls_back_to_key_file(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    bad = "ab" * 32  # openssl rand -hex 32 style, not a Fernet key
    with caplog.at_level(logging.DEBUG):
        c = make_client(tmp_path, secret_key=bad)
        assert c.get("/api/connections").json()["can_store"] is True
    assert (tmp_path / "secret.key").exists()
    assert "not a valid key" in caplog.text
    assert bad not in caplog.text


# ---------------------------------------------------------------------------
# 2. PUT secret: encrypted at rest, not in responses
# ---------------------------------------------------------------------------


def test_put_secret_encrypted_at_rest(tmp_path: Path) -> None:
    mk = master_key()
    c = make_client(
        tmp_path, mode="real", secret_key=mk, env={"real": "search"}
    )
    secret = "hunter2-abc123"
    r = c.put(
        "/api/connections/stash",
        json={"address": "http://stash.local:9999", "secret": secret},
        headers=HDR,
    )
    assert r.status_code == 200
    assert r.json()["key"] == "set"
    assert secret not in r.text

    r2 = c.get("/api/connections")
    assert secret not in r2.text

    conn = sqlite3.connect(str(tmp_path / "p.db"))
    row = conn.execute(
        "SELECT value FROM settings WHERE key='connections.stash.secret'"
    ).fetchone()
    conn.close()
    assert row is not None
    raw: str = row[0]
    assert secret not in raw
    decrypted = Fernet(mk.encode()).decrypt(raw.encode()).decode()
    assert decrypted == secret


# ---------------------------------------------------------------------------
# 3. PUT secret without master key -> 409
# ---------------------------------------------------------------------------


def test_put_secret_no_master_key(tmp_path: Path) -> None:
    (tmp_path / "secret.key").mkdir()  # key file cannot be created
    c = make_client(tmp_path)
    assert c.get("/api/connections").json()["can_store"] is False
    r = c.put(
        "/api/connections/stash",
        json={"secret": "someval"},
        headers=HDR,
    )
    assert r.status_code == 409
    assert r.json()["code"] == "no_master_key"

    r2 = c.get("/api/connections")
    stash = next(x for x in r2.json()["connections"] if x["name"] == "stash")
    assert stash["key"] == "missing"


# ---------------------------------------------------------------------------
# 4. .env wins and locks
# ---------------------------------------------------------------------------


def test_env_wins_and_locks(tmp_path: Path) -> None:
    env = {"stash_api_key": "envsecret", "stash_url": "http://stash.local:9999"}
    c = make_client(tmp_path, secret_key=master_key(), env=env)
    r = c.get("/api/connections")
    stash = next(x for x in r.json()["connections"] if x["name"] == "stash")
    assert stash["key"] == "set"
    assert stash["key_locked"] is True
    assert stash["address_locked"] is True
    assert stash["address"] == "http://stash.local:9999"
    assert "envsecret" not in r.text

    r2 = c.put(
        "/api/connections/stash", json={"secret": "newkey"}, headers=HDR
    )
    assert r2.status_code == 409
    assert r2.json()["code"] == "locked"
    assert "envsecret" not in r2.text

    r3 = c.put(
        "/api/connections/stash",
        json={"address": "http://other:8080"},
        headers=HDR,
    )
    assert r3.status_code == 409
    assert r3.json()["code"] == "locked"
    assert "envsecret" not in r3.text


# ---------------------------------------------------------------------------
# 5. Write guards: Origin, Referer, Content-Type
# ---------------------------------------------------------------------------


def test_write_guard_origin(tmp_path: Path) -> None:
    c = make_client(tmp_path, secret_key=master_key())
    body: dict[str, Any] = {"secret": "x"}

    # Wrong Origin
    r = c.put(
        "/api/connections/stash",
        json=body,
        headers={"Origin": "http://evil.example", "Content-Type": "application/json"},
    )
    assert r.status_code == 403

    # No Origin, no Referer
    r2 = c.put(
        "/api/connections/stash",
        json=body,
        headers={"Content-Type": "application/json"},
    )
    assert r2.status_code == 403

    # Referer matches host, no Origin -> accepted
    r3 = c.put(
        "/api/connections/stash",
        json=body,
        headers={"Referer": "http://testserver", "Content-Type": "application/json"},
    )
    assert r3.status_code == 200

    # Bad Origin + invalid body -> 403 not 422
    r4 = c.put(
        "/api/connections/stash",
        json={"secret": 12345},
        headers={"Origin": "http://evil.example", "Content-Type": "application/json"},
    )
    assert r4.status_code == 403


def test_write_guard_content_type(tmp_path: Path) -> None:
    c = make_client(tmp_path, secret_key=master_key())
    r = c.put(
        "/api/connections/stash",
        content='{"secret": "x"}',
        headers={"Origin": "http://testserver", "Content-Type": "text/plain"},
    )
    assert r.status_code == 415


# ---------------------------------------------------------------------------
# 6. No CORS
# ---------------------------------------------------------------------------


def test_no_cors(tmp_path: Path) -> None:
    kwargs: dict[str, Any] = {
        "mode": "fixture",
        "db_path": tmp_path / "p.db",
        "static_dir": tmp_path / "nostatic",
        "secret_key": master_key(),
    }
    settings = Settings(**kwargs, _env_file=None)  # pyright: ignore[reportCallIssue]
    app = create_app(settings)
    c = TestClient(app, base_url="http://testserver")

    r = c.options(
        "/api/connections/stash",
        headers={
            "Origin": "http://evil.example",
            "Access-Control-Request-Method": "PUT",
        },
    )
    assert "access-control-allow-origin" not in r.headers
    assert r.status_code >= 400

    mw_names = [getattr(mw.cls, "__name__", "") for mw in app.user_middleware]
    assert "CORSMiddleware" not in mw_names


# ---------------------------------------------------------------------------
# 7. 422 handler: no input values leaked
# ---------------------------------------------------------------------------


def test_422_no_leak(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="pearlie")
    c = make_client(tmp_path, secret_key=master_key())

    r = c.put(
        "/api/connections/stash",
        json={"secret": 12345, "bogus": "TOPSECRETVALUE"},
        headers=HDR,
    )
    assert r.status_code == 422
    assert "TOPSECRETVALUE" not in r.text
    assert "12345" not in r.text
    assert "TOPSECRETVALUE" not in caplog.text

    r2 = c.put(
        "/api/connections/stash",
        json={"secret": ["TOPSECRETVALUE"]},
        headers=HDR,
    )
    assert r2.status_code == 422
    assert "TOPSECRETVALUE" not in r2.text


# ---------------------------------------------------------------------------
# 8. Logging: key change logged, secret not
# ---------------------------------------------------------------------------


def test_logging_no_secret_in_logs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="pearlie")
    c = make_client(tmp_path, secret_key=master_key())
    secret = "sUpErSeCrEt1"
    r = c.put(
        "/api/connections/stash",
        json={"address": "http://stash.local:9999", "secret": secret},
        headers=HDR,
    )
    assert r.status_code == 200
    assert "key for stash changed" in caplog.text
    assert secret not in caplog.text


# ---------------------------------------------------------------------------
# 9. Address change clears key
# ---------------------------------------------------------------------------


def test_address_change_clears_key(tmp_path: Path) -> None:
    c = make_client(tmp_path, secret_key=master_key())

    # Set address + key
    r = c.put(
        "/api/connections/stash",
        json={"address": "http://one.local:1", "secret": "k1"},
        headers=HDR,
    )
    assert r.status_code == 200
    assert r.json()["key"] == "set"

    # Change address without secret -> key cleared
    r2 = c.put(
        "/api/connections/stash",
        json={"address": "http://two.local:2"},
        headers=HDR,
    )
    assert r2.json()["key"] == "missing"

    # New address + secret in same call -> key set
    r3 = c.put(
        "/api/connections/stash",
        json={"address": "http://three.local:3", "secret": "k2"},
        headers=HDR,
    )
    assert r3.json()["key"] == "set"

    # clear_secret
    r4 = c.put(
        "/api/connections/stash", json={"clear_secret": True}, headers=HDR
    )
    assert r4.json()["key"] == "missing"

    # Invalid scheme
    r5 = c.put(
        "/api/connections/stash", json={"address": "ftp://x"}, headers=HDR
    )
    assert r5.status_code == 422

    # Fixed site address -> 422
    r6 = c.put(
        "/api/connections/danbooru",
        json={"address": "http://evil.example"},
        headers=HDR,
    )
    assert r6.status_code == 422


# ---------------------------------------------------------------------------
# 10. Test endpoint with MockTransport
# ---------------------------------------------------------------------------


def test_endpoint_connected(tmp_path: Path) -> None:
    hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        return httpx.Response(200)

    c = make_client(tmp_path, secret_key=master_key(), transport=httpx.MockTransport(handler))
    c.put(
        "/api/connections/stash",
        json={"address": "http://stash.local:9999"},
        headers=HDR,
    )
    r = c.post("/api/connections/stash/test", headers=HDR)
    assert r.status_code == 200
    assert r.json() == {"ok": True, "message": "connected"}
    assert hosts == ["stash.local"]


def test_endpoint_key_rejected(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    c = make_client(tmp_path, secret_key=master_key(), transport=httpx.MockTransport(handler))
    c.put(
        "/api/connections/stash",
        json={"address": "http://stash.local:9999"},
        headers=HDR,
    )
    r = c.post("/api/connections/stash/test", headers=HDR)
    assert r.json() == {"ok": False, "message": "key rejected"}


def test_endpoint_unreachable(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="pearlie")

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    c = make_client(
        tmp_path, secret_key=master_key(), transport=httpx.MockTransport(handler)
    )
    c.put(
        "/api/connections/stash",
        json={"address": "http://stash.local:9999", "secret": "topSecretKey99"},
        headers=HDR,
    )
    r = c.post("/api/connections/stash/test", headers=HDR)
    assert r.json() == {"ok": False, "message": "unreachable"}
    assert "ApiKey" not in caplog.text
    assert "topSecretKey99" not in caplog.text
    assert "boom" not in caplog.text


def test_endpoint_no_redirect(tmp_path: Path) -> None:
    hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        return httpx.Response(302, headers={"Location": "http://other.example/"})

    c = make_client(
        tmp_path, secret_key=master_key(), transport=httpx.MockTransport(handler)
    )
    c.put(
        "/api/connections/stash",
        json={"address": "http://stash.local:9999"},
        headers=HDR,
    )
    r = c.post("/api/connections/stash/test", headers=HDR)
    assert r.json()["ok"] is False
    assert hosts == ["stash.local"]


def test_endpoint_danbooru_fixed_host(tmp_path: Path) -> None:
    hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        return httpx.Response(200)

    c = make_client(
        tmp_path, secret_key=master_key(), transport=httpx.MockTransport(handler)
    )
    r = c.post("/api/connections/danbooru/test", headers=HDR)
    assert r.status_code == 200
    assert r.json() == {"ok": True, "message": "connected"}
    assert hosts == ["danbooru.donmai.us"]


def test_endpoint_not_configured(tmp_path: Path) -> None:
    c = make_client(tmp_path, secret_key=master_key())
    r = c.post("/api/connections/komga/test", headers=HDR)
    assert r.json() == {"ok": False, "message": "not configured"}


def test_endpoint_fixture_no_transport(tmp_path: Path) -> None:
    c = make_client(tmp_path, secret_key=master_key())
    r = c.post("/api/connections/danbooru/test", headers=HDR)
    assert r.json()["ok"] is False
    assert r.json()["message"].startswith("fixture mode")


# ---------------------------------------------------------------------------
# 11. Unknown name -> 404
# ---------------------------------------------------------------------------


def test_unknown_name_404(tmp_path: Path) -> None:
    c = make_client(tmp_path, secret_key=master_key())
    r = c.put("/api/connections/nonexist", json={"secret": "x"}, headers=HDR)
    assert r.status_code == 404

    r2 = c.post("/api/connections/nonexist/test", headers=HDR)
    assert r2.status_code == 404


# ---------------------------------------------------------------------------
# 12. Stored key but master key removed later: no crash
# ---------------------------------------------------------------------------


def test_stored_key_without_master_key_no_500(tmp_path: Path) -> None:
    c = make_client(
        tmp_path, mode="real", secret_key=master_key(), env={"real": "search"}
    )
    r = c.put(
        "/api/connections/stash",
        json={"address": "http://stash.local:9999", "secret": "hunter2"},
        headers=HDR,
    )
    assert r.status_code == 200

    c2 = make_client(tmp_path, mode="real", env={"real": "search"})
    r2 = c2.post("/api/connections/stash/test", headers=HDR)
    assert r2.status_code < 500
    assert "hunter2" not in r2.text


# ---------------------------------------------------------------------------
# 13. Proxy: Origin compared to X-Forwarded-Host when present
# ---------------------------------------------------------------------------


def test_write_guard_forwarded_host(tmp_path: Path) -> None:
    c = make_client(tmp_path, secret_key=master_key())
    body: dict[str, Any] = {"secret": "x"}
    ok = {"Origin": "http://pearlie.example", "Content-Type": "application/json"}

    # Proxy rewrote Host, browser-facing host in X-Forwarded-Host
    r = c.put(
        "/api/connections/stash",
        json=body,
        headers={**ok, "X-Forwarded-Host": "pearlie.example"},
    )
    assert r.status_code == 200

    # First value of a list wins
    r2 = c.put(
        "/api/connections/stash",
        json=body,
        headers={**ok, "X-Forwarded-Host": "pearlie.example, inner.local"},
    )
    assert r2.status_code == 200

    # Mismatch still refused, also when Origin equals the raw Host
    r3 = c.put(
        "/api/connections/stash",
        json=body,
        headers={**HDR, "X-Forwarded-Host": "pearlie.example"},
    )
    assert r3.status_code == 403
    r4 = c.put("/api/connections/stash", json=body, headers=ok)
    assert r4.status_code == 403

    # No Origin and no Referer still refused with the forwarded header
    r5 = c.put(
        "/api/connections/stash",
        json=body,
        headers={
            "Content-Type": "application/json",
            "X-Forwarded-Host": "pearlie.example",
        },
    )
    assert r5.status_code == 403


# ---------------------------------------------------------------------------
# 14. restart_needed after saving stash or komga
# ---------------------------------------------------------------------------


def test_restart_needed_flag(tmp_path: Path) -> None:
    c = make_client(tmp_path, secret_key=master_key())
    r = c.put("/api/connections/stash", json={"secret": "k"}, headers=HDR)
    assert r.json()["restart_needed"] is False
    r2 = c.put("/api/connections/komga", json={"secret": "k"}, headers=HDR)
    assert r2.json()["restart_needed"] is False
    r3 = c.put("/api/connections/gelbooru", json={"secret": "k"}, headers=HDR)
    assert r3.json()["restart_needed"] is False
    listed = c.get("/api/connections").json()["connections"]
    assert all(x["restart_needed"] is False for x in listed)


# ---------------------------------------------------------------------------
# 15. rule34 host, httpx logging, tampered token
# ---------------------------------------------------------------------------


def test_rule34_fixed_host(tmp_path: Path) -> None:
    c = make_client(tmp_path, secret_key=master_key())
    conns = c.get("/api/connections").json()["connections"]
    r34 = next(x for x in conns if x["name"] == "rule34")
    assert r34["address"] == "https://api.rule34.xxx"


def test_test_call_logs_no_secret_at_info(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    secret = "qUeRyKeY9876"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    c = make_client(
        tmp_path, secret_key=master_key(), transport=httpx.MockTransport(handler)
    )
    c.put("/api/connections/gelbooru", json={"secret": secret}, headers=HDR)
    caplog.set_level(logging.INFO)
    r = c.post("/api/connections/gelbooru/test", headers=HDR)
    assert r.status_code == 200
    assert secret not in caplog.text
    assert all(secret not in rec.getMessage() for rec in caplog.records)


def test_tampered_token_gives_empty_and_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    c = make_client(
        tmp_path, mode="real", secret_key=master_key(), env={"real": "search"}
    )
    c.put("/api/connections/stash", json={"secret": "plainval"}, headers=HDR)
    row = sqlite3.connect(str(tmp_path / "p.db"))
    stored = row.execute(
        "SELECT value FROM settings WHERE key='connections.stash.secret'"
    ).fetchone()
    row.close()
    assert stored is not None
    assert "plainval" not in stored[0]
    store = c.app.state.connection_store  # pyright: ignore[reportAttributeAccessIssue]
    store._write("connections.stash.secret", stored[0][:-4] + "AAAA")
    caplog.set_level(logging.WARNING, logger="pearlie")
    assert store.effective_secret("stash") == ""
    assert "cannot be decrypted" in caplog.text


# ---------------------------------------------------------------------------
# 16. Client swap on address change (real mode with urls set)
# ---------------------------------------------------------------------------


def _seed(c: TestClient, name: str) -> None:
    r = c.put(
        f"/api/connections/{name}",
        json={"address": f"http://{name}.local:9999", "secret": "firstkey"},
        headers=HDR,
    )
    assert r.status_code == 200


def test_put_stash_swaps_client(tmp_path: Path) -> None:
    c = make_client(
        tmp_path, mode="real", secret_key=master_key(), env={"real": "search"}
    )
    _seed(c, "stash")
    old = c.app.state.stash  # pyright: ignore[reportAttributeAccessIssue]
    assert old is not None
    c.app.state.stubbed_routes = set()  # pyright: ignore[reportAttributeAccessIssue]
    r = c.put(
        "/api/connections/stash",
        json={"address": "http://stash2.local:9999", "secret": "newkey"},
        headers=HDR,
    )
    assert r.status_code == 200
    assert r.json()["restart_needed"] is False
    assert c.app.state.stash is not old  # pyright: ignore[reportAttributeAccessIssue]
    assert isinstance(c.app.state.stash, StashClient)  # pyright: ignore[reportAttributeAccessIssue]
    assert callable(old.library_paths)


def test_put_komga_swaps_client(tmp_path: Path) -> None:
    c = make_client(
        tmp_path, mode="real", secret_key=master_key(), env={"real": "search"}
    )
    _seed(c, "komga")
    old = c.app.state.komga  # pyright: ignore[reportAttributeAccessIssue]
    assert old is not None
    c.app.state.stubbed_routes = set()  # pyright: ignore[reportAttributeAccessIssue]
    r = c.put(
        "/api/connections/komga",
        json={"address": "http://komga2.local:8888", "secret": "newkey"},
        headers=HDR,
    )
    assert r.status_code == 200
    assert r.json()["restart_needed"] is False
    assert c.app.state.komga is not old  # pyright: ignore[reportAttributeAccessIssue]
    assert isinstance(c.app.state.komga, Komga)  # pyright: ignore[reportAttributeAccessIssue]


def test_env_key_dropped_when_user_sets_address(tmp_path: Path) -> None:
    c = make_client(
        tmp_path,
        mode="real",
        secret_key=master_key(),
        env={"real": "search", "stash_api_key": "envsecret"},
    )
    r = c.put(
        "/api/connections/stash",
        json={"address": "http://stash2.local:9999"},
        headers=HDR,
    )
    assert r.status_code == 200
    assert r.json()["key"] == "missing"
    assert r.json()["key_locked"] is False
    assert "envsecret" not in r.text
    s = c.app.state.settings  # pyright: ignore[reportAttributeAccessIssue]
    assert s.stash_url == "http://stash2.local:9999"
    assert s.stash_api_key.get_secret_value() == ""


def _recording_transport(seen: list[httpx.Request]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": {}})

    return httpx.MockTransport(handler)


def test_connection_test_does_not_send_env_key_to_user_address(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    c = make_client(
        tmp_path,
        secret_key=master_key(),
        env={"stash_api_key": "envsecret"},
        transport=_recording_transport(seen),
    )
    r = c.put(
        "/api/connections/stash",
        json={"address": "http://other.local:9999"},
        headers=HDR,
    )
    assert r.status_code == 200
    t = c.post("/api/connections/stash/test", headers=HDR)
    assert t.status_code == 200
    assert len(seen) == 1
    assert seen[0].url.host == "other.local"
    assert "ApiKey" not in seen[0].headers
    assert "envsecret" not in t.text


def test_connection_test_env_key_with_env_address_unchanged(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    c = make_client(
        tmp_path,
        secret_key=master_key(),
        env={"stash_api_key": "envsecret", "stash_url": "http://stash.local:9999"},
        transport=_recording_transport(seen),
    )
    assert c.post("/api/connections/stash/test", headers=HDR).status_code == 200
    assert seen[0].url.host == "stash.local"
    assert seen[0].headers["ApiKey"] == "envsecret"


def test_connection_test_user_key_with_user_address_sent(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    c = make_client(
        tmp_path,
        secret_key=master_key(),
        env={"stash_api_key": "envsecret"},
        transport=_recording_transport(seen),
    )
    r = c.put(
        "/api/connections/stash",
        json={"address": "http://other.local:9999", "secret": "typedkey"},
        headers=HDR,
    )
    assert r.status_code == 200
    assert c.post("/api/connections/stash/test", headers=HDR).status_code == 200
    assert seen[0].headers["ApiKey"] == "typedkey"


def test_fixture_mode_keeps_none_clients(tmp_path: Path) -> None:
    c = make_client(tmp_path, secret_key=master_key())
    c.put(
        "/api/connections/stash",
        json={"address": "http://stash2.local:9999", "secret": "newkey"},
        headers=HDR,
    )
    assert c.app.state.stash is None  # pyright: ignore[reportAttributeAccessIssue]
    assert c.app.state.komga is None  # pyright: ignore[reportAttributeAccessIssue]


def test_swap_does_not_log_secret(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="pearlie")
    c = make_client(
        tmp_path, mode="real", secret_key=master_key(), env={"real": "search"}
    )
    _seed(c, "stash")
    r = c.put(
        "/api/connections/stash",
        json={"address": "http://stash2.local:9999", "secret": "topsecretvalue"},
        headers=HDR,
    )
    assert r.status_code == 200
    assert "topsecretvalue" not in caplog.text
