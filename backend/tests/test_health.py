from pathlib import Path
from typing import cast

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import Settings
from app.main import create_app


def test_health_ok(client: TestClient) -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert body["stash"] == {"state": "not_configured", "version": None}
    assert body["komga"] == {"state": "not_configured", "version": None}
    assert body["mounts"] == []
    assert body["sites"] == [
        {"id": "danbooru", "state": "ok"},
        {"id": "gelbooru", "state": "ok"},
        {"id": "rule34", "state": "ok"},
        {"id": "nhentai", "state": "ok"},
    ]


def test_health_degraded(settings: Settings, client: TestClient, tmp_path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x")
    bad = Settings(
        mode="fixture",
        db_path=tmp_path / "file" / "x.db",
        static_dir=tmp_path / "nostatic",
        _env_file=None,  # pyright: ignore[reportCallIssue]
    )
    cast(FastAPI, client.app).state.settings = bad
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["db"] == "error"


def test_health_no_secrets(settings: Settings) -> None:
    settings.stash_api_key = SecretStr("TOP-SECRET-KEY")
    c = TestClient(create_app(settings))
    resp = c.get("/api/health")
    assert "TOP-SECRET-KEY" not in resp.text


def test_api_404(client: TestClient) -> None:
    resp = client.get("/api/nope")
    assert resp.status_code == 404


def _real_client(tmp_path: Path, handler: httpx.MockTransport, **env: object) -> TestClient:
    settings = Settings(
        mode="fixture",
        db_path=tmp_path / "p.db",
        static_dir=tmp_path / "nostatic",
        **env,  # pyright: ignore[reportArgumentType]
        _env_file=None,  # pyright: ignore[reportCallIssue]
    )
    app = create_app(settings)
    app.state.connection_transport = handler
    return TestClient(app)


def test_health_probes_configured_services(tmp_path: Path) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        if request.url.host == "stash.local":
            return httpx.Response(200, json={"data": {"version": {"version": "v0.27.2"}}})
        return httpx.Response(401)

    c = _real_client(
        tmp_path,
        httpx.MockTransport(handler),
        stash_url="http://stash.local:9999",
        stash_api_key=SecretStr("TOP-SECRET-KEY"),
        komga_url="http://komga.local:25600",
        komga_api_key=SecretStr("KOMGA-SECRET"),
    )
    body = c.get("/api/health").json()
    assert body["stash"] == {"state": "ok", "version": "v0.27.2"}
    assert body["komga"] == {"state": "down", "version": None}
    assert {s["state"] for s in body["sites"]} == {"ok"}
    assert "stash.local" in calls
    assert all(site_host not in calls for site_host in ("danbooru.donmai.us", "gelbooru.com"))
    raw = c.get("/api/health").text
    assert "TOP-SECRET-KEY" not in raw and "KOMGA-SECRET" not in raw
    assert "stash.local" not in raw and "komga.local" not in raw


def test_health_probe_is_cached(tmp_path: Path) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        return httpx.Response(200, json={"data": {"version": {"version": "v1"}}})

    c = _real_client(tmp_path, httpx.MockTransport(handler), stash_url="http://stash.local:9999")
    c.get("/api/health")
    c.get("/api/health")
    assert calls == ["stash.local"]
