import sqlite3
from pathlib import Path

import pytest

from app.db import SCHEMA_VERSION, connect, db_reachable, init_db, schema_version

SNAPSHOTS = {
    1: {
        "destinations": ["site", "folder", "created_at"],
        "jobs": [
            "id",
            "source",
            "post_id",
            "status",
            "error",
            "error_code",
            "target",
            "title",
            "thumb_url",
            "post_json",
            "notices",
            "library_ref_id",
            "attempts",
            "restarts",
            "started_at",
            "finished_at",
            "created_at",
            "updated_at",
        ],
        "rules": ["id", "list", "pattern", "scope", "enabled", "created_at", "target"],
        "saved_items": ["id", "source", "post_id", "md5", "target", "image_id", "created_at"],
        "settings": ["key", "value"],
        "site_icons": ["site", "data", "mime", "fetched_at"],
    },
    2: {
        "destinations": ["site", "folder", "created_at"],
        "jobs": [
            "id",
            "source",
            "post_id",
            "status",
            "error",
            "error_code",
            "target",
            "title",
            "thumb_url",
            "post_json",
            "notices",
            "library_ref_id",
            "dest_path",
            "attempts",
            "restarts",
            "started_at",
            "finished_at",
            "created_at",
            "updated_at",
        ],
        "rules": ["id", "list", "pattern", "scope", "enabled", "created_at", "target"],
        "saved_items": ["id", "source", "post_id", "md5", "target", "image_id", "created_at"],
        "settings": ["key", "value"],
        "site_icons": ["site", "data", "mime", "fetched_at"],
    },
}


def test_init_db_creates_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    init_db(db_path)
    conn = connect(db_path)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "jobs" in tables
    assert "saved_items" in tables
    assert "rules" in tables


def test_saved_items_unique(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    init_db(db_path)
    conn = connect(db_path)
    conn.execute(
        "INSERT INTO saved_items (source, post_id, md5, target) VALUES (?, ?, ?, ?)",
        ("danbooru", "123", "abc123", "/data/123.jpg"),
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO saved_items (source, post_id, md5, target) VALUES (?, ?, ?, ?)",
            ("danbooru", "123", "def456", "/data/other.jpg"),
        )
        conn.commit()
    conn.close()


def test_db_reachable_good(tmp_path: Path) -> None:
    db_path = tmp_path / "good.db"
    init_db(db_path)
    assert db_reachable(db_path) is True


def test_db_reachable_bad(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x")
    bad_path = tmp_path / "file" / "x.db"
    assert db_reachable(bad_path) is False


def test_init_db_stamps_user_version(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    init_db(db_path)
    assert schema_version(db_path) == SCHEMA_VERSION


def test_schema_snapshot_needs_version_bump(tmp_path: Path) -> None:
    # Fails when a column or table changes without a SCHEMA_VERSION bump.
    db_path = tmp_path / "test.db"
    init_db(db_path)
    conn = connect(db_path)
    tables = sorted(
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    )
    snapshot = {t: [row[1] for row in conn.execute(f"PRAGMA table_info({t})")] for t in tables}
    conn.close()
    expected = SNAPSHOTS[SCHEMA_VERSION]
    assert snapshot == expected, "schema changed: bump SCHEMA_VERSION and add a snapshot"


def test_v1_jobs_table_gains_dest_path(tmp_path: Path) -> None:
    db_path = tmp_path / "old.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL, "
        "post_id TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued', error TEXT, "
        "library_ref_id TEXT)"
    )
    conn.execute("INSERT INTO jobs (source, post_id) VALUES ('nhentai', '1')")
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()
    init_db(db_path)
    conn = connect(db_path)
    row = conn.execute("SELECT dest_path FROM jobs").fetchone()
    conn.close()
    assert row["dest_path"] is None
    assert schema_version(db_path) == SCHEMA_VERSION
