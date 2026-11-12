"""Tests for destination validation, storage, and API."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.db import connect, init_db
from app.sources.danbooru import Danbooru
from app.targets import destinations
from app.targets.destinations import DestinationError

LIBRARIES: list[str] = [
    "/mnt/media/stash/rule34",
    "/mnt/media/stash/rule34video",
    "/mnt/media/stash/Other",
]


# --- validate_folder ---


def test_validate_folder_accepts_library_root() -> None:
    assert (
        destinations.validate_folder("/mnt/media/stash/rule34", LIBRARIES)
        == "/mnt/media/stash/rule34"
    )


def test_validate_folder_accepts_subfolder() -> None:
    assert (
        destinations.validate_folder(
            "/mnt/media/stash/rule34/sub", ["/mnt/media/stash/rule34"]
        )
        == "/mnt/media/stash/rule34/sub"
    )


def test_validate_folder_normalizes_trailing_slash() -> None:
    assert (
        destinations.validate_folder("/mnt/media/stash/rule34/", ["/mnt/media/stash/rule34"])
        == "/mnt/media/stash/rule34"
    )


def test_validate_folder_rejects_outside_library() -> None:
    with pytest.raises(DestinationError) as exc:
        destinations.validate_folder("/mnt/media/stash/other", LIBRARIES)
    assert exc.value.code == "outside_library"


def test_validate_folder_rejects_dotdot() -> None:
    with pytest.raises(DestinationError) as exc:
        destinations.validate_folder("/mnt/media/stash/rule34/../x", LIBRARIES)
    assert exc.value.code == "invalid"


def test_validate_folder_rejects_relative() -> None:
    with pytest.raises(DestinationError) as exc:
        destinations.validate_folder("rule34", LIBRARIES)
    assert exc.value.code == "invalid"


def test_validate_folder_rejects_prefix_lookalike() -> None:
    with pytest.raises(DestinationError) as exc:
        destinations.validate_folder("/mnt/media/stash/rule34evil", LIBRARIES)
    assert exc.value.code == "outside_library"


# --- validate_folder with prefix map ---


def test_validate_folder_with_prefix_map() -> None:
    result = destinations.validate_folder(
        "/data/rule34", ["/mnt/media/stash/rule34"], "/data", "/mnt/media/stash"
    )
    assert result == "/data/rule34"
    with pytest.raises(DestinationError):
        destinations.validate_folder(
            "/mnt/media/stash/rule34", ["/mnt/media/stash/rule34"], "/data", "/mnt/media/stash"
        )


# --- to_stash_path ---


def test_to_stash_path_identity_when_prefix_empty() -> None:
    path = "/mnt/media/stash/rule34"
    assert destinations.to_stash_path(path, "", "") == path


# --- DB layer ---


def test_db_destination_lifecycle(tmp_path: Path) -> None:
    db = tmp_path / "p.db"
    init_db(db)

    # upsert: two calls, last wins
    destinations.set_destination(db, "danbooru", "/mnt/media/stash/rule34")
    destinations.set_destination(db, "danbooru", "/mnt/media/stash/rule34video")
    assert destinations.list_destinations(db) == [
        {"site": "danbooru", "folder": "/mnt/media/stash/rule34video"}
    ]

    # list_destinations sorted by site
    destinations.set_destination(db, "rule34", "/mnt/media/stash/Other")
    assert [d["site"] for d in destinations.list_destinations(db)] == ["danbooru", "rule34"]

    # delete_destination returns True then False
    assert destinations.delete_destination(db, "danbooru") is True
    assert destinations.delete_destination(db, "danbooru") is False

    # get_default inserts fallback on first call
    assert destinations.get_default(db, "/mnt/media/stash/Other") == "/mnt/media/stash/Other"
    # set_default then get_default returns stored value
    destinations.set_default(db, "/mnt/media/stash/rule34video")
    assert destinations.get_default(db, "/mnt/media/stash/Other") == "/mnt/media/stash/rule34video"

    # resolve: site folder if set, else default
    destinations.set_destination(db, "danbooru", "/mnt/media/stash/rule34")
    default = "/mnt/media/stash/rule34video"
    assert destinations.resolve(db, "danbooru", "/mnt/media/stash/Other") == (
        "/mnt/media/stash/rule34"
    )
    assert destinations.resolve(db, "unknown", "/mnt/media/stash/Other") == default


# --- Migration ---


def test_migration_adds_image_id_column(tmp_path: Path) -> None:
    db = tmp_path / "old.db"
    old = sqlite3.connect(db)
    old.execute(
        "CREATE TABLE saved_items ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "source TEXT NOT NULL, "
        "post_id TEXT NOT NULL, "
        "md5 TEXT NOT NULL, "
        "target TEXT NOT NULL, "
        "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, "
        "UNIQUE(source, post_id)"
        ")"
    )
    old.commit()
    old.close()

    init_db(db)
    conn = connect(db)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(saved_items)")]
    conn.close()
    assert "image_id" in cols


# --- API ---


def test_api_get_destinations(client) -> None:
    resp = client.get("/api/destinations")
    assert resp.status_code == 200
    body = resp.json()
    assert body["default_folder"] == "/mnt/media/stash/Other"
    assert body["items"] == []


def test_api_put_destination(client) -> None:
    resp = client.put("/api/destinations/danbooru", json={"folder": "/mnt/media/stash/rule34"})
    assert resp.status_code == 200
    assert resp.json()["items"] == [{"site": "danbooru", "folder": "/mnt/media/stash/rule34"}]


def test_api_put_rejects_outside_library(client) -> None:
    resp = client.put("/api/destinations/danbooru", json={"folder": "/etc"})
    assert resp.status_code == 400
    assert resp.json()["code"] == "outside_library"


def test_api_put_rejects_dotdot(client) -> None:
    resp = client.put(
        "/api/destinations/danbooru",
        json={"folder": "/mnt/media/stash/rule34/../../etc"},
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "invalid"


def test_api_put_rejects_unknown_site(client) -> None:
    resp = client.put("/api/destinations/nosuchsite", json={"folder": "/mnt/media/stash/rule34"})
    assert resp.status_code == 422
    assert resp.json()["code"] == "invalid"


def test_api_put_default(client) -> None:
    resp = client.put(
        "/api/destinations/default", json={"folder": "/mnt/media/stash/rule34video"}
    )
    assert resp.status_code == 200
    assert resp.json()["default_folder"] == "/mnt/media/stash/rule34video"


def test_api_delete_destination(client) -> None:
    client.put("/api/destinations/danbooru", json={"folder": "/mnt/media/stash/rule34"})
    resp = client.delete("/api/destinations/danbooru")
    assert resp.status_code == 200
    assert resp.json()["items"] == []
    resp2 = client.delete("/api/destinations/danbooru")
    assert resp2.status_code == 404


def test_api_get_destinations_lists_hints(client) -> None:
    body = client.get("/api/destinations").json()
    assert body["library_paths"] == [
        "/mnt/media/stash/rule34",
        "/mnt/media/stash/rule34video",
        "/mnt/media/stash/Other",
    ]
    assert body["library_error"] is None
    assert body["sites"]
    assert "danbooru" in body["sites"]
    assert body["prefix_pearlie"] == ""


def test_api_get_destinations_survives_missing_stash(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import create_app

    cfg = Settings(
        mode="real",
        db_path=tmp_path / "p.db",
        static_dir=tmp_path / "nostatic",
        _env_file=None,  # pyright: ignore[reportCallIssue]
    )
    with TestClient(create_app(cfg)) as c:
        resp = c.get("/api/destinations")
    assert resp.status_code == 200
    body = resp.json()
    assert body["library_paths"] == []
    assert body["library_error"]


def test_api_put_applies_prefix_map(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import create_app

    cfg = Settings(
        mode="fixture",
        db_path=tmp_path / "p.db",
        static_dir=tmp_path / "nostatic",
        stash_path_prefix_pearlie="/data",
        stash_path_prefix_stash="/mnt/media/stash",
        _env_file=None,  # pyright: ignore[reportCallIssue]
    )
    c = TestClient(create_app(cfg))
    ok = c.put("/api/destinations/default", json={"folder": "/data/rule34"})
    assert ok.status_code == 200
    body = ok.json()
    assert body["default_folder"] == "/data/rule34"
    assert body["prefix_pearlie"] == "/data"
    assert body["prefix_stash"] == "/mnt/media/stash"
    bad = c.put("/api/destinations/default", json={"folder": "/mnt/media/stash/rule34"})
    assert bad.status_code == 400
    assert bad.json()["code"] == "outside_library"


def test_mapping_override_wins_and_reset_falls_back(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import create_app

    cfg = Settings(
        mode="fixture",
        db_path=tmp_path / "p.db",
        static_dir=tmp_path / "nostatic",
        stash_path_prefix_pearlie="/env",
        stash_path_prefix_stash="/mnt/media/stash",
        _env_file=None,  # pyright: ignore[reportCallIssue]
    )
    c = TestClient(create_app(cfg))
    first = c.get("/api/destinations").json()
    assert first["prefix_pearlie"] == "/env"
    assert first["prefix_from_env"] is True
    saved = c.put(
        "/api/destinations/mapping",
        json={"prefix_pearlie": "/data/", "prefix_stash": "/mnt/media/stash"},
    )
    assert saved.status_code == 200
    assert saved.json()["prefix_pearlie"] == "/data"
    assert saved.json()["prefix_from_env"] is False
    assert c.put("/api/destinations/default", json={"folder": "/data/rule34"}).status_code == 200
    assert c.put("/api/destinations/default", json={"folder": "/env/rule34"}).status_code == 400
    back = c.delete("/api/destinations/mapping").json()
    assert back["prefix_pearlie"] == "/env"
    assert back["prefix_from_env"] is True


def test_mapping_validation(client) -> None:
    url = "/api/destinations/mapping"
    one = client.put(url, json={"prefix_pearlie": "/data", "prefix_stash": ""})
    assert one.status_code == 422
    rel = client.put(url, json={"prefix_pearlie": "data", "prefix_stash": "/x"})
    assert rel.status_code == 422
    empty = client.put(url, json={"prefix_pearlie": "", "prefix_stash": ""})
    assert empty.status_code == 200
    assert empty.json()["prefix_pearlie"] == ""
    assert empty.json()["prefix_from_env"] is False


# --- Danbooru source ---


def test_danbooru_source() -> None:
    d = Danbooru()
    assert d.target == "stash"
    assert "cdn.donmai.us" in d.file_hosts
    assert "danbooru.donmai.us" in d.file_hosts


def test_api_komga_site_validates_against_komga_roots(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import create_app

    class FakeKomga:
        def list_libraries(self) -> list[dict]:
            return [{"id": "L1", "root": "/mnt/komga/doujin"}]

    cfg = Settings(
        mode="real",
        db_path=tmp_path / "p.db",
        static_dir=tmp_path / "nostatic",
        _env_file=None,  # pyright: ignore[reportCallIssue]
    )
    app = create_app(cfg)
    app.state.komga = FakeKomga()
    with TestClient(app) as c:
        body = c.get("/api/destinations").json()
        assert body["komga_sites"] == ["nhentai"]
        assert body["komga_library_paths"] == ["/mnt/komga/doujin"]
        bad = c.put("/api/destinations/nhentai", json={"folder": "/mnt/stash/x"})
        assert bad.status_code == 400
        assert "Komga" in bad.json()["message"]
        ok = c.put("/api/destinations/nhentai", json={"folder": "/mnt/komga/doujin/in"})
        assert ok.status_code == 200
        assert ok.json()["items"] == [{"site": "nhentai", "folder": "/mnt/komga/doujin/in"}]
        assert c.delete("/api/destinations/nhentai").status_code == 200
