"""Restore hardening: index failure and tampered trash path. Real files, real SQLite."""

from pathlib import Path
from typing import Any

import pytest

from app.db import connect, init_db
from app.library.trash import TrashError, TrashSpec, TrashStore


@pytest.fixture
def env(tmp_path):
    db = tmp_path / "p.db"
    init_db(db)
    trash = tmp_path / "trash"
    trash.mkdir()
    lib = tmp_path / "lib"
    lib.mkdir()
    return TrashStore(db, trash), lib, db


def make_spec(lib: Path) -> TrashSpec:
    f = lib / "a.jpg"
    f.write_bytes(b"data")
    kw: dict[str, Any] = dict(
        target="stash", kind="image", entity_id="1", title="a.jpg", orig_path=f
    )
    return TrashSpec(**kw)


def test_restore_index_failure_still_drops_row(env, monkeypatch):
    store, lib, _ = env
    spec = make_spec(lib)
    row = store.delete(spec, lambda: None)

    def boom(*a, **k):
        raise RuntimeError("db locked")

    monkeypatch.setattr(store, "_saved_items_after_restore", boom)
    out = store.restore(row["token"], lambda r, p: ("2", p))
    assert out == spec.orig_path
    assert spec.orig_path.read_bytes() == b"data"
    assert store.get(row["token"]) is None


def test_restore_refuses_trash_path_outside_trash_dir(env, tmp_path):
    store, lib, db = env
    row = store.delete(make_spec(lib), lambda: None)
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"secret")
    conn = connect(db)
    conn.execute(
        "UPDATE trash_items SET trash_path = ? WHERE token = ?", (str(outside), row["token"])
    )
    conn.commit()
    conn.close()
    with pytest.raises(TrashError) as e:
        store.restore(row["token"], lambda r, p: ("2", p))
    assert e.value.code == "trash_unavailable"
    assert outside.exists()
    assert store.get(row["token"])["state"] == "trashed"
