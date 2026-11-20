"""Stump adapter: the full series walk and the deleted-items walk are cached briefly (T-381)."""

from __future__ import annotations

import httpx
import pytest

from app.bookserver import stump as adapter
from app.bookserver.stump import StumpBookServer
from app.stump import Stump
from tests import stump_mock


def _server(books: list) -> tuple[StumpBookServer, stump_mock.MockStump]:
    mock = stump_mock.MockStump([stump_mock.lib()], [stump_mock.series()], books, None)
    http = httpx.Client(base_url="http://stump", transport=httpx.MockTransport(mock))
    return StumpBookServer(Stump("http://stump", "k", http, sleep=lambda _s: None)), mock


def _media_calls(mock: stump_mock.MockStump) -> int:
    return len([1 for _m, _p, b in mock.calls if b.get("operationName") == "MediaList"])


def test_series_walk_is_cached_and_cleared_by_writes() -> None:
    many = [dict(stump_mock.book(1), id=f"x{i}", name=f"N{i:03}") for i in range(230)]
    server, mock = _server(many)
    first, _ = server.series_books("s1")
    assert len(first) == 230 and _media_calls(mock) == 3
    again, _ = server.series_books("s1")
    assert [b.id for b in again] == [b.id for b in first]
    assert again is not first
    assert _media_calls(mock) == 3  # served from the cache
    server.set_progress("x1", 2, False)
    server.series_books("s1")
    assert _media_calls(mock) == 6  # a write cleared it


def test_series_walk_cache_expires(monkeypatch: pytest.MonkeyPatch) -> None:
    server, mock = _server([stump_mock.book(1)])
    clock = [100.0]
    monkeypatch.setattr(adapter.time, "monotonic", lambda: clock[0])
    server.series_books("s1")
    clock[0] += adapter.WALK_TTL_S + 1
    server.series_books("s1")
    assert _media_calls(mock) == 2


def test_tag_walk_is_cached_ands_tags_and_is_cleared_by_scan() -> None:
    books = [
        dict(stump_mock.book(1), tags=[{"name": "Big_Cat"}, {"name": "b"}]),
        dict(stump_mock.book(2), tags=[{"name": "big cat"}]),
    ]
    server, mock = _server(books)
    assert [b.id for b in server.tagged_books("", ["big cat", "b"])] == ["b1"]
    assert sorted(b.id for b in server.tagged_books("", ["BIG CAT"])) == ["b1", "b2"]
    assert [b.id for b in server.tagged_books("", ["big cat", "-b"])] == ["b2"]
    assert _media_calls(mock) == 1  # one walk, three searches
    server.scan_library("L1")
    server.tagged_books("", ["b"])
    assert _media_calls(mock) == 2


def test_tag_walk_is_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    many = [dict(stump_mock.book(1), id=f"x{i}") for i in range(230)]
    server, mock = _server(many)
    monkeypatch.setattr(adapter, "TAG_WALK_PAGES", 2)
    assert len(server.tagged_books("", ["x"])) == 200
    assert _media_calls(mock) == 2


def test_list_deleted_walk_is_cached() -> None:
    server, mock = _server([stump_mock.book(7, gone=True)])
    server.list_deleted("books", "L1")
    server.list_deleted("books", "L1")
    assert _media_calls(mock) == 1
    server.purge_deleted("L1")
    server.list_deleted("books", "L1")
    assert _media_calls(mock) == 2


def test_sweep_drops_expired_walks(monkeypatch: pytest.MonkeyPatch) -> None:
    server, _ = _server([stump_mock.book(1)])
    clock = [100.0]
    monkeypatch.setattr(adapter.time, "monotonic", lambda: clock[0])
    server.series_books("s1")
    server.series_books("s2")
    assert len(server._walks) == 2
    clock[0] += adapter.WALK_TTL_S + 1
    server.series_books("s3")
    assert list(server._walks) == [("books", "s3")]


def test_trash_delete_and_restore_clear_the_walk_cache(tmp_path) -> None:  # noqa: ANN001
    from typing import Any

    from tests.test_trash_stump import make, setup_lib

    _, _, _, m = setup_lib(tmp_path)
    c = make(tmp_path, m, wait=60.0)  # the debounced scan has not run
    state: Any = c.app.state  # pyright: ignore[reportAttributeAccessIssue]
    walks = state.books._walks
    walks[("books", "S1")] = (adapter.time.monotonic(), ([], False))
    tok = c.delete("/api/library/books/B1").json()["token"]
    assert walks == {}
    walks[("books", "S1")] = (adapter.time.monotonic(), ([], False))
    assert c.post(f"/api/trash/{tok}/restore").status_code == 200
    assert walks == {}
