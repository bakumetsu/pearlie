"""In-memory shuffled-DTO cache and pagination helpers for Komga browsing."""

from __future__ import annotations

import random
import threading
import time
from collections import OrderedDict
from collections.abc import Callable

type _Key = tuple[str, str, int]


class ShuffleCache:
    """Small in-memory TTL + LRU cache of shuffled DTO lists.

    A ``threading.Lock`` guards all mutations (including the recency refresh
    performed on reads).  The *clock* parameter is injectable for testing.
    """

    def __init__(
        self,
        max_entries: int = 4,
        ttl_s: float = 600.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_entries: int = max_entries
        self._ttl_s: float = ttl_s
        self._clock: Callable[[], float] = clock
        self._store: OrderedDict[_Key, tuple[list[dict], bool, float]] = OrderedDict()
        self._lock: threading.Lock = threading.Lock()

    def get(self, key: _Key) -> tuple[list[dict], bool] | None:
        """Return the cached value for *key*, or ``None`` if absent/expired.

        Expired entries are evicted on access.  A hit refreshes the entry's
        recency (moves it to the LRU tail).
        """
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, truncated, ts = entry
            if self._clock() - ts >= self._ttl_s:
                del self._store[key]
                return None
            self._store.move_to_end(key)
            return value, truncated

    def put(self, key: _Key, value: list[dict], truncated: bool) -> None:
        """Store *value* under *key*, evicting the LRU entry if over capacity."""
        with self._lock:
            self._store[key] = (value, truncated, self._clock())
            self._store.move_to_end(key)
            while len(self._store) > self._max_entries:
                self._store.popitem(last=False)


def fetch_all(
    fetch_page: Callable[[int, int], dict],
    size: int = 500,
    max_pages: int = 40,
) -> tuple[list[dict], bool]:
    """Fetch every item by paginating through *fetch_page*.

    *fetch_page* receives a 0-based page index and a page size, and returns a
    Komga-style page dict with ``"content"`` (list) and ``"last"`` (bool).
    Returns the accumulated list and whether the result was truncated
    (*max_pages* exhausted without reaching ``"last"``).
    """
    items: list[dict] = []
    truncated = False
    for page in range(max_pages):
        result = fetch_page(page, size)
        items.extend(result["content"])
        if result["last"]:
            break
    else:
        truncated = True
    return items, truncated


def shuffled(items: list[dict], seed: int) -> list[dict]:
    """Return a new list with elements in a deterministic order for *seed*.

    The input list is not mutated.  The same seed always produces the same
    permutation.
    """
    result = list(items)
    random.Random(seed).shuffle(result)
    return result


def page_slice(items: list[dict], page: int, page_size: int) -> tuple[list[dict], int | None]:
    """Return the *page*-th slice (1-based) of *items*.

    Returns the slice and the next page number, or ``None`` when there are no
    further items.
    """
    start = (page - 1) * page_size
    end = start + page_size
    chunk = items[start:end]
    next_page: int | None = page + 1 if end < len(items) else None
    return chunk, next_page
