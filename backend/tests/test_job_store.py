"""JobStore tests."""

from pathlib import Path

from app.db import connect, init_db
from app.jobs.store import JobStore
from app.models import Problem
from app.sources.base import Post


def make(tmp_path: Path) -> JobStore:
    path = tmp_path / "p.db"
    init_db(path)
    return JobStore(path)


def post(pid: str = "1") -> Post:
    return Post(
        source="danbooru",
        post_id=pid,
        md5="a" * 32,
        file_url="https://x/y.jpg",
        preview_url="https://x/t.jpg",
    )


def test_enqueue_and_get(tmp_path: Path) -> None:
    store = make(tmp_path)
    jid = store.enqueue(post(), "stash", "title", "https://x/t.jpg")
    assert jid == "1"
    job = store.get("1")
    assert job is not None
    assert job.state == "queued"
    assert job.source == "danbooru"
    assert job.post_id == "1"
    assert job.target == "stash"
    assert job.title == "title"
    assert job.thumb_url == f"/api/media/web/{job.source}/{job.post_id}/thumb"
    assert job.notices == []
    assert job.library_ref is None
    assert store.get("zzz") is None
    assert store.get("99") is None


def test_enqueue_same_post_returns_active_id(tmp_path: Path) -> None:
    store = make(tmp_path)
    jid1 = store.enqueue(post(), "stash", "t", "u")
    jid2 = store.enqueue(post(), "stash", "t", "u")
    assert jid2 == jid1
    assert len(store.list()) == 1
    jid3 = store.enqueue(post("2"), "stash", "t", "u")
    assert jid3 != jid1


def test_list_newest_first_and_filter(tmp_path: Path) -> None:
    store = make(tmp_path)
    store.enqueue(post("1"), "stash", "t", "u")
    store.enqueue(post("2"), "stash", "t", "u")
    store.enqueue(post("3"), "stash", "t", "u")
    ids = [j.id for j in store.list()]
    assert ids == ["3", "2", "1"]
    store.mark_running("1")
    running = store.list({"running"})
    assert [j.id for j in running] == ["1"]


def test_saved_image_id(tmp_path: Path) -> None:
    store = make(tmp_path)
    assert store.saved_image_id("danbooru", "1") is None
    path = tmp_path / "p.db"
    conn = connect(path)
    conn.execute(
        "INSERT INTO saved_items (source, post_id, md5, target, image_id) "
        "VALUES (?, ?, ?, ?, ?)",
        ("danbooru", "1", "a" * 32, "stash", "42"),
    )
    conn.commit()
    conn.close()
    assert store.saved_image_id("danbooru", "1") == "42"
    conn = connect(path)
    conn.execute(
        "INSERT INTO saved_items (source, post_id, md5, target, image_id) "
        "VALUES (?, ?, ?, ?, ?)",
        ("danbooru", "2", "b" * 32, "stash", None),
    )
    conn.commit()
    conn.close()
    assert store.saved_image_id("danbooru", "2") == ""


def test_mark_running_once(tmp_path: Path) -> None:
    store = make(tmp_path)
    store.enqueue(post(), "stash", "t", "u")
    assert store.mark_running("1") is True
    assert store.mark_running("1") is False
    job = store.get("1")
    assert job is not None
    assert job.state == "running"


def test_finish_stores_fields(tmp_path: Path) -> None:
    store = make(tmp_path)
    store.enqueue(post(), "stash", "t", "u")
    store.mark_running("1")
    store.finish(
        "1",
        "done",
        notices=[Problem(code="tags_created", message="m")],
        library_ref_id="7",
    )
    job = store.get("1")
    assert job is not None
    assert job.state == "done"
    assert job.progress == 1.0
    assert job.library_ref is not None
    assert job.library_ref.kind == "image"
    assert job.library_ref.id == "7"
    assert job.notices[0].code == "tags_created"
    assert job.finished_at is not None
    new_id = store.enqueue(post(), "stash", "t", "u")
    assert new_id != "1"


def test_failed_then_retry(tmp_path: Path) -> None:
    store = make(tmp_path)
    store.enqueue(post(), "stash", "t", "u")
    store.mark_running("1")
    store.finish("1", "failed", error="boom", error_code="download_failed")
    job = store.get("1")
    assert job is not None
    assert job.error == "boom"
    assert store.retry("1") == "ok"
    job = store.get("1")
    assert job is not None
    assert job.state == "queued"
    assert job.error is None
    assert store.retry("1") == "bad_state"
    assert store.retry("99") == "missing"
    target, post_json = store.load_post("1")
    assert target == "stash"
    assert post_json is None


def test_retry_blocked_by_newer_active_job(tmp_path: Path) -> None:
    store = make(tmp_path)
    store.enqueue(post(), "stash", "t", "u")
    store.mark_running("1")
    store.finish("1", "failed", error="x")
    jid2 = store.enqueue(post(), "stash", "t", "u")
    assert jid2 == "2"
    assert store.retry("1") == "conflict"


def test_delete(tmp_path: Path) -> None:
    store = make(tmp_path)
    store.enqueue(post("1"), "stash", "t", "u")
    store.enqueue(post("2"), "stash", "t", "u")
    store.mark_running("2")
    assert store.delete("1") == "ok"
    assert store.get("1") is None
    assert store.delete("2") == "bad_state"
    assert store.get("2") is not None
    assert store.delete("99") == "missing"


def test_requeue_running(tmp_path: Path) -> None:
    store = make(tmp_path)
    store.enqueue(post("1"), "stash", "t", "u")
    store.enqueue(post("2"), "stash", "t", "u")
    store.mark_running("1")
    assert store.requeue_running() == 1
    j1 = store.get("1")
    assert j1 is not None
    assert j1.state == "queued"
    j2 = store.get("2")
    assert j2 is not None
    assert j2.state == "queued"


def test_requeue_running_caps_restarts(tmp_path: Path) -> None:
    store = make(tmp_path)
    store.enqueue(post("1"), "stash", "t", "u")
    for _ in range(3):
        store.mark_running("1")
        assert store.requeue_running(max_restarts=3) == 1
        job = store.get("1")
        assert job is not None
        assert job.state == "queued"
    store.mark_running("1")
    assert store.requeue_running(max_restarts=3) == 0
    job = store.get("1")
    assert job is not None
    assert job.state == "failed"
    assert job.error_code == "restart_limit"
    assert job.error
    assert store.retry("1") == "ok"
    store.mark_running("1")
    assert store.requeue_running(max_restarts=3) == 1


def test_queued_order(tmp_path: Path) -> None:
    store = make(tmp_path)
    store.enqueue(post("1"), "stash", "t", "u")
    store.enqueue(post("2"), "stash", "t", "u")
    store.enqueue(post("3"), "stash", "t", "u")
    store.mark_running("2")
    result = store.queued()
    assert result == [("1", "danbooru"), ("3", "danbooru")]


def test_set_post_and_load_post(tmp_path: Path) -> None:
    store = make(tmp_path)
    store.enqueue(post("5"), "stash", "t", "u")
    target, post_json = store.load_post("1")
    assert target == "stash"
    assert post_json is not None
    assert '"5"' in post_json
    store.mark_running("1")
    store.finish("1", "failed", error="x")
    store.retry("1")
    store.set_post("1", post())
    _, new_json = store.load_post("1")
    assert new_json is not None


def test_saved_refs_batch_and_md5(tmp_path: Path) -> None:
    store = make(tmp_path)
    assert store.saved_refs("danbooru", []) == {}
    conn = connect(tmp_path / "p.db")
    rows = [
        ("danbooru", "1", "a" * 32, "stash", "42"),
        ("danbooru", "2", "b" * 32, "stump", ""),
        ("gelbooru", "9", "c" * 32, "stash", "7"),
    ]
    conn.executemany(
        "INSERT INTO saved_items (source, post_id, md5, target, image_id) VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()
    got = store.saved_refs("danbooru", ["1", "2", "3", "4"], {"3": "C" * 32, "4": "d" * 32})
    assert got["1"].model_dump() == {"kind": "image", "id": "42"}
    assert got["2"].model_dump() == {"kind": "book", "id": ""}
    assert got["3"].id == "7"  # same file saved from another source (md5 pass)
    assert "4" not in got
    assert "9" not in store.saved_refs("danbooru", ["9"])


def test_saved_refs_video_kind(tmp_path: Path) -> None:
    store = make(tmp_path)
    conn = connect(tmp_path / "p.db")
    rows = [
        ("danbooru", "30", "a" * 32, "stash", "30", "video"),
        ("danbooru", "31", "b" * 32, "stash", "31", "image"),
        ("danbooru", "32", "c" * 32, "stump", "", "image"),
    ]
    conn.executemany(
        "INSERT INTO saved_items (source, post_id, md5, target, image_id, kind) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()
    got = store.saved_refs("danbooru", ["30", "31", "32"])
    assert got["30"].kind == "video"
    assert got["30"].id == "30"
    assert got["31"].kind == "image"
    assert got["31"].id == "31"
    assert got["32"].kind == "book"
    assert got["32"].id == ""
    assert store.saved_kind("danbooru", "30") == "video"
    assert store.saved_kind("danbooru", "31") == "image"
    md5_got = store.saved_refs("danbooru", ["99"], {"99": "a" * 32})
    assert md5_got["99"].kind == "video"


def test_list_pages_with_limit_and_offset(tmp_path: Path) -> None:
    store = make(tmp_path)
    for i in range(5):
        store.enqueue(post(str(i)), "stash", "t", "u")
    assert [j.id for j in store.list(limit=2)] == ["5", "4"]
    assert [j.id for j in store.list(limit=2, offset=2)] == ["3", "2"]
    assert len(store.list()) == 5


def test_jobs_status_index_exists(tmp_path: Path) -> None:
    store = make(tmp_path)
    conn = connect(tmp_path / "p.db")
    try:
        names = {r[1] for r in conn.execute("PRAGMA index_list(jobs)")}
    finally:
        conn.close()
    assert "idx_jobs_status_id" in names
    del store


def test_purge_finished_drops_only_old_terminal_jobs(tmp_path: Path) -> None:
    store = make(tmp_path)
    for i in range(4):
        store.enqueue(post(str(i)), "stash", "t", "u")
    conn = connect(tmp_path / "p.db")
    try:
        conn.execute(
            "UPDATE jobs SET status='done', finished_at=datetime('now','-40 days') WHERE id=1"
        )
        conn.execute("UPDATE jobs SET status='done', finished_at=datetime('now') WHERE id=2")
        conn.execute(
            "UPDATE jobs SET status='failed', finished_at=datetime('now','-40 days') WHERE id=3"
        )
        conn.commit()
    finally:
        conn.close()
    assert store.purge_finished(30) == 1
    assert sorted(j.id for j in store.list()) == ["2", "3", "4"]


def test_list_does_not_read_post_json(tmp_path: Path, monkeypatch) -> None:
    import app.jobs.store as store_mod

    store = make(tmp_path)
    store.enqueue(post(), "stash", "t", "u")
    seen: list[str] = []

    def traced(path: Path):
        conn = connect(path)
        conn.set_trace_callback(seen.append)
        return conn

    monkeypatch.setattr(store_mod, "connect", traced)
    jobs = store.list()
    assert len(jobs) == 1
    assert not any("post_json" in s for s in seen)
    assert not any(s.startswith("SELECT *") for s in seen)


def test_saved_refs_null_image_id(tmp_path: Path) -> None:
    store = make(tmp_path)
    conn = connect(tmp_path / "p.db")
    rows = [
        ("danbooru", "1", "a" * 32, "stash", None, "image"),
        ("danbooru", "2", "b" * 32, "stump", None, "book"),
        ("danbooru", "3", "c" * 32, "stash", None, "video"),
    ]
    conn.executemany(
        "INSERT INTO saved_items (source, post_id, md5, target, image_id, kind) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()

    refs = store.saved_refs("danbooru", ["1", "2", "3"])
    assert refs["1"].id == ""
    assert refs["1"].kind == "image"
    assert refs["2"].id == ""
    assert refs["2"].kind == "book"
    assert refs["3"].id == ""
    assert refs["3"].kind == "video"

    md5s = {"8": "A" * 32, "9": "b" * 32}
    refs2 = store.saved_refs("danbooru", ["8", "9"], md5s)
    assert refs2["8"].id == ""
    assert refs2["8"].kind == "image"
    assert refs2["9"].id == ""
    assert refs2["9"].kind == "book"

    assert store.saved_image_id("danbooru", "1") == ""


def test_retry_conflict_rolls_back_failed_job(tmp_path: Path) -> None:
    store = make(tmp_path)
    jid = store.enqueue(post("1"), "stash", "t", "u")
    store.mark_running(jid)
    store.finish(jid, "failed", error="x")

    # Enqueue the same post again -> new active job exists.
    store.enqueue(post("1"), "stash", "t", "u")

    conn = connect(tmp_path / "p.db")
    row_before = conn.execute(
        "SELECT attempts, status, error, notices FROM jobs WHERE id = ?", (jid,)
    ).fetchone()
    before = (
        row_before["attempts"],
        row_before["status"],
        row_before["error"],
        row_before["notices"],
    )

    assert store.retry(jid) == "conflict"

    row_after = conn.execute(
        "SELECT attempts, status, error, notices FROM jobs WHERE id = ?", (jid,)
    ).fetchone()
    after = (
        row_after["attempts"],
        row_after["status"],
        row_after["error"],
        row_after["notices"],
    )
    assert after == before
    assert row_after["status"] == "failed"
    assert row_after["error"] == "x"
    conn.close()

    assert store.get(jid) is not None
    assert store.enqueue(post("2"), "stash", "t", "u") == "3"


def test_done_book_job_without_ref_takes_the_book_id_from_the_index(tmp_path: Path) -> None:
    store = make(tmp_path)
    p1 = post()
    jid = store.enqueue(p1, "stump", "t", "")
    assert store.mark_running(jid)
    store.finish(jid, "done")
    other = store.enqueue(post("2"), "stump", "t2", "")
    assert store.mark_running(other)
    store.finish(other, "done")
    conn = connect(tmp_path / "p.db")
    conn.execute(
        "INSERT INTO saved_items (source, post_id, md5, target, image_id, library_id) "
        "VALUES (?, ?, 'm', 'stump', '', 'B9')",
        (p1.source, p1.post_id),
    )
    conn.commit()
    conn.close()
    for job in (store.get(jid), next(j for j in store.list() if j.id == jid)):
        assert job is not None and job.library_ref is not None
        assert (job.library_ref.kind, job.library_ref.id) == ("book", "B9")
    nolink = store.get(other)
    assert nolink is not None and nolink.library_ref is None
