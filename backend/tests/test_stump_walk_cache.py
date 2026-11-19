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


def test_list_deleted_walk_is_cached() -> None:
    server, mock = _server([stump_mock.book(7, gone=True)])
    server.list_deleted("books", "L1")
    server.list_deleted("books", "L1")
    assert _media_calls(mock) == 1
    server.purge_deleted("L1")
    server.list_deleted("books", "L1")
    assert _media_calls(mock) == 2
