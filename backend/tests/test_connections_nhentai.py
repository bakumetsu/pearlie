"""nhentai auth state in the connections list and the Test button's /user check (mocked)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.sources.nhentai import NHentai

pytestmark = pytest.mark.no_default_origin

HDR = {"Origin": "http://localhost", "Content-Type": "application/json"}
KEY = "nh-secret-key-123"


def _client(tmp_path: Path, user_status: int | None, mode: str = "real") -> TestClient:
    settings = Settings(
        mode=mode,
        real="search",
        db_path=tmp_path / "p.db",
        static_dir=tmp_path / "nostatic",
        secret_key="",
        nhentai_api_key=KEY,
        _env_file=None,  # pyright: ignore[reportCallIssue]
    )
    app = create_app(settings)
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if user_status is None:
            raise httpx.ConnectError("down")
        return httpx.Response(user_status, json={"email": "x@y.z"})

    src = app.state.sources["nhentai"]
    assert isinstance(src, NHentai)
    src._client = httpx.Client(transport=httpx.MockTransport(handler))  # pyright: ignore[reportPrivateUsage]
    app.state.seen = seen
    return TestClient(app, base_url="http://localhost")


def _nh(c: TestClient) -> dict:
    return next(
        x for x in c.get("/api/connections").json()["connections"] if x["name"] == "nhentai"
    )


def test_other_connections_have_no_auth(tmp_path: Path) -> None:
    c = _client(tmp_path, 200)
    for conn in c.get("/api/connections").json()["connections"]:
        if conn["name"] != "nhentai":
            assert conn["auth"] is None and conn["reason"] is None


def test_key_unchecked_before_test_then_ok(tmp_path: Path) -> None:
    c = _client(tmp_path, 200)
    assert _nh(c)["auth"] == "unchecked"
    r = c.post("/api/connections/nhentai/test", headers=HDR)
    assert r.json() == {"ok": True, "message": "Key works"}
    nh = _nh(c)
    assert nh["auth"] == "ok" and nh["reason"] is None
    assert KEY not in c.get("/api/connections").text
    assert c.app.state.seen[0].url.path == "/api/v2/user"  # pyright: ignore[reportAttributeAccessIssue]


def test_test_invalid_key(tmp_path: Path) -> None:
    c = _client(tmp_path, 401)
    r = c.post("/api/connections/nhentai/test", headers=HDR)
    assert r.json() == {"ok": False, "message": "Key rejected by nhentai"}
    nh = _nh(c)
    assert nh["auth"] == "failed" and nh["reason"] == "invalid"


def test_test_blocked_key(tmp_path: Path) -> None:
    c = _client(tmp_path, 403)
    r = c.post("/api/connections/nhentai/test", headers=HDR)
    assert r.json()["ok"] is False
    nh = _nh(c)
    assert nh["auth"] == "failed" and nh["reason"] == "blocked"


def test_test_unreachable_keeps_unchecked(tmp_path: Path) -> None:
    c = _client(tmp_path, None)
    r = c.post("/api/connections/nhentai/test", headers=HDR)
    assert r.json() == {"ok": False, "message": "nhentai unreachable"}
    assert _nh(c)["auth"] == "unchecked"


def test_fixture_mode_makes_no_site_call(tmp_path: Path) -> None:
    c = _client(tmp_path, 200, mode="fixture")
    r = c.post("/api/connections/nhentai/test", headers=HDR)
    assert r.json()["ok"] is False
    assert c.app.state.seen == []  # pyright: ignore[reportAttributeAccessIssue]
    assert _nh(c)["auth"] == "unchecked"


def test_no_key_is_guest(tmp_path: Path) -> None:
    settings = Settings(
        mode="fixture",
        db_path=tmp_path / "p.db",
        static_dir=tmp_path / "n",
        secret_key="",
        _env_file=None,  # pyright: ignore[reportCallIssue]
    )
    c = TestClient(create_app(settings), base_url="http://localhost")
    assert _nh(c)["auth"] == "guest"
