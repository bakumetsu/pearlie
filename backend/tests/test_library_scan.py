"""Tests for the rule34 folder scan that indexes older Stash images."""

from __future__ import annotations

import json
import sqlite3

import httpx
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.targets.stash_client import StashClient

URL = "http://stash.test"
MD5_A = "6ec467ce2c206d4d8a0495a966ff03b5"
MD5_B = "0123456789abcdef0123456789ABCDEF"


def _img(id, path):
    return {
        "id": id,
        "visual_files": [{"path": path, "basename": path.rsplit("/", 1)[-1]}],
    }


IMAGES = [
    _img("1", f"/mnt/media/stash/rule34/rule34_17575542_{MD5_A}.jpg"),
    _img("2", f"/mnt/media/stash/rule34/rule34_99_{MD5_B}.png"),
    _img("3", "/mnt/media/stash/rule34/holiday.jpg"),
    _img("4", f"/mnt/media/stash/rule34video/rule34_5_{MD5_A}.jpg"),
]


def make_client(tmp_path, images, seen):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body["variables"])
        v = body["variables"]
        start = (v["page"] - 1) * v["n"]
        page = images[start : start + v["n"]]
        return httpx.Response(
            200, json={"data": {"findImages": {"count": len(images), "images": page}}}
        )

    app = create_app(
        Settings(
            mode="real",
            real="library_stash",
            stash_url=URL,
            db_path=tmp_path / "p.db",
            static_dir=tmp_path / "nostatic",
            _env_file=None,  # pyright: ignore[reportCallIssue]
        )
    )
    app.state.stash = StashClient(
        URL, "k", client=httpx.Client(base_url=URL, transport=httpx.MockTransport(handler))
    )
    return TestClient(app), tmp_path / "p.db"


def _rows(db):
    conn = sqlite3.connect(db)
    try:
        return conn.execute(
            "SELECT source, post_id, md5, target, image_id, kind, imported "
            "FROM saved_items ORDER BY post_id"
        ).fetchall()
    finally:
        conn.close()


def test_scan_indexes_matching_files_and_is_idempotent(tmp_path):
    seen: list = []
    c, db = make_client(tmp_path, IMAGES, seen)
    r = c.post("/api/library/scan-rule34")
    assert r.status_code == 200
    assert r.json() == {"found": 4, "imported": 2, "skipped": 2}
    assert _rows(db) == [
        ("rule34", "17575542", MD5_A, "stash", "1", "image", 1),
        ("rule34", "99", MD5_B.lower(), "stash", "2", "image", 1),
    ]
    again = c.post("/api/library/scan-rule34").json()
    assert again["imported"] == 0
    assert len(_rows(db)) == 2


def test_scan_pages_through_folder(tmp_path, monkeypatch):
    import app.api.library_scan as mod

    monkeypatch.setattr(mod, "_PAGE", 1)
    seen: list = []
    c, db = make_client(tmp_path, IMAGES[:2], seen)
    assert c.post("/api/library/scan-rule34").json()["imported"] == 2
    assert [v["page"] for v in seen] == [1, 2]


def test_scan_keeps_existing_row(tmp_path):
    c, db = make_client(tmp_path, IMAGES[:1], [])
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO saved_items (source, post_id, md5, target, image_id, kind) "
        "VALUES ('rule34', '17575542', ?, 'stash', '77', 'image')",
        (MD5_A,),
    )
    conn.commit()
    conn.close()
    assert c.post("/api/library/scan-rule34").json()["imported"] == 0
    assert _rows(db)[0][4:] == ("77", "image", 0)


def test_scan_without_stash_is_502(tmp_path):
    app = create_app(
        Settings(
            mode="real",
            real="library_stash",
            db_path=tmp_path / "p.db",
            static_dir=tmp_path / "nostatic",
            _env_file=None,  # pyright: ignore[reportCallIssue]
        )
    )
    app.state.stash = None
    r = TestClient(app).post("/api/library/scan-rule34")
    assert r.status_code == 502
