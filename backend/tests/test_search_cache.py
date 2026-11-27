"""Tests for the site search answer cache and its use in /api/search."""

from __future__ import annotations

import threading

import httpx
import pytest

from app.search_cache import SearchCache
from app.sources.base import SearchPage
from tests.test_search_real import load, make_client


class Clock:
    """Fake monotonic clock."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _page() -> SearchPage:
    return SearchPage(posts=[], page=1)


def test_cache_ttl_and_bound():
    """An answer lives for the TTL; the oldest row goes when full."""
    clock = Clock()
    cache = SearchCache(ttl=300.0, max_entries=2, clock=clock)
    cache.put(("a",), _page())
    assert cache.get(("a",)) is not None
    assert cache.get(("b",)) is None
    clock.now = 301.0
    assert cache.get(("a",)) is None
    cache.put(("a",), _page())
    cache.put(("b",), _page())
    cache.put(("c",), _page())
    assert cache.get(("a",)) is None
    assert cache.get(("c",)) is not None


def _counting(tmp_path, status=200):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if status != 200:
            return httpx.Response(status, json={})
        return httpx.Response(200, json=load("search"))

    return make_client(tmp_path, handler), calls


def test_second_identical_search_skips_the_site(tmp_path):
    """Same key within the TTL: one site call; a different key misses."""
    client, calls = _counting(tmp_path)
    url = "/api/search?q=1girl&sources=danbooru&page=1"
    assert client.get(url).status_code == 200
    assert client.get(url).status_code == 200
    assert len(calls) == 1
    client.get("/api/search?q=1girl&sources=danbooru&page=2")
    client.get("/api/search?q=2girls&sources=danbooru&page=1")
    assert len(calls) == 3


def test_search_expires_after_ttl(tmp_path):
    """After the TTL the site is called again."""
    client, calls = _counting(tmp_path)
    clock = Clock()
    client.app.state.search_cache = SearchCache(clock=clock)  # pyright: ignore[reportAttributeAccessIssue]
    url = "/api/search?q=1girl&sources=danbooru"
    client.get(url)
    clock.now = 10.0
    client.get(url)
    assert len(calls) == 1
    clock.now = 601.0
    client.get(url)
    assert len(calls) == 2


def test_errors_are_not_cached(tmp_path):
    """A rate_limited answer is retried on the next search."""
    client, calls = _counting(tmp_path, status=429)
    url = "/api/search?q=1girl&sources=danbooru"
    client.get(url)
    client.get(url)
    assert len(calls) == 2


def test_library_sources_are_not_cached(tmp_path):
    """Stash and Stump are not sites: nothing of them goes in the cache."""
    client, _calls = _counting(tmp_path)
    client.get("/api/search?q=x&sources=stash_images")
    cache = getattr(client.app.state, "search_cache", None)  # pyright: ignore[reportAttributeAccessIssue]
    assert cache is None or cache._rows == {}  # pyright: ignore[reportPrivateUsage]


def test_get_or_join_second_request_joins_running_call():
    """A request for a key during a running call starts no second call and gets its answer."""
    cache = SearchCache()
    started, release = threading.Event(), threading.Event()
    calls: list[int] = []
    page = _page()

    def slow() -> SearchPage:
        calls.append(1)
        started.set()
        release.wait(5)
        return page

    out: list[SearchPage] = []
    t1 = threading.Thread(target=lambda: out.append(cache.get_or_join(("k",), slow)))
    t1.start()
    assert started.wait(5)

    def second() -> SearchPage:
        calls.append(2)
        return _page()

    t2 = threading.Thread(target=lambda: out.append(cache.get_or_join(("k",), second)))
    t2.start()
    release.set()
    t1.join(5)
    t2.join(5)
    assert calls == [1]
    assert out == [page, page]
    assert cache.get(("k",)) is page


def test_get_or_join_error_is_shared_and_not_stored():
    """A failed call is not cached and leaves no running entry; the next call tries again."""
    cache = SearchCache()

    def boom() -> SearchPage:
        raise RuntimeError("x")

    with pytest.raises(RuntimeError):
        cache.get_or_join(("k",), boom)
    assert cache.get(("k",)) is None
    page = _page()
    assert cache.get_or_join(("k",), lambda: page) is page


def test_default_ttl_is_ten_minutes():
    """An answer lives 10 minutes by default."""
    clock = Clock()
    cache = SearchCache(clock=clock)
    cache.put(("a",), _page())
    clock.now = 599.0
    assert cache.get(("a",)) is not None
    clock.now = 601.0
    assert cache.get(("a",)) is None
