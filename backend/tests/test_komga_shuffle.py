"""Tests for app.komga_shuffle."""

from __future__ import annotations

from collections.abc import Callable

from app.komga_shuffle import ShuffleCache, fetch_all, page_slice, shuffled


def _make_items(n: int) -> list[dict]:
    """Create *n* dummy DTO dicts with string ids 0..n-1."""
    return [{"id": str(i)} for i in range(n)]


# ---------------------------------------------------------------------------
# shuffled
# ---------------------------------------------------------------------------


def test_shuffled_deterministic_per_seed() -> None:
    items = _make_items(30)
    assert shuffled(items, 42) == shuffled(items, 42)


def test_shuffled_is_permutation() -> None:
    items = _make_items(30)
    result = shuffled(items, 7)
    assert sorted(r["id"] for r in result) == sorted(r["id"] for r in items)


def test_shuffled_does_not_mutate_input() -> None:
    items = _make_items(30)
    original = list(items)
    shuffled(items, 1)
    assert items == original


def test_shuffled_different_seeds_differ() -> None:
    items = _make_items(30)
    assert shuffled(items, 1) != shuffled(items, 2)


# ---------------------------------------------------------------------------
# page_slice
# ---------------------------------------------------------------------------


def test_page_slice_sizes_and_next() -> None:
    items = _make_items(25)
    p1, n1 = page_slice(items, 1, 10)
    p2, n2 = page_slice(items, 2, 10)
    p3, n3 = page_slice(items, 3, 10)
    assert len(p1) == 10
    assert len(p2) == 10
    assert len(p3) == 5
    assert n1 == 2
    assert n2 == 3
    assert n3 is None


def test_page_slice_covers_all_ids_uniquely() -> None:
    items = _make_items(25)
    seen: set[str] = set()
    page = 1
    while True:
        chunk, next_page = page_slice(items, page, 10)
        for item in chunk:
            assert item["id"] not in seen
            seen.add(item["id"])
        if next_page is None:
            break
        page = next_page
    assert seen == {str(i) for i in range(25)}


def test_page_slice_beyond_end() -> None:
    items = _make_items(25)
    chunk, next_page = page_slice(items, 4, 10)
    assert chunk == []
    assert next_page is None


# ---------------------------------------------------------------------------
# ShuffleCache
# ---------------------------------------------------------------------------


def _clock_fn(state: list[float]) -> Callable[[], float]:
    """Return a zero-arg clock that reads from a mutable list."""

    def _clock() -> float:
        return state[0]

    return _clock


def test_cache_put_get_roundtrip() -> None:
    clock = [0.0]
    cache = ShuffleCache(max_entries=4, ttl_s=600.0, clock=_clock_fn(clock))
    cache.put(("a", "b", 1), [{"id": "1"}], False)
    assert cache.get(("a", "b", 1)) == ([{"id": "1"}], False)


def test_cache_ttl_expiry() -> None:
    clock = [0.0]
    cache = ShuffleCache(max_entries=4, ttl_s=10.0, clock=_clock_fn(clock))
    cache.put(("a", "b", 1), [{"id": "1"}], False)
    clock[0] = 11.0
    assert cache.get(("a", "b", 1)) is None


def test_cache_lru_eviction_with_recency_refresh() -> None:
    clock = [0.0]
    cache = ShuffleCache(max_entries=2, ttl_s=600.0, clock=_clock_fn(clock))
    cache.put(("a", "b", 1), [{"id": "1"}], False)
    cache.put(("c", "d", 2), [{"id": "2"}], False)
    # Refresh recency of the first entry.
    cache.get(("a", "b", 1))
    # Adding a third entry must evict ("c","d",2), the LRU one.
    cache.put(("e", "f", 3), [{"id": "3"}], False)
    assert cache.get(("a", "b", 1)) is not None
    assert cache.get(("c", "d", 2)) is None
    assert cache.get(("e", "f", 3)) is not None


# ---------------------------------------------------------------------------
# fetch_all
# ---------------------------------------------------------------------------


def _fake_fetch_page() -> Callable[[int, int], dict]:
    """Build a fetch_page that serves 3 pages of 500, 500, 20 items."""
    pages: list[list[dict]] = [
        [{"id": str(i)} for i in range(500)],
        [{"id": str(i)} for i in range(500, 1000)],
        [{"id": str(i)} for i in range(1000, 1020)],
    ]

    def fetch_page(page: int, size: int) -> dict:
        return {"content": pages[page], "last": page == len(pages) - 1}

    return fetch_page


def test_fetch_all_not_truncated() -> None:
    items, truncated = fetch_all(_fake_fetch_page(), size=500, max_pages=40)
    assert len(items) == 1020
    assert truncated is False


def test_fetch_all_truncated() -> None:
    items, truncated = fetch_all(_fake_fetch_page(), size=500, max_pages=2)
    assert len(items) == 1000
    assert truncated is True
