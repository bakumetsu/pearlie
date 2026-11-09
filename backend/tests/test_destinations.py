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
    resp = client.put("/api/destinations/nhentai", json={"folder": "/mnt/media/stash/rule34"})
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


# --- Danbooru source ---


def test_danbooru_source() -> None:
    d = Danbooru()
    assert d.target == "stash"
    assert "cdn.donmai.us" in d.file_hosts
    assert "danbooru.donmai.us" in d.file_hosts
