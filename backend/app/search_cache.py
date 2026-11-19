"""Short memory cache for site search answers, so Back/Forward and reload skip the site call.

Holds the result list only (posts: ids, titles, tags, URLs), never media.
Memory only: it clears on restart. Only good answers go in; an error or
rate_limited answer is never stored.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable

from app.sources.base import SearchPage

SEARCH_TTL = 5 * 60.0
MAX_ENTRIES = 200


class SearchCache:
    """Bounded TTL cache; safe to call from several threads."""

    def __init__(
        self,
        ttl: float = SEARCH_TTL,
        max_entries: int = MAX_ENTRIES,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl
        self._max = max_entries
        self._clock = clock
        self._lock = threading.Lock()
        self._rows: OrderedDict[tuple, tuple[float, SearchPage]] = OrderedDict()

    def get(self, key: tuple) -> SearchPage | None:
        """Return the stored answer, or None when it is missing or older than the TTL."""
        with self._lock:
            hit = self._rows.get(key)
            if hit is None:
                return None
            if self._clock() - hit[0] > self._ttl:
                del self._rows[key]
                return None
            self._rows.move_to_end(key)
            return hit[1]

    def put(self, key: tuple, page: SearchPage) -> None:
        """Store a good answer; the oldest rows go when the cache is full."""
        with self._lock:
            self._rows[key] = (self._clock(), page)
            self._rows.move_to_end(key)
            while len(self._rows) > self._max:
                self._rows.popitem(last=False)
