"""Job worker."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

from app import logs
from app.jobs.store import JobStore
from app.sources.base import Post, Source, SourceError
from app.targets.stash import SaveError, SaveResult

logger = logging.getLogger("pearlie.jobs")


class SaveTarget(Protocol):
    def save(self, post: Post, tags: list[str]) -> SaveResult: ...


class JobWorker:
    def __init__(
        self,
        db_path: Path,
        sources: dict[str, Source],
        targets: dict[str, SaveTarget],
        interval_s: float = 2.0,
        clock: Callable[[], float] = time.monotonic,
        workers: int = 1,
        startup_hooks: Sequence[Callable[[], object]] = (),
    ) -> None:
        self._store = JobStore(db_path)
        self._sources = sources
        self._targets = targets
        self._interval = interval_s
        self._clock = clock
        self._workers = workers
        self._startup_hooks = startup_hooks
        self._busy: set[str] = set()
        self._next_at: dict[str, float] = {}
        self._lock = threading.Lock()
        self._cond = threading.Condition()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def recover(self) -> int:
        count = self._store.requeue_running()
        for hook in self._startup_hooks:
            try:
                hook()
            except Exception as e:
                logger.warning("startup hook failed: %s", type(e).__name__)
        return count

    def start(self) -> None:
        self.recover()
        self._stop.clear()
        for n in range(self._workers):
            t = threading.Thread(target=self._loop, name=f"pearlie-job-{n}", daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()
        with self._cond:
            self._cond.notify_all()
        for t in self._threads:
            t.join(timeout=timeout)
        self._threads.clear()

    def wake(self) -> None:
        with self._cond:
            self._cond.notify_all()

    def _claim(self) -> tuple[str, str] | None:
        with self._lock:
            now = self._clock()
            for job_id, source in self._store.queued():
                if source in self._busy:
                    continue
                if self._next_at.get(source, 0.0) > now:
                    continue
                if self._store.mark_running(job_id):
                    self._busy.add(source)
                    return (job_id, source)
        return None

    def _wait_s(self) -> float:
        with self._lock:
            now = self._clock()
            waits: list[float] = []
            for _job_id, source in self._store.queued():
                if source in self._busy:
                    continue
                waits.append(self._next_at.get(source, 0.0) - now)
            if not waits:
                return 1.0
            return min(1.0, max(0.05, min(waits)))

    def run_once(self) -> bool:
        claimed = self._claim()
        if claimed is None:
            return False
        self._process(*claimed)
        return True

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                if not self.run_once():
                    with self._cond:
                        self._cond.wait(self._wait_s())
            except Exception as e:
                logger.error("worker loop: %s", type(e).__name__)
                with self._cond:
                    self._cond.wait(1.0)

    def _process(self, job_id: str, source_id: str) -> None:
        try:
            self._run(job_id, source_id)
        finally:
            with self._lock:
                self._busy.discard(source_id)
                self._next_at[source_id] = self._clock() + self._interval

    def _end(
        self, job_id: str, state: str, code: str = "", message: str = "", level: int = logging.INFO
    ) -> None:
        extra = f" code={code} message={message}" if code else ""
        logger.log(level, "job=%s end state=%s%s", job_id, state, extra)

    def _run(self, job_id: str, source_id: str) -> None:
        job = self._store.get(job_id)
        token = logs.set_job(job_id, source_id, job.post_id if job else "")
        try:
            target = job.target if job is not None else "?"
            logger.info("job=%s start source=%s target=%s", job_id, source_id, target)
            self._run_job(job_id, source_id)
        finally:
            logs.reset_job(token)

    def _run_job(self, job_id: str, source_id: str) -> None:
        try:
            src = self._sources.get(source_id)
            if src is None:
                self._store.finish(
                    job_id, "failed", error="source is not configured", error_code="no_source"
                )
                self._end(job_id, "failed", "no_source", "source is not configured", logging.ERROR)
                return

            target_id, post_json = self._store.load_post(job_id)
            target = self._targets.get(target_id)
            if target is None:
                self._store.finish(
                    job_id,
                    "failed",
                    error=f"no save target for {target_id} yet",
                    error_code="no_target",
                )
                self._end(
                    job_id, "failed", "no_target", f"no save target for {target_id}", logging.ERROR
                )
                return

            if post_json is None:
                job = self._store.get(job_id)
                if job is None:
                    self._store.finish(
                        job_id, "failed", error="job not found", error_code="unexpected_error"
                    )
                    self._end(job_id, "failed", "unexpected_error", "job not found", logging.ERROR)
                    return
                post = src.get_post(job.post_id)
                self._store.set_post(job_id, post)
            else:
                post = Post.model_validate_json(post_json)

            tags = sorted({tag for group in post.tags.values() for tag in group})
            result = target.save(post, tags)

            if result.status == "saved":
                self._store.finish(
                    job_id, "done", notices=result.notices, library_ref_id=result.image_id
                )
                self._end(job_id, "done", message=f"image={result.image_id}")
            elif result.status == "duplicate":
                error = result.notices[0].message if result.notices else "already saved"
                self._store.finish(
                    job_id,
                    "skipped",
                    error=error,
                    error_code="duplicate",
                    notices=result.notices,
                    library_ref_id=result.image_id,
                )
                self._end(job_id, "skipped", "duplicate", error)
            else:
                self._store.finish(
                    job_id,
                    "failed",
                    error="unexpected save result",
                    error_code="unexpected_error",
                )
                self._end(
                    job_id, "failed", "unexpected_error", "unexpected save result", logging.ERROR
                )

        except (SaveError, SourceError) as e:
            self._store.finish(job_id, "failed", error=e.message, error_code=e.code)
            self._end(job_id, "failed", e.code, e.message, logging.ERROR)
        except Exception as e:
            logger.error("job %s failed: %s", job_id, type(e).__name__, exc_info=True)
            self._store.finish(
                job_id,
                "failed",
                error=f"unexpected error ({type(e).__name__})",
                error_code="unexpected_error",
            )
            self._end(
                job_id, "failed", "unexpected_error", type(e).__name__, logging.ERROR
            )
