"""ScanWait: one Stump scan per quiet library, then the book check."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import pytest

from app.db import connect, init_db
from app.jobs.scan_wait import ScanWait
from app.jobs.store import JobStore
from app.jobs.worker import JobWorker
from app.models import Problem
from app.sources.base import Post
from app.stump import StumpError
from app.targets.stash import PendingScan, SaveResult


class Clock:
    now = 1000.0

    def __call__(self) -> float:
        return self.now


class FakeStump:
    def __init__(self) -> None:
        self.scans: list[str] = []
        self.visible: set[str] = set()  # stump paths Stump lists
        self.fail_scan = False
        self.fail_list = False
        self.list_calls = 0

    def scan(self, library_id: str) -> None:
        if self.fail_scan:
            raise StumpError("upstream_error", "down", 502)
        self.scans.append(library_id)

    def find_books(self, library_id: str, books: dict[str, PendingScan]) -> dict[str, str]:
        self.list_calls += 1
        if self.fail_list:
            raise StumpError("upstream_error", "down", 502)
        return {j: f"book-{j}" for j, b in books.items() if b.stump_path in self.visible}


class Env:
    def __init__(self, tmp_path: Path) -> None:
        self.db = tmp_path / "p.db"
        init_db(self.db)
        self.clock = Clock()
        self.store = JobStore(self.db)
        self.stump = FakeStump()
        self.worker = JobWorker(self.db, {}, {}, clock=self.clock)
        self.wait = self.make_wait()
        self.worker.scan_wait = self.wait
        self.n = 0

    def make_wait(self, **kw: object) -> ScanWait:
        return ScanWait(
            self.stump,
            self.store,
            self.worker.finish_saved,
            wait_s=lambda: 10.0,
            clock=self.clock,
            delays=(0.0,) * 6,
            **kw,  # type: ignore[arg-type]
        )

    def job(
        self, lib: str = "L1", notice: bool = False, wait: float | None = None
    ) -> tuple[str, str]:
        """A saved job in scan_wait; returns (job id, stump path)."""
        self.n += 1
        post = Post(
            source="nhentai", post_id=str(self.n), title="t", source_url="https://x/", tags={}
        )
        jid = self.store.enqueue(post, "stump", "t", "")
        assert self.store.mark_running(jid)
        path = f"/k/{self.n}.cbz"
        notices = [Problem(code="oneshots_not_set", message="m")] if notice else []
        self.store.mark_scan_wait(jid, lib, f"{self.n}.cbz", path, notices)
        pending = PendingScan(library_id=lib, name=f"{self.n}.cbz", stump_path=path)
        self.wait.add(jid, "nhentai", pending, wait_s=wait)
        return jid, path

    def state(self, jid: str) -> str:
        job = self.store.get(jid)
        assert job is not None
        return job.state


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


def test_five_files_make_one_scan(env: Env) -> None:
    jobs = [env.job() for _ in range(5)]
    env.stump.visible = {p for _j, p in jobs}
    assert env.wait.run_due() == 0
    env.clock.now += 10
    assert env.wait.run_due() == 1
    assert env.stump.scans == ["L1"]
    assert env.stump.list_calls == 1
    assert all(env.state(j) == "done" for j, _p in jobs)


def test_new_file_restarts_the_timer(env: Env) -> None:
    first, p1 = env.job()
    env.clock.now += 6
    second, p2 = env.job()
    env.stump.visible = {p1, p2}
    env.clock.now += 6  # 12 s after the first file, 6 s after the second
    assert env.wait.run_due() == 0 and env.stump.scans == []
    assert env.state(first) == "scan_wait"
    job = env.store.get(first)
    assert (
        job is not None and job.eta_s is not None and 9.0 < job.eta_s <= 10.0
    )  # the countdown jumped back up
    env.clock.now += 5
    assert env.wait.run_due() == 1
    assert env.stump.scans == ["L1"]
    assert env.state(first) == env.state(second) == "done"


def test_other_library_has_its_own_timer(env: Env) -> None:
    a, pa = env.job("L1")
    env.clock.now += 8
    b, pb = env.job("L2")
    env.stump.visible = {pa, pb}
    env.clock.now += 3  # L1 is 11 s old, L2 3 s
    assert env.wait.run_due() == 1
    assert env.stump.scans == ["L1"]
    assert env.state(a) == "done" and env.state(b) == "scan_wait"
    env.clock.now += 7
    env.wait.run_due()
    assert env.stump.scans == ["L1", "L2"]


def test_hold_cap_stops_a_steady_trickle(env: Env, caplog: pytest.LogCaptureFixture) -> None:
    wait = env.make_wait(max_hold_s=30.0)
    env.wait = env.worker.scan_wait = wait
    caplog.set_level(logging.INFO, logger="pearlie.stump")
    jobs = []
    for _ in range(5):
        jobs.append(env.job())
        env.clock.now += 8  # always inside the 10 s wait
    env.stump.visible = {p for _j, p in jobs}
    assert env.wait.run_due() == 1  # 40 s since the first, cap at 30 s
    assert "hold cap reached" in caplog.text
    assert env.stump.scans == ["L1"]


def test_found_book_ends_done_with_its_saved_notices(env: Env) -> None:
    jid, path = env.job(notice=True)
    env.stump.visible = {path}
    env.clock.now += 10
    env.wait.run_due()
    job = env.store.get(jid)
    assert job is not None and job.state == "done"
    assert job.dest_path == path
    assert job.library_ref is not None
    assert (job.library_ref.kind, job.library_ref.id) == ("book", f"book-{jid}")
    assert [n.code for n in job.notices] == ["oneshots_not_set"]
    assert job.finished_at is not None


def test_not_found_ends_done_with_notice_after_one_extra_scan(env: Env) -> None:
    jid, path = env.job(notice=True)
    env.clock.now += 10
    env.wait.run_due()
    assert env.stump.scans == ["L1", "L1"]  # one extra scan after try 3, never a third
    assert env.stump.list_calls == 6
    job = env.store.get(jid)
    assert job is not None and job.state == "done"
    assert [n.code for n in job.notices] == ["oneshots_not_set", "waiting_for_stump"]


def test_no_extra_scan_when_a_book_was_found(env: Env) -> None:
    _a, pa = env.job()
    env.job()  # never listed
    env.stump.visible = {pa}
    env.clock.now += 10
    env.wait.run_due()
    assert env.stump.scans == ["L1"]


def test_scan_failure_ends_done_with_notice(env: Env) -> None:
    jid, _p = env.job()
    env.stump.fail_scan = True
    env.clock.now += 10
    env.wait.run_due()
    job = env.store.get(jid)
    assert job is not None and job.state == "done"
    assert [n.code for n in job.notices] == ["scan_failed"]


def test_list_error_stops_checking_and_still_ends_the_job(env: Env) -> None:
    jid, _p = env.job()
    env.stump.fail_list = True
    env.clock.now += 10
    env.wait.run_due()
    assert env.stump.list_calls == 1
    job = env.store.get(jid)
    assert job is not None and job.state == "done"
    assert [n.code for n in job.notices] == ["waiting_for_stump"]


def test_job_removed_while_waiting_is_dropped(env: Env) -> None:
    gone, _pg = env.job()
    kept, pk = env.job()
    assert env.store.delete(gone) == "ok"
    env.stump.visible = {pk}
    env.clock.now += 10
    env.wait.run_due()
    assert env.store.get(gone) is None
    assert env.state(kept) == "done"


def test_batch_of_removed_jobs_makes_no_scan(env: Env) -> None:
    gone, _p = env.job()
    env.store.delete(gone)
    env.clock.now += 10
    env.wait.run_due()
    assert env.stump.scans == []


def test_zero_wait_fires_at_once(env: Env) -> None:
    jid, path = env.job("L9", wait=0)
    env.stump.visible = {path}
    assert env.wait.run_due() == 1
    assert env.stump.scans == ["L9"] and env.state(jid) == "done"


def test_scan_wait_and_worker_end_a_job_the_same_way(
    env: Env, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="pearlie.jobs")
    jid, path = env.job(notice=True)
    env.stump.visible = {path}
    env.clock.now += 10
    env.wait.run_due()
    waited = env.store.get(jid)
    waited_logs = [r.getMessage() for r in caplog.records if "end state=done" in r.getMessage()]

    post = Post(source="nhentai", post_id="99", title="t", source_url="https://x/", tags={})
    direct = env.store.enqueue(post, "stump", "t", "")
    env.store.mark_running(direct)
    env.worker.finish_saved(
        direct, "nhentai", [Problem(code="oneshots_not_set", message="m")], path, None
    )
    plain = env.store.get(direct)
    assert waited is not None and plain is not None
    assert (waited.state, waited.dest_path, [n.code for n in waited.notices]) == (
        plain.state,
        plain.dest_path,
        [n.code for n in plain.notices],
    )
    assert waited.finished_at and plain.finished_at
    assert waited_logs == [f"job={jid} end state=done"]


def test_restart_rearms_three_waiting_jobs_with_one_scan(env: Env) -> None:
    jobs = [env.job() for _ in range(3)]
    env.stump.visible = {p for _j, p in jobs}
    env.store.set_verifying([jobs[0][0]])  # one was mid-check at the crash
    fresh = Env.__new__(Env)
    fresh.db, fresh.clock, fresh.store, fresh.stump = env.db, Clock(), env.store, FakeStump()
    fresh.stump.visible = env.stump.visible
    fresh.worker = JobWorker(env.db, {}, {}, clock=fresh.clock)
    fresh.wait = fresh.worker.scan_wait = fresh.make_wait()
    assert fresh.worker.recover() == 0
    assert all(fresh.state(j) == "scan_wait" for j, _p in jobs)
    assert fresh.wait.run_due() == 0
    fresh.clock.now += 10
    assert fresh.wait.run_due() == 1
    assert fresh.stump.scans == ["L1"]
    assert all(fresh.state(j) == "done" for j, _p in jobs)


def test_worker_parks_a_saved_job_with_pending_scan(env: Env) -> None:
    class Target:
        def save(self, post: Post, tags: list[str]) -> SaveResult:
            return SaveResult(
                status="saved",
                dest_path="/k/a.cbz",
                pending_scan=PendingScan(library_id="L1", name="a.cbz", stump_path="/k/a.cbz"),
            )

    class Source:
        id = "nhentai"

    post = Post(source="nhentai", post_id="5", title="t", source_url="https://x/", tags={})
    worker = JobWorker(env.db, {"nhentai": Source()}, {"stump": Target()}, clock=env.clock)  # type: ignore[dict-item]
    worker.scan_wait = env.wait
    jid = env.store.enqueue(post, "stump", "t", "")
    assert worker.run_once()
    job = env.store.get(jid)
    assert job is not None and job.state == "scan_wait" and job.progress == 1.0
    assert job.eta_s is not None and 0 < job.eta_s <= 10
    assert job.dest_path == "/k/a.cbz" and job.finished_at is None


def test_new_states_block_a_second_active_job_and_count_as_active(env: Env) -> None:
    jid, _p = env.job()
    waiting = env.store.get(jid)
    assert waiting is not None
    post = Post(
        source="nhentai", post_id=waiting.post_id, title="t", source_url="https://x/", tags={}
    )
    assert env.store.active_job_id("nhentai", post.post_id) == jid
    assert env.store.enqueue(post, "stump", "t", "") == jid  # the index blocks a 2nd row
    env.store.set_verifying([jid])
    assert env.store.active_job_id("nhentai", post.post_id) == jid
    checking = env.store.get(jid)
    assert checking is not None and checking.state == "verifying" and checking.eta_s is None


def test_old_active_index_is_rebuilt_once(tmp_path: Path) -> None:
    db = tmp_path / "old.db"
    init_db(db)
    conn = connect(db)
    conn.execute("DROP INDEX idx_jobs_active")
    conn.execute(
        "CREATE UNIQUE INDEX idx_jobs_active ON jobs (source, post_id) "
        "WHERE status IN ('queued', 'running')"
    )
    conn.execute("INSERT INTO jobs (source, post_id, status) VALUES ('nhentai', '1', 'done')")
    conn.commit()
    conn.close()
    init_db(db)
    init_db(db)
    conn = connect(db)
    sql = conn.execute("SELECT sql FROM sqlite_master WHERE name='idx_jobs_active'").fetchone()[0]
    conn.execute("INSERT INTO jobs (source, post_id, status) VALUES ('nhentai', '1', 'scan_wait')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO jobs (source, post_id, status) VALUES ('nhentai', '1', 'verifying')"
        )
    conn.close()
    assert "scan_wait" in sql
    assert JobStore(db).get("1") is not None  # old rows still load
