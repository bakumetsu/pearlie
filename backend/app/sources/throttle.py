"""Per-site rate throttle with exponential back-off and ease-in."""
from __future__ import annotations

import threading
import time
from collections.abc import Callable

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
    ) -> None:
        self._user: float = min_interval
        self._current: float = min_interval
        self._clean: int = 0
        self._next_at: float = 0.0
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()

    def wait(self) -> None:
        """Block until the next slot, then advance."""
        with self._lock:
            now = self._clock()
            start = max(now, self._next_at)
            self._next_at = start + self._current
        if start > now:
            self._sleep(start - now)

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
