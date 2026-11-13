"""Per-site rate throttle with exponential back-off and ease-in."""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

logger = logging.getLogger("pearlie.throttle")

MAX_WAIT: float = 300.0
EASE_AFTER: int = 10
DEFAULT_PACE: dict[str, float] = {
    "danbooru": 1.0,
    "gelbooru": 1.0,
    "rule34": 1.0,
    "nhentai": 2.0,
}


class Throttle:
    """Thread-safe per-site pacing with exponential back-off."""

    def __init__(
        self,
        min_interval: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        site: str = "",
    ) -> None:
        self._site = site
        self._user: float = min_interval
        self._current: float = min_interval
        self._clean: int = 0
        self._next_at: float = 0.0
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()

    def reserve(self, floor: float = 0.0) -> float:
        """Take the next slot and return the seconds to wait (the caller sleeps).

        `floor` spaces the slot at least that far from the previous one.
        """
        with self._lock:
            now = self._clock()
            start = max(now, self._next_at)
            self._next_at = start + max(self._current, floor)
        return max(0.0, start - now)

    def wait(self) -> None:
        """Block until the next slot, then advance."""
        delay = self.reserve()
        if delay > 0:
            logger.debug("THROTTLE site=%s wait=%.1fs", self._site, delay)
            self._sleep(delay)

    def report(self, status: int, retry_after: float | None = None) -> None:
        """Record a response; raise pace on 429/503, ease on success."""
        with self._lock:
            if status in (429, 503):
                self._clean = 0
                if retry_after is not None:
                    new = min(MAX_WAIT, max(0.0, retry_after))
                else:
                    new = min(MAX_WAIT, (self._current or 1.0) * 2)
                self._current = max(self._user, new)
                self._next_at = max(self._next_at, self._clock() + self._current)
                logger.warning(
                    "THROTTLE site=%s backoff status=%d retry_after=%s wait=%.1fs",
                    self._site,
                    status,
                    "none" if retry_after is None else f"{retry_after:.1f}s",
                    self._current,
                )
            else:
                self._clean += 1
                if self._clean >= EASE_AFTER:
                    self._current = max(self._user, self._current / 2)
                    self._clean = 0

    @property
    def backing_off(self) -> bool:
        return self._current > self._user

    def set_interval(self, v: float) -> None:
        """Change the user-set base interval."""
        with self._lock:
            self._user = v
            if not self.backing_off:
                self._current = v
            else:
                self._current = max(self._current, v)

    @property
    def interval(self) -> float:
        return self._user
