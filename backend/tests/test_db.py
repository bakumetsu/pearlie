import sqlite3
from pathlib import Path

import pytest

from app.db import connect, db_reachable, init_db


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
