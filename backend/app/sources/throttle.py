from __future__ import annotations

import threading
import time
from collections.abc import Callable


class Throttle:
    """Enforces a minimum interval between successive wait() calls."""

    def __init__(
        self,
        min_interval: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._next_at: float = 0.0

    def wait(self) -> None:
        """Block until at least min_interval has passed since the last wait()."""
        with self._lock:
            now = self._clock()
            start = max(now, self._next_at)
            if start > now:
                self._sleep(start - now)
            self._next_at = start + self._min_interval
