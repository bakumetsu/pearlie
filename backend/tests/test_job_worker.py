"""JobWorker tests."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app import logs
from app.db import init_db
from app.jobs.store import JobStore
from app.jobs.worker import JobWorker
from app.models import Problem
from app.sources.base import Post, SourceError
from app.targets.stash import SaveError, SaveResult


class FakeClock:
    now: float = 100.0

    def __call__(self) -> float:
        return self.now

    def advance(self, s: float) -> None:
        self.now += s


class FakeSource:
    def __init__(self, id: str) -> None:
        self.id = id
        self.target = "stash"
        self.file_hosts: tuple[str, ...] = ()
        self.posts: dict[str, Post] = {}
        self.calls: list[str] = []

    def get_post(self, pid: str) -> Post:
        self.calls.append(pid)
        if pid not in self.posts:
            raise SourceError("not_found", "post not found")
        return self.posts[pid]

    def search(self, *args: object, **kwargs: object) -> Any:
        raise NotImplementedError


class FakeTarget:
    def __init__(self) -> None:
        self.results: list[object] = []
        self.calls: list[str] = []
        self.tags_seen: list[list[str]] = []
        self.inflight: dict[str, int] = {}
        self.max_inflight: dict[str, int] = {}
        self._lock = threading.Lock()
        self.entered: threading.Event | None = None
        self.release: threading.Event | None = None
        self.block_sources: set[str] = set()

    def save(self, post: Post, tags: list[str]) -> SaveResult:
        self.calls.append(post.post_id)
        self.tags_seen.append(tags)
        with self._lock:
            self.inflight[post.source] = self.inflight.get(post.source, 0) + 1
            cur = self.inflight[post.source]
            if cur > self.max_inflight.get(post.source, 0):
                self.max_inflight[post.source] = cur
        try:
            if self.release is not None and post.source in self.block_sources:
                assert self.entered is not None
                self.entered.set()
                self.release.wait(5.0)
            if self.results:
                item = self.results.pop(0)
                if isinstance(item, Exception):
                    raise item
                return item  # type: ignore[return-value]
            return SaveResult(status="saved", image_id="7")
        finally:
            with self._lock:
                self.inflight[post.source] -= 1


def _make_post(source_id: str, pid: str) -> Post:
    return Post(
        source=source_id,
        post_id=pid,
        md5=pid * 32,
        file_url="https://x/y.jpg",
        preview_url="https://x/t.jpg",
        tags={"general": ["a_b", "c"]},
    )


def make(
    tmp_path: Path,
    interval: float = 2.0,
    workers: int = 1,
    sources: tuple[str, ...] = ("danbooru",),
    clock: FakeClock | None = None,
) -> tuple[JobWorker, JobStore, FakeTarget, dict[str, FakeSource], FakeClock]:
    path = tmp_path / "p.db"
    init_db(path)
    ck = clock or FakeClock()
    fake_sources: dict[str, FakeSource] = {}
    for sid in sources:
        fs = FakeSource(sid)
        for pid in ("1", "2", "3"):
            fs.posts[pid] = _make_post(sid, pid)
        fake_sources[sid] = fs
    fake_target = FakeTarget()
    worker = JobWorker(
        path,
        fake_sources,  # type: ignore[arg-type]
        {"stash": fake_target},
        interval_s=interval,
        clock=ck,
        workers=workers,
    )
    store = JobStore(path)
    return worker, store, fake_target, fake_sources, ck


def enqueue(store: JobStore, sources: dict[str, FakeSource], source_id: str, pid: str) -> str:
    post = sources[source_id].posts[pid]
    return store.enqueue(post, "stash", f"{source_id} {pid}", "t")


def test_run_once_saves(tmp_path: Path) -> None:
    worker, store, target, sources, clock = make(tmp_path)
    jid = enqueue(store, sources, "danbooru", "1")
    assert worker.run_once() is True
    job = store.get(jid)
    assert job is not None
    assert job.state == "done"
    assert job.library_ref is not None
    assert job.library_ref.id == "7"
    assert target.calls == ["1"]
    assert worker.run_once() is False


def test_unknown_save_status_fails_job(tmp_path: Path) -> None:
    worker, store, target, sources, clock = make(tmp_path)
    target.results = [SimpleNamespace(status="weird", notices=[], image_id=None)]
    jid = enqueue(store, sources, "danbooru", "1")
    assert worker.run_once() is True
    job = store.get(jid)
    assert job is not None
    assert job.state == "failed"
    assert job.error == "unexpected save result"


def test_tags_are_flattened_sorted(tmp_path: Path) -> None:
    worker, store, target, sources, clock = make(tmp_path)
    enqueue(store, sources, "danbooru", "1")
    worker.run_once()
    assert target.tags_seen == [["a_b", "c"]]


def test_failed_job_keeps_error_then_retry_succeeds(tmp_path: Path) -> None:
    worker, store, target, sources, clock = make(tmp_path)
    target.results.append(SaveError("download_failed", "download failed", 502))
    jid = enqueue(store, sources, "danbooru", "1")
    assert worker.run_once() is True
    job = store.get(jid)
    assert job is not None
    assert job.state == "failed"
    assert job.error == "download failed"
    assert store.retry(jid) == "ok"
    clock.advance(2.0)
    assert worker.run_once() is True
    job = store.get(jid)
    assert job is not None
    assert job.state == "done"


def test_duplicate_is_skipped_with_text(tmp_path: Path) -> None:
    worker, store, target, sources, clock = make(tmp_path)
    target.results.append(
        SaveResult(
            status="duplicate",
            image_id="5",
            notices=[Problem(code="duplicate", message="already saved (md5), image 5")],
        )
    )
    jid = enqueue(store, sources, "danbooru", "1")
    assert worker.run_once() is True
    job = store.get(jid)
    assert job is not None
    assert job.state == "skipped"
    assert job.error == "already saved (md5), image 5"
    assert job.library_ref is not None
    assert job.library_ref.id == "5"
    assert len(job.notices) == 1


def test_notices_kept_on_done(tmp_path: Path) -> None:
    worker, store, target, sources, clock = make(tmp_path)
    target.results.append(
        SaveResult(
            status="saved",
            image_id="7",
            notices=[Problem(code="tags_created", message="created tags: x")],
        )
    )
    jid = enqueue(store, sources, "danbooru", "1")
    assert worker.run_once() is True
    job = store.get(jid)
    assert job is not None
    assert job.state == "done"
    assert job.notices[0].code == "tags_created"


def test_no_target(tmp_path: Path) -> None:
    worker, store, target, sources, clock = make(tmp_path, sources=("danbooru", "gelbooru"))
    sources["gelbooru"].target = "komga"
    post = sources["gelbooru"].posts["1"]
    jid = store.enqueue(post, "komga", "gelbooru 1", "t")
    assert worker.run_once() is True
    job = store.get(jid)
    assert job is not None
    assert job.state == "failed"
    assert job.error == "no save target for komga yet"


def test_unexpected_error_text_has_no_secret(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("INFO")
    caplog.handler.addFilter(logs.ScrubFilter())
    worker, store, target, sources, clock = make(tmp_path)
    target.results.append(RuntimeError("https://x/?api_key=SECRET"))
    jid = enqueue(store, sources, "danbooru", "1")
    assert worker.run_once() is True
    job = store.get(jid)
    assert job is not None
    assert job.state == "failed"
    assert job.error == "unexpected error (RuntimeError)"
    assert "SECRET" not in (job.error or "")
    assert "SECRET" not in caplog.text


def test_missing_snapshot_refetches(tmp_path: Path) -> None:
    worker, store, target, sources, clock = make(tmp_path)
    target.results.append(SaveError("download_failed", "boom", 502))
    jid = enqueue(store, sources, "danbooru", "1")
    assert worker.run_once() is True
    assert sources["danbooru"].calls == []
    job = store.get(jid)
    assert job is not None
    assert job.state == "failed"
    store.retry(jid)
    clock.advance(2.0)
    assert worker.run_once() is True
    assert sources["danbooru"].calls == ["1"]
    job = store.get(jid)
    assert job is not None
    assert job.state == "done"


def test_source_error_on_refetch_fails_job(tmp_path: Path) -> None:
    worker, store, target, sources, clock = make(tmp_path)
    target.results.append(SaveError("download_failed", "boom", 502))
    jid = enqueue(store, sources, "danbooru", "1")
    assert worker.run_once() is True
    store.retry(jid)
    clock.advance(2.0)
    del sources["danbooru"].posts["1"]
    assert worker.run_once() is True
    job = store.get(jid)
    assert job is not None
    assert job.state == "failed"
    assert job.error == "post not found"


def test_resume_after_restart(tmp_path: Path) -> None:
    worker, store, target, sources, clock = make(tmp_path)
    jid1 = enqueue(store, sources, "danbooru", "1")
    jid2 = enqueue(store, sources, "danbooru", "2")
    store.mark_running(jid1)
    worker2 = JobWorker(
        tmp_path / "p.db",
        sources,  # type: ignore[arg-type]
        {"stash": target},
        interval_s=2.0,
        clock=clock,
    )
    assert worker2.recover() == 1
    assert worker2.run_once() is True
    clock.advance(2.0)
    assert worker2.run_once() is True
    job1 = store.get(jid1)
    job2 = store.get(jid2)
    assert job1 is not None
    assert job1.state == "done"
    assert job2 is not None
    assert job2.state == "done"


def test_startup_hook_failure_does_not_abort(tmp_path: Path) -> None:
    called: list[str] = []

    def good_hook() -> None:
        called.append("ran")

    def bad_hook() -> None:
        raise ZeroDivisionError

    path = tmp_path / "p.db"
    init_db(path)
    fs = FakeSource("danbooru")
    for pid in ("1", "2", "3"):
        fs.posts[pid] = _make_post("danbooru", pid)
    worker = JobWorker(
        path,
        {"danbooru": fs},  # type: ignore[arg-type]
        {},
        startup_hooks=[bad_hook, good_hook],
    )
    worker.recover()
    assert called == ["ran"]


def test_throttle_same_site(tmp_path: Path) -> None:
    worker, store, target, sources, clock = make(tmp_path, interval=2.0)
    enqueue(store, sources, "danbooru", "1")
    enqueue(store, sources, "danbooru", "2")
    assert worker.run_once() is True
    assert worker.run_once() is False
    clock.advance(1.9)
    assert worker.run_once() is False
    clock.advance(0.2)
    assert worker.run_once() is True
    job1 = store.get("1")
    job2 = store.get("2")
    assert job1 is not None
    assert job1.state == "done"
    assert job2 is not None
    assert job2.state == "done"


def test_throttle_other_site_not_blocked(tmp_path: Path) -> None:
    worker, store, target, sources, clock = make(
        tmp_path, interval=2.0, sources=("danbooru", "gelbooru")
    )
    sources["gelbooru"].target = "stash"
    enqueue(store, sources, "danbooru", "1")
    enqueue(store, sources, "danbooru", "2")
    enqueue(store, sources, "gelbooru", "1")
    assert worker.run_once() is True
    job1 = store.get("1")
    assert job1 is not None
    assert job1.state == "done"
    assert worker.run_once() is True
    job3 = store.get("3")
    assert job3 is not None
    assert job3.state == "done"
    assert worker.run_once() is False


def test_failed_job_also_throttles(tmp_path: Path) -> None:
    worker, store, target, sources, clock = make(tmp_path, interval=2.0)
    target.results.append(SaveError("download_failed", "boom", 502))
    enqueue(store, sources, "danbooru", "1")
    enqueue(store, sources, "danbooru", "2")
    assert worker.run_once() is True
    assert worker.run_once() is False
    clock.advance(2.0)
    assert worker.run_once() is True


def test_one_download_per_site_with_two_workers(tmp_path: Path) -> None:
    worker, store, target, sources, clock = make(
        tmp_path, interval=0.0, workers=2, sources=("danbooru", "gelbooru")
    )
    sources["gelbooru"].target = "stash"
    enqueue(store, sources, "danbooru", "1")
    enqueue(store, sources, "danbooru", "2")
    enqueue(store, sources, "gelbooru", "1")

    target.release = threading.Event()
    target.entered = threading.Event()
    target.block_sources = {"danbooru"}

    t = threading.Thread(target=worker.run_once)
    t.start()
    assert target.entered.wait(5.0)

    assert worker.run_once() is True
    job3 = store.get("3")
    assert job3 is not None
    assert job3.state == "done"
    job1 = store.get("1")
    assert job1 is not None
    assert job1.state == "running"

    assert worker.run_once() is False

    target.release.set()  # type: ignore[union-attr]
    t.join(timeout=5.0)
    assert not t.is_alive()

    assert target.max_inflight["danbooru"] == 1

    assert worker.run_once() is True
    job2 = store.get("2")
    assert job2 is not None
    assert job2.state == "done"


def test_enqueue_while_job_is_running(tmp_path: Path) -> None:
    worker, store, target, sources, clock = make(tmp_path, interval=0.0)
    enqueue(store, sources, "danbooru", "1")

    target.release = threading.Event()
    target.entered = threading.Event()
    target.block_sources = {"danbooru"}

    t = threading.Thread(target=worker.run_once)
    t.start()
    assert target.entered.wait(5.0)

    post2 = sources["danbooru"].posts["2"]
    store.enqueue(post2, "stash", "danbooru 2", "t")

    states = [j.state for j in store.list()]
    assert states.count("running") == 1
    assert states.count("queued") == 1

    target.release.set()  # type: ignore[union-attr]
    t.join(timeout=5.0)
    assert not t.is_alive()


def test_thread_lifecycle(tmp_path: Path) -> None:
    worker, store, target, sources, clock = make(tmp_path, interval=0.0)
    worker.start()
    jid = enqueue(store, sources, "danbooru", "1")
    worker.wake()

    for _ in range(250):
        job = store.get(jid)
        if job is not None and job.state == "done":
            break
        time.sleep(0.02)
    assert job is not None
    assert job.state == "done"

    worker.stop()
    remaining = [t for t in threading.enumerate() if t.name.startswith("pearlie-job")]
    assert remaining == []
