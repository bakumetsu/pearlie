"""Per-site credential fields: store, API, Test request and Danbooru auth (mocked HTTP)."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.sources.auth import DEFAULT_USER_AGENT, build_auth
from app.sources.base import SourceError
from app.sources.danbooru import Danbooru
from app.sources.throttle import Throttle

pytestmark = pytest.mark.no_default_origin

HDR: dict[str, str] = {"Origin": "http://testserver", "Content-Type": "application/json"}


def make_client(
    tmp_path: Path,
    key: str,
    handler: Any = None,
    env: dict[str, Any] | None = None,
) -> TestClient:
    kwargs: dict[str, Any] = {
        "mode": "real",
        "real": "search",
        "db_path": tmp_path / "p.db",
        "static_dir": tmp_path / "nostatic",
        "secret_key": key,
    }
    kwargs.update(env or {})
    app = create_app(Settings(**kwargs, _env_file=None))  # pyright: ignore[reportCallIssue]
    if handler is not None:
        app.state.connection_transport = httpx.MockTransport(handler)
    return TestClient(app, base_url="http://testserver")


def put(c: TestClient, name: str, body: dict[str, Any]) -> Any:
    return c.put(f"/api/connections/{name}", json=body, headers=HDR)


def capture() -> tuple[list[httpx.Request], Any]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    return seen, handler


def stored_rows(tmp_path: Path) -> dict[str, str]:
    db = sqlite3.connect(str(tmp_path / "p.db"))
    try:
        return dict(db.execute("SELECT key, value FROM settings").fetchall())
    finally:
        db.close()


# -- store round trip, encryption, never echoed --


def test_fields_listed_per_site(tmp_path: Path) -> None:
    c = make_client(tmp_path, Fernet.generate_key().decode())
    conns = {x["name"]: x for x in c.get("/api/connections").json()["connections"]}
    assert [f["id"] for f in conns["danbooru"]["fields"]] == ["login", "api_key"]
    assert [f["id"] for f in conns["gelbooru"]["fields"]] == ["user_id", "api_key"]
    assert [f["id"] for f in conns["rule34"]["fields"]] == ["user_id", "api_key"]
    assert [f["id"] for f in conns["nhentai"]["fields"]] == ["cookie", "user_agent"]
    assert all(f["state"] == "missing" for f in conns["danbooru"]["fields"])


def test_round_trip_encrypted_and_not_echoed(tmp_path: Path) -> None:
    c = make_client(tmp_path, Fernet.generate_key().decode())
    r = put(c, "danbooru", {"fields": {"login": "alice-login", "api_key": "k3y-VALUE"}})
    assert r.status_code == 200
    body = r.text + c.get("/api/connections").text
    assert "alice-login" not in body and "k3y-VALUE" not in body
    states = {f["id"]: f["state"] for f in r.json()["fields"]}
    assert states == {"login": "set", "api_key": "set"}
    rows = stored_rows(tmp_path)
    assert "alice-login" not in "".join(rows.values())
    assert "k3y-VALUE" not in "".join(rows.values())
    store = c.app.state.connection_store  # pyright: ignore[reportAttributeAccessIssue]
    assert store.field_values("danbooru") == {"login": "alice-login", "api_key": "k3y-VALUE"}


def test_clear_one_field_keeps_the_other(tmp_path: Path) -> None:
    c = make_client(tmp_path, Fernet.generate_key().decode())
    put(c, "nhentai", {"fields": {"cookie": "c=1", "user_agent": "UA/1"}})
    r = put(c, "nhentai", {"clear_fields": ["user_agent"]})
    states = {f["id"]: f["state"] for f in r.json()["fields"]}
    assert states == {"cookie": "set", "user_agent": "missing"}


def test_unknown_field_and_control_chars_rejected(tmp_path: Path) -> None:
    c = make_client(tmp_path, Fernet.generate_key().decode())
    assert put(c, "danbooru", {"fields": {"nope": "x"}}).status_code == 422
    assert put(c, "nhentai", {"fields": {"user_agent": "a\r\nX-Evil: 1"}}).status_code == 422


def test_env_locked_field_cannot_be_overwritten(tmp_path: Path) -> None:
    c = make_client(tmp_path, Fernet.generate_key().decode(), env={"gelbooru_user_id": "777"})
    r = put(c, "gelbooru", {"fields": {"user_id": "1"}})
    assert r.status_code == 409
    fields = {
        f["id"]: f for f in next(
            x for x in c.get("/api/connections").json()["connections"] if x["name"] == "gelbooru"
        )["fields"]
    }
    assert fields["user_id"]["locked"] is True and fields["user_id"]["state"] == "set"
    assert "777" not in c.get("/api/connections").text


# -- migration of the single secret --


def test_legacy_secret_maps_to_primary_field(tmp_path: Path) -> None:
    key = Fernet.generate_key().decode()
    c = make_client(tmp_path, key)
    # a row exactly as the single-secret version wrote it
    token = Fernet(key).encrypt(b"legacy-cookie").decode()
    store = c.app.state.connection_store  # pyright: ignore[reportAttributeAccessIssue]
    store._write("connections.nhentai.secret", token)
    store._write("connections.danbooru.secret", Fernet(key).encrypt(b"legacy-key").decode())
    conns = {x["name"]: x for x in c.get("/api/connections").json()["connections"]}
    assert conns["nhentai"]["key"] == "set"
    states = {f["id"]: f["state"] for f in conns["nhentai"]["fields"]}
    assert states == {"cookie": "set", "user_agent": "missing"}
    assert store.field_values("nhentai") == {"cookie": "legacy-cookie"}
    assert store.field_values("danbooru") == {"api_key": "legacy-key"}


def test_legacy_nhentai_cookie_still_sent_by_test(tmp_path: Path) -> None:
    key = Fernet.generate_key().decode()
    seen, handler = capture()
    c = make_client(tmp_path, key, handler)
    c.app.state.connection_store._write(  # pyright: ignore[reportAttributeAccessIssue]
        "connections.nhentai.secret", Fernet(key).encrypt(b"legacy-cookie").decode()
    )
    r = c.post("/api/connections/nhentai/test", headers=HDR)
    assert r.json() == {"ok": True, "message": "connected"}
    assert seen[0].headers["Cookie"] == "legacy-cookie"
    assert seen[0].headers["User-Agent"] == DEFAULT_USER_AGENT


# -- Test request per site --


def test_danbooru_test_sends_basic_auth_and_user_agent(tmp_path: Path) -> None:
    seen, handler = capture()
    c = make_client(tmp_path, Fernet.generate_key().decode(), handler)
    put(c, "danbooru", {"fields": {"login": "alice", "api_key": "abc"}})
    r = c.post("/api/connections/danbooru/test", headers=HDR)
    assert r.json()["ok"] is True
    req = seen[0]
    assert req.headers["Authorization"].startswith("Basic ")
    assert req.headers["User-Agent"] == DEFAULT_USER_AGENT
    assert "abc" not in str(req.url)


@pytest.mark.parametrize("site", ["gelbooru", "rule34"])
def test_booru_test_sends_user_id_and_api_key(tmp_path: Path, site: str) -> None:
    seen, handler = capture()
    c = make_client(tmp_path, Fernet.generate_key().decode(), handler)
    put(c, site, {"fields": {"user_id": "42", "api_key": "kk"}})
    assert c.post(f"/api/connections/{site}/test", headers=HDR).json()["ok"] is True
    assert seen[0].url.params["user_id"] == "42"
    assert seen[0].url.params["api_key"] == "kk"


def test_nhentai_test_sends_cookie_and_user_agent(tmp_path: Path) -> None:
    seen, handler = capture()
    c = make_client(tmp_path, Fernet.generate_key().decode(), handler)
    put(c, "nhentai", {"fields": {"cookie": "cf=1", "user_agent": "Mozilla/5.0 X"}})
    assert c.post("/api/connections/nhentai/test", headers=HDR).json()["ok"] is True
    assert seen[0].headers["Cookie"] == "cf=1"
    assert seen[0].headers["User-Agent"] == "Mozilla/5.0 X"


@pytest.mark.parametrize(
    ("site", "fields", "message"),
    [
        ("danbooru", {"login": "alice"}, "missing: API key"),
        ("danbooru", {"api_key": "k"}, "missing: Login"),
        ("gelbooru", {"user_id": "1"}, "missing: API key"),
        ("rule34", {"api_key": "k"}, "missing: User ID"),
    ],
)
def test_half_filled_pair_reports_missing_field(
    tmp_path: Path, site: str, fields: dict[str, str], message: str
) -> None:
    seen, handler = capture()
    c = make_client(tmp_path, Fernet.generate_key().decode(), handler)
    put(c, site, {"fields": fields})
    r = c.post(f"/api/connections/{site}/test", headers=HDR)
    assert r.json() == {"ok": False, "message": message}
    assert seen == []


@pytest.mark.parametrize("site", ["danbooru", "gelbooru", "rule34", "nhentai"])
def test_nothing_set_tests_anonymously(tmp_path: Path, site: str) -> None:
    seen, handler = capture()
    c = make_client(tmp_path, Fernet.generate_key().decode(), handler)
    assert c.post(f"/api/connections/{site}/test", headers=HDR).json()["ok"] is True
    req = seen[0]
    assert "Authorization" not in req.headers and "Cookie" not in req.headers
    assert "api_key" not in req.url.params


def test_no_credential_value_in_logs(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    seen, handler = capture()
    c = make_client(tmp_path, Fernet.generate_key().decode(), handler)
    put(c, "danbooru", {"fields": {"login": "zed-login", "api_key": "zed-secret"}})
    put(c, "nhentai", {"fields": {"cookie": "zed-cookie", "user_agent": "zed-agent"}})
    c.post("/api/connections/danbooru/test", headers=HDR)
    c.post("/api/connections/nhentai/test", headers=HDR)
    for word in ("zed-login", "zed-secret", "zed-cookie", "zed-agent"):
        assert word not in caplog.text


# -- adapter / build_auth --


def test_build_auth_pairs() -> None:
    assert build_auth("danbooru", {"login": "a", "api_key": "b"}).basic == ("a", "b")
    assert build_auth("danbooru", {}).basic is None
    assert build_auth("gelbooru", {"user_id": "1", "api_key": "k"}).params == {
        "user_id": "1",
        "api_key": "k",
    }
    assert build_auth("gelbooru", {"api_key": "k"}).params == {}


def danbooru_with(handler: Any, creds: dict[str, str]) -> Danbooru:
    return Danbooru(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        throttle=Throttle(0.0),
        credentials=lambda: creds,
    )


def test_danbooru_adapter_sends_login_and_key() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[])

    danbooru_with(handler, {"login": "alice", "api_key": "abc"}).search(["cat"])
    assert seen[0].headers["Authorization"].startswith("Basic ")
    assert "abc" not in str(seen[0].url)


def test_danbooru_adapter_anonymous_when_partial() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[])

    danbooru_with(handler, {"login": "alice"}).search(["cat"])
    assert "Authorization" not in seen[0].headers


def test_danbooru_error_message_has_no_credentials() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    with pytest.raises(SourceError) as exc:
        danbooru_with(handler, {"login": "alice", "api_key": "abc"}).search(["cat"])
    assert "abc" not in exc.value.message and "alice" not in exc.value.message
