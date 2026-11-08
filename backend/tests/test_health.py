from typing import cast

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
        {"id": "danbooru", "state": "not_configured"},
        {"id": "gelbooru", "state": "not_configured"},
        {"id": "rule34", "state": "not_configured"},
        {"id": "nhentai", "state": "not_configured"},
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
