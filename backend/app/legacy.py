"""One-time cleanup for installs that ran Komga as the book server."""

import logging
import os
from pathlib import Path

from app.db import connect

logger = logging.getLogger(__name__)

# Stored settings keys the rename moved to a new name; the value is kept.
_RENAMED_KEYS = (
    ("komga.place_mode", "stump.place_mode"),
    ("options.global.komga_scan_wait_s", "options.global.stump_scan_wait_s"),
    ("view.komga_series", "view.stump_series"),
    ("view.komga_books", "view.stump_books"),
)


def migrate_komga(db_path: Path) -> None:
    """Ignore old Komga config, retag stored rows to stump, log one INFO line when any was found."""
    env = sorted(k for k in os.environ if k.startswith("PEARLIE_KOMGA_"))
    if os.environ.get("PEARLIE_BOOK_SERVER", "").strip().lower() == "komga":
        env.append("PEARLIE_BOOK_SERVER")
    conn = connect(db_path)
    try:
        # saved_items keeps (source, post_id) unique and the retag leaves both alone: no clash.
        # Komga ids mean nothing to Stump, so the library id goes; the index row stays.
        saved = conn.execute(
            "UPDATE saved_items SET target = 'stump', library_id = NULL WHERE target = 'komga'"
        ).rowcount
        # Trash rows keep entity_id and paths: a restore moves the file back and scans Stump.
        trash = conn.execute(
            "UPDATE trash_items SET target = 'stump' WHERE target = 'komga'"
        ).rowcount
        jobs = conn.execute("UPDATE jobs SET target = 'stump' WHERE target = 'komga'").rowcount
        # Copy the old value when the new key is unset, then drop the old row.
        for old, new in _RENAMED_KEYS:
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) "
                "SELECT ?, value FROM settings WHERE key = ?",
                (new, old),
            )
            conn.execute("DELETE FROM settings WHERE key = ?", (old,))
        keys = conn.execute(
            "SELECT COUNT(*) FROM settings "
            "WHERE key LIKE 'komga.%' OR key LIKE 'connections.komga.%'"
        ).fetchone()[0]
        conn.commit()
    finally:
        conn.close()
    if env or keys or saved or trash or jobs:
        logger.info(
            "Komga is removed; its settings are ignored (env vars: %d, stored keys: %d). "
            "Retagged to stump: %d saved items, %d trash items, %d jobs.",
            len(env),
            keys,
            saved,
            trash,
            jobs,
        )
