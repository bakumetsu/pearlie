import sqlite3
from pathlib import Path

# Bump on every new column or table (test_db.py snapshot guard fails otherwise).
SCHEMA_VERSION = 2

SCHEMA = """\
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    post_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    error TEXT,
    error_code TEXT,
    target TEXT NOT NULL DEFAULT 'stash',
    title TEXT NOT NULL DEFAULT '',
    thumb_url TEXT NOT NULL DEFAULT '',
    post_json TEXT,
    notices TEXT NOT NULL DEFAULT '[]',
    library_ref_id TEXT,
    dest_path TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    restarts INTEGER NOT NULL DEFAULT 0,
    started_at TEXT,
    finished_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_active
    ON jobs (source, post_id) WHERE status IN ('queued', 'running');
CREATE TABLE IF NOT EXISTS saved_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    post_id TEXT NOT NULL,
    md5 TEXT NOT NULL,
    target TEXT NOT NULL,
    image_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source, post_id)
);
CREATE INDEX IF NOT EXISTS idx_saved_items_md5 ON saved_items (md5);
CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    list TEXT NOT NULL,
    pattern TEXT NOT NULL,
    scope TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS destinations (
    site TEXT PRIMARY KEY,
    folder TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS site_icons (
    site TEXT PRIMARY KEY,
    data BLOB,
    mime TEXT NOT NULL DEFAULT '',
    fetched_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(path: Path) -> None:
    conn = connect(path)
    conn.executescript(SCHEMA)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(saved_items)")}
    if "image_id" not in cols:
        conn.execute("ALTER TABLE saved_items ADD COLUMN image_id TEXT")
    jobs_cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)")}
    jobs_migrations: dict[str, str] = {
        "error_code": "error_code TEXT",
        "target": "target TEXT NOT NULL DEFAULT 'stash'",
        "title": "title TEXT NOT NULL DEFAULT ''",
        "thumb_url": "thumb_url TEXT NOT NULL DEFAULT ''",
        "post_json": "post_json TEXT",
        "notices": "notices TEXT NOT NULL DEFAULT '[]'",
        "library_ref_id": "library_ref_id TEXT",
        "dest_path": "dest_path TEXT",
        "attempts": "attempts INTEGER NOT NULL DEFAULT 0",
        "restarts": "restarts INTEGER NOT NULL DEFAULT 0",
        "started_at": "started_at TEXT",
        "finished_at": "finished_at TEXT",
        "placement": "placement TEXT",
    }
    for col_name, col_def in jobs_migrations.items():
        if col_name not in jobs_cols:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {col_def}")
    rules_cols = {row[1] for row in conn.execute("PRAGMA table_info(rules)")}
    if "target" not in rules_cols:
        conn.execute("ALTER TABLE rules ADD COLUMN target TEXT")
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()
    conn.close()


def schema_version(path: Path) -> int:
    conn = sqlite3.connect(str(path))
    try:
        return int(conn.execute("PRAGMA user_version").fetchone()[0])
    finally:
        conn.close()


def db_reachable(path: Path) -> bool:
    try:
        conn = sqlite3.connect(str(path))
        try:
            conn.execute("SELECT 1")
        finally:
            conn.close()
        return True
    except (sqlite3.Error, OSError):
        return False
