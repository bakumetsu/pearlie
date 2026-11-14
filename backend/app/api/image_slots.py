"""Async slot scheduler for web image fetches (D-21 amendment A1).

Per site and image host class (`t` thumbs and covers, `i` full images and pages) there is one
priority queue and an adaptive number of fetch slots. The slots start at the setting "images at a
time per site" (default 10, 1-16). On 403/429/503 or Retry-After the site gets a pause and falls
back to the browser level (6); a further error during the next run drops it lower; clean fetches
bring it back to the setting slowly. The fetch itself stays sync (threadpool).
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
DEFAULT_SLOTS = 10
MIN_SLOTS = 1
MAX_SLOTS = 16
BROWSER_LEVEL = 6  # what a browser opens per host: the fallback level
RAMP_EVERY = 10
RECOVER_EVERY = 30
RAMP_BLOCK_S = 600.0
BACKOFF_PAUSE_S = 2.0
MAX_PAUSE_S = 60.0
SLOW_S = 8.0
SLOW_RUN = 3
WAIT_CAP_S = 20.0
POLL_S = 0.25
CEILING_TTL_S = 5.0
STREAM_LIMIT_S = 300.0  # one image stream may run this long in all
STALE_GRANT_S = 600.0  # a slot never finished (stream never started) is taken back


class Busy(Exception):
    """The queue wait went over the cap."""


class StreamCut(Exception):
    """A strict body was cut short; raised so the client sees a failed transfer."""


class Gone(Exception):
    """The client left while the request waited."""


def clamp_slots(value: int | None) -> int:
    return DEFAULT_SLOTS if value is None else max(MIN_SLOTS, min(MAX_SLOTS, value))


def parse_prio(value: str | None, default: Prio) -> Prio:
    return value if value in RANK else default  # type: ignore[return-value]


@dataclass(order=True)
class _Entry:
    rank: int
    seq: int
    future: asyncio.Future[Slot] = field(compare=False)
    cancelled: bool = field(default=False, compare=False)


def _on_loop(loop: asyncio.AbstractEventLoop) -> bool:
    try:
        return asyncio.get_running_loop() is loop
    except RuntimeError:
        return False


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
        elapsed = self._clock() - self.started
        loop = self._limiter._loop
        if loop is not None and loop.is_running() and not _on_loop(loop):
            # the response body iterates in a worker thread; limiter state belongs to the loop
            loop.call_soon_threadsafe(self._limiter._release, self, status, retry_after, elapsed)
            return
        self._limiter._release(self, status, retry_after, elapsed)


class Limiter:
    """Slots and queue of one (site, host class)."""

    def __init__(
        self,
        host_class: str,
        ceiling: int | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.host_class = host_class
        self.ceiling = clamp_slots(ceiling)
        self.slots = self.ceiling
        self._clock = clock
        self._loop: asyncio.AbstractEventLoop | None = None
        self._heap: list[_Entry] = []
        self._seq = itertools.count()
        self._active: set[Slot] = set()
        self._clean = 0
        self._slow = 0
        self._pause_until = 0.0
        self._ramp_blocked_until = 0.0
        self._fell_back = False

    @property
    def in_flight(self) -> int:
        return len(self._active)

    def set_ceiling(self, ceiling: int) -> None:
        self.ceiling = clamp_slots(ceiling)
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
        if status in (403, 429, 503) or retry_after is not None:
            pause = BACKOFF_PAUSE_S
            if retry_after is not None:
                pause = min(MAX_PAUSE_S, max(pause, retry_after))
            # answers of requests sent before the pause started are one event, not new errors
            fresh = now >= self._pause_until
            if not self._fell_back:
                self.slots = min(self.slots, BROWSER_LEVEL)
                self._fell_back = True
            elif fresh:
                self.slots = max(MIN_SLOTS, self.slots // 2)
            self._pause_until = max(self._pause_until, now + pause)
            self._ramp_blocked_until = now + RAMP_BLOCK_S
            self._clean = self._slow = 0
            logger.warning(
                "backoff host=%s status=%d pause=%.0fs slots=%d",
                self.host_class,
                status,
                pause,
                self.slots,
            )
            return
        if status >= 400:
            return
        if elapsed > SLOW_S:
            self._slow += 1
            self._clean = 0
            if self._slow >= SLOW_RUN and self.slots > MIN_SLOTS:
                self.slots = min(self.slots - 1, BROWSER_LEVEL)
                self._slow = 0
                logger.warning("slow spell host=%s: slots=%d", self.host_class, self.slots)
            return
        self._slow = 0
        self._clean += 1
        every = RECOVER_EVERY if now < self._ramp_blocked_until else RAMP_EVERY
        if self._clean >= every and self.slots < self.ceiling:
            self.slots += 1
            self._clean = 0
            if self.slots >= self.ceiling:
                self._fell_back = False

    async def acquire(
        self,
        prio: str,
        gone: Callable[[], Awaitable[bool]],
        wait_cap: float = WAIT_CAP_S,
    ) -> Slot:
        """Wait for a slot by priority; Gone if the client left, Busy after the wait cap."""
        loop = self._loop = asyncio.get_running_loop()
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

    def __init__(self, ceiling: Callable[[], int | None] | None = None) -> None:
        self._read = ceiling
        self._limiters: dict[tuple[str, str], Limiter] = {}
        self._read_at: tuple[float, int | None] | None = None

    def _ceiling(self) -> int | None:
        """The setting, read at most every CEILING_TTL_S (not one DB read per image)."""
        if self._read is None:
            return None
        now = time.monotonic()
        if self._read_at is None or now - self._read_at[0] >= CEILING_TTL_S:
            self._read_at = (now, self._read())
        return self._read_at[1]

    def limiter(self, site: str, host_class: str) -> Limiter:
        key = (site, host_class)
        lim = self._limiters.get(key)
        ceiling = self._ceiling()
        if lim is None:
            lim = self._limiters[key] = Limiter(host_class, ceiling)
        elif ceiling is not None and clamp_slots(ceiling) != lim.ceiling:
            lim.set_ceiling(ceiling)
        return lim


def scheduler(app) -> SlotScheduler:
    """The app's one scheduler; its ceiling is the stored setting."""
    from app.api.options import images_per_site

    sched = getattr(app.state, "image_slots", None)
    if sched is None:
        sched = app.state.image_slots = SlotScheduler(lambda: images_per_site(app))
    return sched


class SlotBody:
    """Streams an upstream body under a size and time cap; frees response and slot once."""

    def __init__(
        self,
        resp,
        slot: Slot,
        max_bytes: int | None = None,
        time_limit: float = STREAM_LIMIT_S,
        clock: Callable[[], float] = time.monotonic,
        strict: bool = False,
        chunk_size: int | None = None,
        record_status: bool = True,
    ) -> None:
        self._strict = strict
        self._chunk = () if chunk_size is None else (chunk_size,)
        # a long video is slow by nature: its length must not count as a slow spell
        self._record = record_status
        self._resp, self._slot = resp, slot
        self._status = resp.status_code
        self._max_bytes = max_bytes
        self._clock = clock
        self._deadline = clock() + time_limit
        self._complete = False

    def __iter__(self):
        sent = 0
        try:
            for chunk in self._resp.iter_raw(*self._chunk):
                sent += len(chunk)
                if self._max_bytes is not None and sent > self._max_bytes:
                    return self._cut("size limit")
                yield chunk
                if self._clock() > self._deadline:
                    return self._cut("time limit")
            self._complete = True
        finally:
            self.close()

    def _cut(self, why: str) -> None:
        logger.warning("stream cut: %s", why)
        if self._strict:
            raise StreamCut(why)  # headers are sent: abort so no client caches a short body

    def close(self) -> None:
        self._resp.close()
        self._slot.finish(self._status if self._complete and self._record else None)
