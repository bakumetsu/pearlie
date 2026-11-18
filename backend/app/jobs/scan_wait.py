"""One Komga scan per library after a quiet period, then a check for each saved book."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol

from app.bookserver.base import BookServerError
from app.jobs.store import JobStore
from app.models import Problem
from app.targets.komga import scan_failed_notice, waiting_for_komga_notice
from app.targets.stash import PendingScan

logger = logging.getLogger("pearlie.komga")

MAX_HOLD_S = 300.0
VERIFY_DELAYS_S = (3.0, 5.0, 10.0, 20.0, 30.0, 60.0)
EXTRA_SCAN_AFTER_TRY = 3

FinishSaved = Callable[[str, str, list[Problem], str | None, str | None], None]


class ScanTarget(Protocol):
    def scan(self, library_id: str) -> None: ...

    def find_books(self, library_id: str, books: dict[str, PendingScan]) -> set[str]: ...


@dataclass
class _Batch:
    due: float
    first: float
    jobs: dict[str, tuple[str, PendingScan]] = field(default_factory=dict)


class ScanWait:
    """Holds saved files per library; a quiet library gets one scan, then the check."""

    def __init__(
        self,
        target: ScanTarget,
        store: JobStore,
        finish: FinishSaved,
        wait_s: Callable[[], float] = lambda: 10.0,
        clock: Callable[[], float] = time.monotonic,
        delays: tuple[float, ...] = VERIFY_DELAYS_S,
        max_hold_s: float = MAX_HOLD_S,
    ) -> None:
        self._target = target
        self._store = store
        self._finish = finish
        self._wait_s = wait_s
        self._clock = clock
        self._delays = delays
        self._max_hold = max_hold_s
        self._batches: dict[str, _Batch] = {}
        self._cond = threading.Condition()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._fires: list[threading.Thread] = []

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="pearlie-scan-wait", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()
        with self._cond:
            self._cond.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None
        for t in self._fires:
            t.join(timeout=timeout)
        self._fires.clear()

    def add(
        self, job_id: str, source_id: str, pending: PendingScan, wait_s: float | None = None
    ) -> None:
        """Put a placed file in its library batch and restart that library's timer."""
        wait = max(0.0, self._wait_s() if wait_s is None else wait_s)
        lib = pending.library_id
        with self._cond:
            now = self._clock()
            batch = self._batches.get(lib)
            if batch is None:
                batch = self._batches[lib] = _Batch(due=now, first=now)
                armed = True
            else:
                armed = False
            batch.jobs[job_id] = (source_id, pending)
            cap = batch.first + self._max_hold
            batch.due = min(now + wait, cap)
            capped = now + wait > cap
            due_in = batch.due - now
            ids = list(batch.jobs)
            count = len(ids)
            self._cond.notify_all()
        if capped:
            logger.info("KOMGA scan wait hold cap reached library=%s", lib)
        logger.info(
            "KOMGA scan wait %s library=%s due_in=%.0fs jobs=%d",
            "armed" if armed else "restarted",
            lib,
            due_in,
            count,
        )
        try:
            due_at = datetime.now(UTC) + timedelta(seconds=due_in)
            self._store.set_scan_due(ids, due_at)
        except Exception as e:
            logger.warning("KOMGA scan due write failed: %s", type(e).__name__)

    def _pop_due(self) -> list[tuple[str, _Batch]]:
        with self._cond:
            now = self._clock()
            due = [(lib, b) for lib, b in self._batches.items() if b.due <= now]
            for lib, _b in due:
                del self._batches[lib]
            return due

    def run_due(self) -> int:
        """Fire every batch that is due, in this thread. Returns how many fired."""
        due = self._pop_due()
        for lib, batch in due:
            self._fire(lib, batch)
        return len(due)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                for lib, batch in self._pop_due():
                    t = threading.Thread(
                        target=self._fire_safe,
                        args=(lib, batch),
                        name="pearlie-scan-fire",
                        daemon=True,
                    )
                    self._fires = [x for x in self._fires if x.is_alive()]
                    self._fires.append(t)
                    t.start()
                with self._cond:
                    if self._stop.is_set():
                        break
                    now = self._clock()
                    nexts = [b.due - now for b in self._batches.values()]
                    self._cond.wait(min(1.0, max(0.05, min(nexts))) if nexts else 1.0)
            except Exception as e:
                logger.error("scan wait loop: %s", type(e).__name__)
                self._stop.wait(1.0)

    def _fire_safe(self, lib: str, batch: _Batch) -> None:
        try:
            self._fire(lib, batch)
        except Exception as e:
            logger.error("KOMGA scan fire failed library=%s: %s", lib, type(e).__name__)

    def _label(self) -> str:
        return getattr(self._target, "label", "Komga")

    def _end(self, job_id: str, source_id: str, extra: list[Problem]) -> None:
        """End one job Done through the shared helper; a removed job is skipped."""
        job = self._store.get(job_id)
        if job is None:
            return
        self._finish(job_id, source_id, [*job.notices, *extra], job.dest_path, None)

    def _fire(self, library_id: str, batch: _Batch) -> None:
        live = {jid: v for jid, v in batch.jobs.items() if self._store.get(jid) is not None}
        if not live:
            return
        ids = list(live)
        self._store.set_verifying(ids)
        waited = self._clock() - batch.first
        logger.info(
            "KOMGA scan requested library=%s books=%d waited=%.0fs", library_id, len(ids), waited
        )
        try:
            self._target.scan(library_id)
        except BookServerError as e:
            logger.warning(
                "%s scan failed code=%s status=%s", self._label(), e.code, e.status
            )
            for jid, (src, _p) in live.items():
                self._end(jid, src, [scan_failed_notice(self._label())])
            return

        pending = dict(live)
        any_found = False
        extra_scan = False
        for attempt, delay in enumerate(self._delays, 1):
            if self._stop.wait(delay):
                return  # shutdown: the jobs stay `verifying`, recover() re-arms them
            for jid in [j for j in pending if self._store.get(j) is None]:
                del pending[jid]
            if not pending:
                return
            try:
                found = self._target.find_books(
                    library_id, {jid: p for jid, (_s, p) in pending.items()}
                )
            except BookServerError as e:
                logger.warning("KOMGA verify failed code=%s status=%s", e.code, e.status)
                break
            for jid in found & set(pending):
                src, p = pending.pop(jid)
                logger.info("KOMGA source=%s verified path=%s", src, p.komga_path)
                self._end(jid, src, [])
                any_found = True
            if not pending:
                return
            if attempt == EXTRA_SCAN_AFTER_TRY and not any_found and not extra_scan:
                extra_scan = True
                logger.info("KOMGA scan retry library=%s", library_id)
                try:
                    self._target.scan(library_id)
                except BookServerError as e:
                    logger.warning(
                        "%s scan failed code=%s status=%s", self._label(), e.code, e.status
                    )
        for jid, (src, p) in pending.items():
            logger.warning("KOMGA source=%s book not found in Komga path=%s", src, p.komga_path)
            self._end(jid, src, [waiting_for_komga_notice(p.komga_path)])
