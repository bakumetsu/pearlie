"""Options API: thumbnail cache fields and clear route (D-17 part C)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def real_client(tmp_path: Path) -> TestClient:
    return TestClient(
        create_app(
            Settings(
                mode="real",
                real="search",
                db_path=tmp_path / "p.db",
                static_dir=tmp_path / "nostatic",
                _env_file=None,  # pyright: ignore[reportCallIssue]
            )
        )
    )


@pytest.fixture(params=["fixture", "real"])
def any_client(request, client, tmp_path: Path) -> TestClient:
    if request.param == "fixture":
        return client
    return real_client(tmp_path)


def test_defaults(any_client: TestClient) -> None:
    info = any_client.get("/api/options").json()["thumb_cache"]
    assert info["max_mb"] == 1024
    assert info["used_mb"] == 0.0
    assert info["files"] == 0


@pytest.mark.parametrize("value", [49, 20481, 0, -1, 100.5, "100", True])
def test_max_mb_rejects_bad_values(any_client: TestClient, value: object) -> None:
    r = any_client.put("/api/options", json={"thumb_cache_max_mb": value})
    assert r.status_code == 422
    assert any_client.get("/api/options").json()["thumb_cache"]["max_mb"] == 1024


@pytest.mark.parametrize("value", [50, 2048, 20480])
def test_max_mb_saved(any_client: TestClient, value: int) -> None:
    r = any_client.put("/api/options", json={"thumb_cache_max_mb": value})
    assert r.status_code == 200
    assert r.json()["thumb_cache"]["max_mb"] == value
    assert any_client.get("/api/options").json()["thumb_cache"]["max_mb"] == value


def test_clear_fixture_is_noop(client: TestClient) -> None:
    r = client.post("/api/thumb-cache/clear")
    assert r.status_code == 200
    assert r.json() == {"freed_mb": 0.0}


def test_real_size_and_clear(tmp_path: Path) -> None:
    c = real_client(tmp_path)
    cache = c.app.state.thumb_cache  # type: ignore[attr-defined]
    png = b"\x89PNG\r\n\x1a\n" + b"\0" * (1024 * 1024)
    for i in range(3):
        assert cache.put("danbooru", str(i), png)
    info = c.get("/api/options").json()["thumb_cache"]
    assert info["files"] == 3
    assert info["available"] is True
    assert c.post("/api/thumb-cache/clear").json()["freed_mb"] >= 3.0
    assert c.get("/api/options").json()["thumb_cache"]["files"] == 0


def test_cap_survives_restart(tmp_path: Path) -> None:
    c = real_client(tmp_path)
    assert c.put("/api/options", json={"thumb_cache_max_mb": 300}).status_code == 200
    c2 = real_client(tmp_path)
    assert c2.get("/api/options").json()["thumb_cache"]["max_mb"] == 300
