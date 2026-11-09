# T-56: fixture mode never builds or calls a real Stash or Komga client
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient


def _app(tmp_path: Path, mode: str):
    from app.config import Settings
    from app.main import create_app

    settings = Settings(
        mode=mode,
        real="search,library_komga,media_komga,library_stash,media_stash,jobs",
        komga_url="http://real-komga.invalid",
        stash_url="http://real-stash.invalid",
        stash_api_key="fake",
        komga_api_key="fake",
        db_path=tmp_path / "p.db",
        static_dir=tmp_path / "nostatic",
        _env_file=None,  # pyright: ignore
    )
    return create_app(settings)


def test_fixture_mode_builds_no_clients(tmp_path, monkeypatch):
    stash_cls = MagicMock()
    komga_cls = MagicMock()
    monkeypatch.setattr("app.main.StashClient", stash_cls)
    monkeypatch.setattr("app.main.Komga", komga_cls)

    app = _app(tmp_path, "fixture")

    stash_cls.assert_not_called()
    komga_cls.assert_not_called()
    assert app.state.stash is None
    assert app.state.komga is None


def test_fixture_routes_never_touch_clients(tmp_path, monkeypatch):
    stash_cls = MagicMock()
    komga_cls = MagicMock()
    monkeypatch.setattr("app.main.StashClient", stash_cls)
    monkeypatch.setattr("app.main.Komga", komga_cls)

    app = _app(tmp_path, "fixture")
    client = TestClient(app)

    resp = client.get("/api/library/stash/images")
    assert resp.status_code == 200
    images = resp.json()["items"]

    resp = client.get("/api/library/stash/videos")
    assert resp.status_code == 200
    videos = resp.json()["items"]

    resp = client.get("/api/library/komga/books")
    assert resp.status_code == 200

    resp = client.get("/api/search")
    assert resp.status_code == 200

    resp = client.get("/api/destinations")
    assert resp.status_code == 200

    resp = client.put(
        "/api/destinations/default",
        json={"folder": "/mnt/media/stash/Other"},
    )
    assert resp.status_code == 200

    # fetch thumbnails for first image and first video
    resp = client.get(images[0]["thumb_url"])
    assert resp.status_code == 200

    resp = client.get(videos[0]["thumb_url"])
    assert resp.status_code == 200

    assert stash_cls.return_value.mock_calls == []
    assert komga_cls.return_value.mock_calls == []
    stash_cls.assert_not_called()
    komga_cls.assert_not_called()


def test_fixture_thumb_url_differs_from_real(tmp_path, monkeypatch):
    stash_cls = MagicMock()
    komga_cls = MagicMock()
    monkeypatch.setattr("app.main.StashClient", stash_cls)
    monkeypatch.setattr("app.main.Komga", komga_cls)

    app = _app(tmp_path, "fixture")
    client = TestClient(app)

    images = client.get("/api/library/stash/images").json()["items"]
    item = images[0]

    thumb_url = item["thumb_url"]
    assert thumb_url.endswith("?src=fixture")
    assert thumb_url.startswith("/api/media/stash/images/")

    resp = client.get(thumb_url)
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "no-store"

    real_url = f"/api/media/stash/images/{item['id']}/thumb"
    assert real_url != thumb_url


def test_real_mode_still_builds_clients(tmp_path, monkeypatch):
    stash_cls = MagicMock()
    monkeypatch.setattr("app.main.StashClient", stash_cls)

    from app.config import Settings
    from app.main import create_app

    settings = Settings(
        mode="real",
        real="library_stash,media_stash",
        stash_url="http://real-stash.invalid",
        stash_api_key="fake",
        db_path=tmp_path / "p.db",
        static_dir=tmp_path / "nostatic",
        _env_file=None,  # pyright: ignore
    )
    create_app(settings)

    assert stash_cls.call_count == 1
