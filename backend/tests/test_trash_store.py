"""TrashStore core tests: real files in tmp_path, real SQLite, no Stash."""

from datetime import UTC, datetime, timedelta
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


def make_spec(lib: Path, name="a.jpg", entity_id="1", **over) -> TrashSpec:
    f = lib / name
    f.write_bytes(b"data")
    kw: dict[str, Any] = dict(
        target="stash", kind="image", entity_id=entity_id, title=name, orig_path=f
    )
    kw.update(over)
    return TrashSpec(**kw)


def noop():
    return None


def test_delete_moves_file_and_restore_puts_it_back(env):
    store, lib, _ = env
    spec = make_spec(lib)
    row = store.delete(spec, noop)
    assert row["state"] == "trashed"
    assert not spec.orig_path.exists()
    assert (store.dir / row["token"] / "a.jpg").read_bytes() == b"data"
    assert store.active_for_entity("stash", "1")

    out = store.restore(row["token"], lambda r, p: ("2", p))
    assert out == spec.orig_path
    assert spec.orig_path.read_bytes() == b"data"
    assert store.get(row["token"]) is None
    assert not (store.dir / row["token"]).exists()


def test_destroy_failure_rolls_back(env):
    store, lib, _ = env
    spec = make_spec(lib)

    def boom():
        raise RuntimeError("stash down")

    with pytest.raises(RuntimeError):
        store.delete(spec, boom)
    assert spec.orig_path.exists()
    assert store.list_rows() == []
    assert store.active_for_entity("stash", "1") is None
    assert list(store.dir.iterdir()) == []


def test_missing_trash_dir_is_503(env):
    store, lib, _ = env
    spec = make_spec(lib)
    store.dir.rmdir()
    store.dir.write_text("a file blocks the folder")
    with pytest.raises(TrashError) as e:
        store.delete(spec, noop)
    assert e.value.status == 503
    assert spec.orig_path.exists()


def test_source_inside_trash_is_refused(env):
    store, _, _ = env
    f = store.dir / "x.jpg"
    f.write_bytes(b"x")
    spec = TrashSpec(target="stash", kind="image", entity_id="9", title="x", orig_path=f)
    with pytest.raises(TrashError) as e:
        store.delete(spec, noop)
    assert e.value.code == "path_outside_library"


def test_restore_suffix_when_original_path_taken(env):
    store, lib, _ = env
    spec = make_spec(lib)
    row = store.delete(spec, noop)
    spec.orig_path.write_bytes(b"new")
    out = store.restore(row["token"], lambda r, p: ("2", p))
    assert out != spec.orig_path
    assert out.parent == lib
    assert out.read_bytes() == b"data"
    assert spec.orig_path.read_bytes() == b"new"


def test_restore_apply_failure_keeps_file_and_reports(env):
    store, lib, _ = env
    spec = make_spec(lib)
    row = store.delete(spec, noop)

    def bad(r, p):
        raise RuntimeError("not indexed")

    with pytest.raises(TrashError) as e:
        store.restore(row["token"], bad)
    assert e.value.code == "restore_incomplete"
    assert spec.orig_path.exists()
    assert store.get(row["token"]) is None


def test_expired_token_is_purged_and_404(env):
    store, lib, db = env
    row = store.delete(make_spec(lib), noop)
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    conn = connect(db)
    conn.execute("UPDATE trash_items SET expires_at = ? WHERE token = ?", (past, row["token"]))
    conn.commit()
    conn.close()
    assert store.list_rows() == []
    with pytest.raises(TrashError) as e:
        store.restore(row["token"], lambda r, p: ("2", p))
    assert e.value.status == 404
    assert not (store.dir / row["token"]).exists()


def test_purge_expired_only_takes_expired(env):
    store, lib, db = env
    old = store.delete(make_spec(lib, "a.jpg", "1"), noop)
    keep = store.delete(make_spec(lib, "b.jpg", "2"), noop)
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    conn = connect(db)
    conn.execute("UPDATE trash_items SET expires_at = ? WHERE token = ?", (past, old["token"]))
    conn.commit()
    conn.close()
    assert store.purge_expired() == 1
    assert store.get(old["token"]) is None
    assert store.get(keep["token"]) is not None


def test_empty_and_delete_for_good(env):
    store, lib, _ = env
    a = store.delete(make_spec(lib, "a.jpg", "1"), noop)
    store.delete(make_spec(lib, "b.jpg", "2"), noop)
    store.delete(make_spec(lib, "c.jpg", "3"), noop)
    store.delete_for_good(a["token"])
    assert not (store.dir / a["token"]).exists()
    with pytest.raises(TrashError):
        store.delete_for_good(a["token"])
    assert store.empty() == 2
    assert store.list_rows() == []
    assert list(store.dir.iterdir()) == []


def test_purge_removes_saved_items_row(env):
    store, lib, db = env
    conn = connect(db)
    conn.execute(
        "INSERT INTO saved_items (source, post_id, md5, target, image_id, kind) "
        "VALUES ('gelbooru','55','abc','stash','1','image')"
    )
    conn.commit()
    conn.close()
    row = store.delete(make_spec(lib, source="gelbooru", post_id="55", md5="ABC"), noop)
    assert store.find_in_trash("gelbooru", "55")["token"] == row["token"]
    assert store.find_in_trash(md5="abc")["token"] == row["token"]
    store.purge_row(row["token"])
    conn = connect(db)
    n = conn.execute("SELECT COUNT(*) FROM saved_items").fetchone()[0]
    conn.close()
    assert n == 0
    assert store.find_in_trash("gelbooru", "55") is None


def test_restore_repoints_saved_items(env):
    store, lib, db = env
    conn = connect(db)
    conn.execute(
        "INSERT INTO saved_items (source, post_id, md5, target, image_id, kind) "
        "VALUES ('gelbooru','55','abc','stash','1','image')"
    )
    conn.commit()
    conn.close()
    row = store.delete(make_spec(lib, source="gelbooru", post_id="55", md5="abc"), noop)
    store.restore(row["token"], lambda r, p: ("77", p))
    conn = connect(db)
    ids = [r[0] for r in conn.execute("SELECT image_id FROM saved_items")]
    conn.close()
    assert ids == ["77"]


def test_folder_item_moves_whole_folder(env):
    store, lib, _ = env
    d = lib / "gallery"
    d.mkdir()
    (d / "1.jpg").write_bytes(b"1")
    spec = TrashSpec(target="stash", kind="image", entity_id="5", title="g", orig_path=d)
    row = store.delete(spec, noop)
    assert not d.exists()
    assert (store.dir / row["token"] / "gallery" / "1.jpg").exists()


def test_retention_and_preview(env):
    store, lib, db = env
    assert store.retention_days() == 7
    row = store.delete(make_spec(lib), noop)
    old = (datetime.now(UTC) - timedelta(days=3)).isoformat()
    conn = connect(db)
    conn.execute("UPDATE trash_items SET trashed_at = ? WHERE token = ?", (old, row["token"]))
    conn.commit()
    conn.close()
    assert store.purge_preview(2) == 1
    assert store.purge_preview(5) == 0
    assert store.set_retention(2) == 0  # lowering without purge keeps the row
    assert store.get(row["token"]) is not None
    assert store.set_retention(2, purge=True) == 1
    assert store.get(row["token"]) is None


def test_repair_moving_row(env):
    store, lib, db = env
    spec = make_spec(lib, "a.jpg", "1")
    row = store.delete(spec, noop)
    # Fake a crash after the move: state back to moving.
    conn = connect(db)
    conn.execute("UPDATE trash_items SET state='moving' WHERE token=?", (row["token"],))
    conn.commit()
    conn.close()
    called = []
    store.repair({"stash": lambda r: called.append(r["token"])})
    assert called == [row["token"]]
    assert store.get(row["token"])["state"] == "trashed"

    # Destroy fails on repair: file goes back, row dropped.
    conn = connect(db)
    conn.execute("UPDATE trash_items SET state='moving' WHERE token=?", (row["token"],))
    conn.commit()
    conn.close()

    def boom(r):
        raise RuntimeError

    store.repair({"stash": boom})
    assert spec.orig_path.exists()
    assert store.get(row["token"]) is None
