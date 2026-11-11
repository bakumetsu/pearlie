"""Player settings API tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def real_client(tmp_path):
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
def any_client(request, client, tmp_path):
    if request.param == "fixture":
        return client
    return real_client(tmp_path)


def test_get_default(any_client):
    r = any_client.get("/api/player-settings")
    assert r.status_code == 200
    assert r.json() == {"autoplay": False}


def test_put_true_then_get(any_client):
    r = any_client.put("/api/player-settings", json={"autoplay": True})
    assert r.status_code == 200
    assert r.json() == {"autoplay": True}
    r2 = any_client.get("/api/player-settings")
    assert r2.status_code == 200
    assert r2.json() == {"autoplay": True}


def test_put_false_after_true(any_client):
    any_client.put("/api/player-settings", json={"autoplay": True})
    r = any_client.put("/api/player-settings", json={"autoplay": False})
    assert r.status_code == 200
    assert r.json() == {"autoplay": False}
    r2 = any_client.get("/api/player-settings")
    assert r2.json() == {"autoplay": False}


@pytest.mark.parametrize("body", [{"autoplay": "yes"}, {}, {"autoplay": 2}])
def test_put_invalid(any_client, body):
    r = any_client.put("/api/player-settings", json=body)
    assert r.status_code == 422


def test_fixture_stores_in_mem_not_db(client):
    client.put("/api/player-settings", json={"autoplay": True})
    assert client.app.state.player_settings_mem == {"player.autoplay": "1"}
    db: Path = client.app.state.settings.db_path
    if db.exists():
        conn = sqlite3.connect(db)
        rows = conn.execute(
            "SELECT key FROM settings WHERE key = 'player.autoplay'"
        ).fetchall()
        conn.close()
        assert rows == []


def test_real_writes_to_db(tmp_path):
    c = real_client(tmp_path)
    c.put("/api/player-settings", json={"autoplay": True})
    conn = sqlite3.connect(tmp_path / "p.db")
    row = conn.execute(
        "SELECT key, value FROM settings WHERE key = 'player.autoplay'"
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] == "player.autoplay"
    assert row[1] == "1"
