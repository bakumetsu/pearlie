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
    3: {
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
            "placement",
        ],
        "rules": ["id", "list", "pattern", "scope", "enabled", "created_at", "target"],
        "saved_items": ["id", "source", "post_id", "md5", "target", "image_id", "created_at"],
        "settings": ["key", "value"],
        "site_icons": ["site", "data", "mime", "fetched_at"],
    },
    4: {
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
            "placement",
            "pages_done",
            "pages_total",
            "eta_s",
        ],
        "rules": ["id", "list", "pattern", "scope", "enabled", "created_at", "target"],
        "saved_items": ["id", "source", "post_id", "md5", "target", "image_id", "created_at"],
        "settings": ["key", "value"],
        "site_icons": ["site", "data", "mime", "fetched_at"],
    },
    5: {
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
            "placement",
            "pages_done",
            "pages_total",
            "eta_s",
            "scan_library_id",
            "scan_name",
            "scan_due_at",
        ],
        "rules": ["id", "list", "pattern", "scope", "enabled", "created_at", "target"],
        "saved_items": ["id", "source", "post_id", "md5", "target", "image_id", "created_at"],
        "settings": ["key", "value"],
        "site_icons": ["site", "data", "mime", "fetched_at"],
    },
    6: {
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
            "placement",
            "pages_done",
            "pages_total",
            "eta_s",
            "scan_library_id",
            "scan_name",
            "scan_due_at",
        ],
        "rules": ["id", "list", "pattern", "scope", "enabled", "created_at", "target"],
        "saved_items": [
            "id",
            "source",
            "post_id",
            "md5",
            "target",
            "image_id",
            "created_at",
            "kind",
        ],
        "settings": ["key", "value"],
        "site_icons": ["site", "data", "mime", "fetched_at"],
    },
    7: {
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
            "placement",
            "pages_done",
            "pages_total",
            "eta_s",
            "scan_library_id",
            "scan_name",
            "scan_due_at",
        ],
        "rules": ["id", "list", "pattern", "scope", "enabled", "created_at", "target"],
        "saved_items": [
            "id",
            "source",
            "post_id",
            "md5",
            "target",
            "image_id",
            "created_at",
            "library_id",
            "kind",
        ],
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


def _make_pre_v3(path: Path) -> Path:
    """Create a v2-era database with saved_items, rules, and jobs."""
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE saved_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            post_id TEXT NOT NULL,
            md5 TEXT NOT NULL,
            target TEXT NOT NULL DEFAULT 'stash',
            created_at TEXT
        );
        CREATE TABLE rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            list TEXT NOT NULL,
            pattern TEXT NOT NULL,
            scope TEXT NOT NULL DEFAULT 'all',
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT
        );
        CREATE TABLE jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            post_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            created_at TEXT
        );
        CREATE UNIQUE INDEX idx_jobs_active
            ON jobs (source, post_id)
            WHERE status IN ('queued', 'running');
        """
    )
    cur.execute(
        "INSERT INTO saved_items (source, post_id, md5, target, created_at) VALUES (?, ?, ?, ?, ?)",
        ("reddit", "abc123", "d41d8cd98f", "stash", "2025-01-01T00:00:00"),
    )
    cur.execute(
        "INSERT INTO rules (list, pattern, scope, enabled, created_at) VALUES (?, ?, ?, ?, ?)",
        ("mylist", "*.jpg", "all", 1, "2025-01-01T00:00:00"),
    )
    cur.execute(
        "INSERT INTO jobs (source, post_id, status, created_at) VALUES (?, ?, ?, ?)",
        ("reddit", "abc123", "queued", "2025-01-01T00:00:00"),
    )
    cur.execute("PRAGMA user_version = 2")
    conn.commit()
    conn.close()
    return path


def test_pre_v3_db_migrates_and_keeps_rows(tmp_path: Path):
    db = _make_pre_v3(tmp_path / "old.db")

    init_db(db)

    conn = sqlite3.connect(db)
    cur = conn.cursor()

    # Original row data preserved
    row = cur.execute("SELECT source, post_id, md5, target, created_at FROM saved_items").fetchone()
    assert row == ("reddit", "abc123", "d41d8cd98f", "stash", "2025-01-01T00:00:00")

    # saved_items gained image_id (None) and kind ('image')
    row = cur.execute("SELECT image_id, kind FROM saved_items WHERE id = 1").fetchone()
    assert row[0] is None
    assert row[1] == "image"

    # rules gained target (None)
    row = cur.execute("SELECT target FROM rules WHERE id = 1").fetchone()
    assert row[0] is None

    # jobs columns include dest_path and attempts
    cols = [r[1] for r in cur.execute("PRAGMA table_info(jobs)").fetchall()]
    assert "dest_path" in cols
    assert "attempts" in cols

    # idx_jobs_active now references scan_wait
    sql = cur.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = 'idx_jobs_active'"
    ).fetchone()
    assert sql is not None
    assert "scan_wait" in sql[0]

    # schema_version bumped to current
    assert schema_version(db) == SCHEMA_VERSION

    conn.close()


def test_init_db_twice_is_idempotent(tmp_path: Path):
    db = _make_pre_v3(tmp_path / "old.db")

    init_db(db)
    init_db(db)

    conn = sqlite3.connect(db)
    cur = conn.cursor()
    assert cur.execute("SELECT COUNT(*) FROM saved_items").fetchone()[0] == 1
    assert cur.execute("SELECT COUNT(*) FROM rules").fetchone()[0] == 1
    assert cur.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 1
    conn.close()
