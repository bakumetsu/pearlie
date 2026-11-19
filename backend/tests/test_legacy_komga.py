"""Old Komga installs: stored rows are retagged to stump, one INFO line, no crash."""

import logging

from app.db import connect, init_db
from app.legacy import migrate_komga


def test_rows_are_retagged_and_one_line_is_logged(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("PEARLIE_KOMGA_URL", "http://komga")
    monkeypatch.setenv("PEARLIE_BOOK_SERVER", "komga")
    db = tmp_path / "p.db"
    init_db(db)
    conn = connect(db)
    conn.execute(
        "INSERT INTO saved_items (source, post_id, md5, target, library_id) "
        "VALUES ('nhentai','1','m1','komga','kid'), ('nhentai','2','m2','stash','sid')"
    )
    conn.execute(
        "INSERT INTO trash_items (token, target, kind, entity_id, orig_path, trash_path, "
        "trashed_at, expires_at) VALUES ('t','komga','book','k1','/a','/b','x','y')"
    )
    conn.execute("INSERT INTO jobs (source, post_id, target) VALUES ('nhentai','3','komga')")
    conn.execute("INSERT INTO settings (key, value) VALUES ('connections.komga.url','u')")
    conn.commit()
    conn.close()
    with caplog.at_level(logging.INFO, logger="app.legacy"):
        migrate_komga(db)
    conn = connect(db)
    rows = conn.execute("SELECT target, library_id FROM saved_items ORDER BY id").fetchall()
    assert [tuple(r) for r in rows] == [("stump", None), ("stash", "sid")]
    assert conn.execute("SELECT target FROM trash_items").fetchone()[0] == "stump"
    assert conn.execute("SELECT target FROM jobs").fetchone()[0] == "stump"
    conn.close()
    lines = [r.message for r in caplog.records if "Komga is removed" in r.message]
    assert len(lines) == 1
    assert "1 saved items, 1 trash items, 1 jobs" in lines[0]


def test_clean_install_logs_nothing(tmp_path, monkeypatch, caplog):
    monkeypatch.delenv("PEARLIE_BOOK_SERVER", raising=False)
    db = tmp_path / "p.db"
    init_db(db)
    with caplog.at_level(logging.INFO, logger="app.legacy"):
        migrate_komga(db)
    assert not caplog.records


def test_renamed_settings_keys_keep_their_values(tmp_path):
    db = tmp_path / "p.db"
    init_db(db)
    conn = connect(db)
    conn.executemany(
        "INSERT INTO settings (key, value) VALUES (?, ?)",
        [
            ("komga.place_mode", "auto"),
            ("options.global.komga_scan_wait_s", "42"),
            ("view.komga_books", '{"mode": "list", "per_page": 50, "zoom": 2}'),
            ("view.komga_series", '{"mode": "grid", "per_page": 25, "zoom": 3}'),
            ("view.stump_series", '{"mode": "list", "per_page": 10, "zoom": 1}'),
        ],
    )
    conn.commit()
    conn.close()
    migrate_komga(db)
    conn = connect(db)
    got = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings")}
    conn.close()
    assert got["stump.place_mode"] == "auto"
    assert got["options.global.stump_scan_wait_s"] == "42"
    assert '"list"' in got["view.stump_books"]
    assert '"per_page": 10' in got["view.stump_series"]  # a value already set stays
    assert not [k for k in got if "komga" in k]
