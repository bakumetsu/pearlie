import sqlite3
from pathlib import Path

# Bump on every new column or table (test_db.py snapshot guard fails otherwise).
SCHEMA_VERSION = 9

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
    ON jobs (source, post_id)
    WHERE status IN ('queued', 'running', 'scan_wait', 'verifying');
CREATE INDEX IF NOT EXISTS idx_jobs_status_id ON jobs (status, id);
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
CREATE TABLE IF NOT EXISTS trash_items (
    token TEXT PRIMARY KEY,
    group_id TEXT,
    target TEXT NOT NULL,
    kind TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    orig_path TEXT NOT NULL,
    trash_path TEXT NOT NULL,
    md5 TEXT,
    source TEXT,
    post_id TEXT,
    meta TEXT NOT NULL DEFAULT '{}',
    state TEXT NOT NULL DEFAULT 'moving',
    trashed_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    size_bytes INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_trash_entity ON trash_items (target, entity_id);
CREATE INDEX IF NOT EXISTS idx_trash_md5 ON trash_items (md5);
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


def _rebuild_active_index(conn: sqlite3.Connection) -> None:
    """Old databases hold idx_jobs_active over queued/running only; widen it once."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND name='idx_jobs_active'"
    ).fetchone()
    if row is not None and "scan_wait" in (row[0] or ""):
        return
    conn.execute("DROP INDEX IF EXISTS idx_jobs_active")
    conn.execute(
        "CREATE UNIQUE INDEX idx_jobs_active ON jobs (source, post_id) "
        "WHERE status IN ('queued', 'running', 'scan_wait', 'verifying')"
    )


def init_db(path: Path) -> None:
    conn = connect(path)
    conn.executescript(SCHEMA)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(saved_items)")}
    if "image_id" not in cols:
        conn.execute("ALTER TABLE saved_items ADD COLUMN image_id TEXT")
    if "library_id" not in cols:
        conn.execute("ALTER TABLE saved_items ADD COLUMN library_id TEXT")
    if "kind" not in cols:
        conn.execute("ALTER TABLE saved_items ADD COLUMN kind TEXT NOT NULL DEFAULT 'image'")
    if "imported" not in cols:
        conn.execute("ALTER TABLE saved_items ADD COLUMN imported INTEGER NOT NULL DEFAULT 0")
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
        "pages_done": "pages_done INTEGER",
        "pages_total": "pages_total INTEGER",
        "eta_s": "eta_s REAL",
        "scan_library_id": "scan_library_id TEXT",
        "scan_name": "scan_name TEXT",
        "scan_due_at": "scan_due_at TEXT",
    }
    for col_name, col_def in jobs_migrations.items():
        if col_name not in jobs_cols:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {col_def}")
    _rebuild_active_index(conn)
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
