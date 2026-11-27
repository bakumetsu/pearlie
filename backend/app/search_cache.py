"""Short memory cache for site search answers, so Back/Forward and reload skip the site call.

Holds the result list only (posts: ids, titles, tags, URLs), never media.
Memory only: it clears on restart. Only good answers go in; an error or
rate_limited answer is never stored.
A call that is running can be joined: a second request for the same key waits for it.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import Future

from app.sources.base import SearchPage

SEARCH_TTL = 10 * 60.0
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
        self._running: dict[tuple, Future[SearchPage]] = {}

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

    def get_or_join(self, key: tuple, fetch: Callable[[], SearchPage]) -> SearchPage:
        """Return the cached answer, join a running call for *key*, or run *fetch* once.

        A good answer is stored. An error from *fetch* is not stored; it reaches the
        caller that ran it and every caller that joined it. Nothing is cached for it.
        """
        with self._lock:
            hit = self._rows.get(key)
            if hit is not None:
                if self._clock() - hit[0] <= self._ttl:
                    self._rows.move_to_end(key)
                    return hit[1]
                del self._rows[key]
            fut = self._running.get(key)
            owner = fut is None
            if fut is None:
                fut = self._running[key] = Future()
        if not owner:
            return fut.result()
        try:
            page = fetch()
        except BaseException as e:
            with self._lock:
                self._running.pop(key, None)
            fut.set_exception(e)
            raise
        with self._lock:
            self._running.pop(key, None)
        self.put(key, page)
        fut.set_result(page)
        return page
