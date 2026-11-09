"""View settings API tests."""

from __future__ import annotations

import sqlite3

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


def test_get_defaults(any_client):
    r = any_client.get("/api/view-settings")
    assert r.status_code == 200
    sources = r.json()["sources"]
    assert set(sources) == {
        "stash_images",
        "stash_videos",
        "komga_series",
        "komga_books",
        "danbooru",
        "gelbooru",
        "rule34",
        "nhentai",
    }
    assert sources["stash_images"] == {
        "mode": "grid",
        "per_page": 60,
        "zoom": 3,
        "per_page_options": [20, 40, 60, 100, 200],
        "per_page_max": 200,
    }
    assert sources["gelbooru"]["per_page_options"] == [20, 40, 60, 100]
    assert sources["gelbooru"]["per_page_max"] == 100
    assert sources["nhentai"]["per_page"] == 25
    assert sources["nhentai"]["per_page_options"] == [25]
    assert sources["nhentai"]["per_page_max"] == 25


def test_put_roundtrip(any_client):
    r = any_client.put(
        "/api/view-settings/stash_images",
        json={"mode": "masonry", "per_page": 37, "zoom": 5},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "masonry"
    assert body["per_page"] == 37
    assert body["zoom"] == 5
    assert body["per_page_max"] == 200
    r2 = any_client.get("/api/view-settings")
    sources = r2.json()["sources"]
    assert sources["stash_images"]["mode"] == "masonry"
    assert sources["stash_images"]["per_page"] == 37
    assert sources["stash_images"]["zoom"] == 5
    assert sources["danbooru"]["mode"] == "grid"
    assert sources["danbooru"]["per_page"] == 60
    assert sources["danbooru"]["zoom"] == 3


@pytest.mark.parametrize(
    "source,body,field,message",
    [
        (
            "stash_images",
            {"mode": "grid", "per_page": 0, "zoom": 3},
            "per_page",
            "per_page must be 1 to 200",
        ),
        (
            "stash_images",
            {"mode": "grid", "per_page": 201, "zoom": 3},
            "per_page",
            "per_page must be 1 to 200",
        ),
        (
            "gelbooru",
            {"mode": "grid", "per_page": 101, "zoom": 3},
            "per_page",
            "per_page must be 1 to 100",
        ),
        (
            "nhentai",
            {"mode": "grid", "per_page": 26, "zoom": 3},
            "per_page",
            "per_page must be 1 to 25",
        ),
        ("danbooru", {"mode": "cards", "per_page": 60, "zoom": 3}, "mode", None),
        ("danbooru", {"mode": "grid", "per_page": 60, "zoom": 6}, "zoom", None),
        ("danbooru", {"mode": "grid", "per_page": 60, "zoom": 0}, "zoom", None),
        ("nope", {"mode": "grid", "per_page": 60, "zoom": 3}, "source", None),
    ],
)
def test_put_invalid(any_client, source, body, field, message):
    r = any_client.put(f"/api/view-settings/{source}", json=body)
    assert r.status_code == 422
    if message is not None:
        assert message in r.text


@pytest.mark.parametrize(
    "source,cap",
    [
        ("stash_images", 200),
        ("gelbooru", 100),
        ("rule34", 100),
        ("nhentai", 25),
        ("komga_books", 200),
    ],
)
def test_cap_accepted(any_client, source, cap):
    r = any_client.put(
        f"/api/view-settings/{source}",
        json={"mode": "list", "per_page": cap, "zoom": 1},
    )
    assert r.status_code == 200
    assert r.json()["per_page"] == cap
    r2 = any_client.put(
        f"/api/view-settings/{source}",
        json={"mode": "list", "per_page": 1, "zoom": 1},
    )
    assert r2.status_code == 200


def test_real_bad_stored_row_falls_back(tmp_path):
    c = real_client(tmp_path)
    conn = sqlite3.connect(tmp_path / "p.db")
    conn.execute("INSERT INTO settings (key, value) VALUES ('view.danbooru', 'not json')")
    conn.execute(
        "INSERT INTO settings (key, value) VALUES "
        '(\'view.gelbooru\', \'{"mode": "grid", "per_page": 5000, "zoom": 3}\')'
    )
    conn.commit()
    conn.close()
    r = c.get("/api/view-settings")
    sources = r.json()["sources"]
    assert sources["danbooru"]["mode"] == "grid"
    assert sources["danbooru"]["per_page"] == 60
    assert sources["danbooru"]["zoom"] == 3
    assert sources["gelbooru"]["mode"] == "grid"
    assert sources["gelbooru"]["per_page"] == 60
    assert sources["gelbooru"]["zoom"] == 3


def test_real_persists_across_apps(tmp_path):
    c1 = real_client(tmp_path)
    c1.put(
        "/api/view-settings/stash_videos",
        json={"mode": "wall", "per_page": 100, "zoom": 2},
    )
    c2 = real_client(tmp_path)
    r = c2.get("/api/view-settings")
    sources = r.json()["sources"]
    assert sources["stash_videos"]["mode"] == "wall"
    assert sources["stash_videos"]["per_page"] == 100


def test_real_non_object_stored_rows_fall_back(tmp_path):
    c = real_client(tmp_path)
    conn = sqlite3.connect(tmp_path / "p.db")
    conn.execute("INSERT INTO settings (key, value) VALUES ('view.danbooru', '[1]')")
    conn.execute("INSERT INTO settings (key, value) VALUES ('view.gelbooru', '\"x\"')")
    conn.execute("INSERT INTO settings (key, value) VALUES ('view.rule34', '5')")
    conn.commit()
    conn.close()
    r = c.get("/api/view-settings")
    assert r.status_code == 200
    sources = r.json()["sources"]
    assert sources["danbooru"]["mode"] == "grid"
    assert sources["danbooru"]["per_page"] == 60
    assert sources["danbooru"]["zoom"] == 3
    assert sources["gelbooru"]["mode"] == "grid"
    assert sources["gelbooru"]["per_page"] == 60
    assert sources["gelbooru"]["zoom"] == 3
    assert sources["rule34"]["mode"] == "grid"
    assert sources["rule34"]["per_page"] == 60
    assert sources["rule34"]["zoom"] == 3
