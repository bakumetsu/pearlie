"""Async slot scheduler for web image fetches (D-21 amendment A1).

Per site and image host class (`t` thumbs and covers, `i` full pages) there is one priority
queue and an adaptive number of fetch slots: they ramp up on clean fetches and drop to one on
403/429/Retry-After or a run of slow fetches. The fetch itself stays sync (threadpool).
"""

from __future__ import annotations

import asyncio
import heapq
import itertools
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Literal

logger = logging.getLogger("pearlie.image_slots")

Prio = Literal["focus", "cover", "prefetch"]
HostClass = Literal["t", "i"]
RANK: dict[str, int] = {"focus": 0, "cover": 1, "prefetch": 2}
START_SLOTS: dict[str, int] = {"t": 4, "i": 2}
DEFAULT_CEILING: dict[str, int] = {"t": 8, "i": 4}
RAMP_EVERY = 10
RECOVER_EVERY = 30
RAMP_BLOCK_S = 600.0
BACKOFF_PAUSE_S = 2.0
MAX_PAUSE_S = 60.0
SLOW_S = 8.0
SLOW_RUN = 3
WAIT_CAP_S = 20.0
POLL_S = 0.25
STALE_GRANT_S = 180.0  # a slot never finished (stream never started) is taken back


class Busy(Exception):
    """The queue wait went over the cap."""


class Gone(Exception):
    """The client left while the request waited."""


def parse_prio(value: str | None, default: Prio) -> Prio:
    return value if value in RANK else default  # type: ignore[return-value]


@dataclass(order=True)
class _Entry:
    rank: int
    seq: int
    future: asyncio.Future[Slot] = field(compare=False)
    cancelled: bool = field(default=False, compare=False)


class Slot:
    """One granted fetch slot. `finish` is idempotent and must run on every path."""

    def __init__(self, limiter: Limiter, clock: Callable[[], float]) -> None:
        self._limiter = limiter
        self._clock = clock
        self.started = clock()
        self.done = False

    def finish(self, status: int | None = None, retry_after: float | None = None) -> None:
        """Free the slot; `status` is the site's answer (None: aborted, not counted)."""
        if self.done:
            return
        self.done = True
        self._limiter._release(self, status, retry_after, self._clock() - self.started)


class Limiter:
    """Slots and queue of one (site, host class)."""

    def __init__(
        self,
        host_class: str,
        ceiling: int | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.host_class = host_class
        self.start = START_SLOTS[host_class]
        self.ceiling = max(1, ceiling if ceiling is not None else DEFAULT_CEILING[host_class])
        self.slots = min(self.start, self.ceiling)
        self._clock = clock
        self._heap: list[_Entry] = []
        self._seq = itertools.count()
        self._active: set[Slot] = set()
        self._clean = 0
        self._slow = 0
        self._pause_until = 0.0
        self._ramp_blocked_until = 0.0

    @property
    def in_flight(self) -> int:
        return len(self._active)

    def set_ceiling(self, ceiling: int) -> None:
        self.ceiling = max(1, ceiling)
        self.slots = min(self.slots, self.ceiling)

    def _dispatch(self) -> None:
        now = self._clock()
        for slot in [s for s in self._active if now - s.started > STALE_GRANT_S]:
            logger.warning("slot reclaimed host=%s", self.host_class)
            slot.finish(None)
        if now < self._pause_until:
            return
        while self._heap and len(self._active) < self.slots:
            entry = heapq.heappop(self._heap)
            if entry.cancelled or entry.future.done():
                continue
            slot = Slot(self, self._clock)
            self._active.add(slot)
            entry.future.set_result(slot)

    def _release(
        self, slot: Slot, status: int | None, retry_after: float | None, elapsed: float
    ) -> None:
        self._active.discard(slot)
        if status is not None:
            self._record(status, retry_after, elapsed)
        self._dispatch()

    def _record(self, status: int, retry_after: float | None, elapsed: float) -> None:
        now = self._clock()
        if status in (403, 429) or retry_after is not None:
            pause = BACKOFF_PAUSE_S
            if retry_after is not None:
                pause = min(MAX_PAUSE_S, max(pause, retry_after))
            self.slots = 1
            self._pause_until = now + pause
            self._ramp_blocked_until = now + RAMP_BLOCK_S
            self._clean = self._slow = 0
            logger.warning("backoff host=%s status=%d pause=%.0fs", self.host_class, status, pause)
            return
        if status >= 400:
            return
        if elapsed > SLOW_S:
            self._slow += 1
            self._clean = 0
            if self._slow >= SLOW_RUN and self.slots > 1:
                self.slots = 1
                self._slow = 0
                logger.warning("slow spell host=%s: one slot", self.host_class)
            return
        self._slow = 0
        self._clean += 1
        every = RECOVER_EVERY if now < self._ramp_blocked_until else RAMP_EVERY
        if self._clean >= every and self.slots < self.ceiling:
            self.slots += 1
            self._clean = 0

    async def acquire(
        self,
        prio: str,
        gone: Callable[[], Awaitable[bool]],
        wait_cap: float = WAIT_CAP_S,
    ) -> Slot:
        """Wait for a slot by priority; Gone if the client left, Busy after the wait cap."""
        loop = asyncio.get_running_loop()
        entry = _Entry(RANK.get(prio, 0), next(self._seq), loop.create_future())
        heapq.heappush(self._heap, entry)
        self._dispatch()
        deadline = loop.time() + wait_cap
        try:
            while not entry.future.done():
                left = deadline - loop.time()
                if left <= 0:
                    raise Busy
                await asyncio.wait({entry.future}, timeout=min(POLL_S, left))
                if entry.future.done():
                    break
                self._dispatch()
                if await gone():
                    raise Gone
            return entry.future.result()
        except BaseException:
            entry.cancelled = True
            if entry.future.done() and not entry.future.cancelled():
                entry.future.result().finish(None)  # granted in the same instant: give it back
            else:
                entry.future.cancel()
            raise


class SlotScheduler:
    """All limiters of the app, keyed by site and host class."""

    def __init__(self, ceilings: Callable[[str], int | None] | None = None) -> None:
        self._ceilings = ceilings
        self._limiters: dict[tuple[str, str], Limiter] = {}

    def limiter(self, site: str, host_class: str) -> Limiter:
        key = (site, host_class)
        lim = self._limiters.get(key)
        ceiling = self._ceilings(host_class) if self._ceilings else None
        if lim is None:
            lim = self._limiters[key] = Limiter(host_class, ceiling)
        elif ceiling is not None and ceiling != lim.ceiling:
            lim.set_ceiling(ceiling)
        return lim
