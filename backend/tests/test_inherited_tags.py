"""Series inherited tags and the safe-mode tag helper."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from starlette.requests import Request

from app.api.media_web_pages import _apply_safe_tags, build_book
from app.bookserver.base import BookDTO, SeriesDTO
from app.bookserver.map import book_detail, series_detail
from app.filters.rules import RuleSet
from app.filters.safe_mode import visible_tags
from app.models import Tag
from tests.test_safe_mode_filter import _setting
from tests.test_search_rules_real import _client, _post, _put_rules


def _book(id: str, tags: list[str]) -> BookDTO:
    return BookDTO(id, "l", "s1", id, id, "/p", "2026-01-01", tags=tags)


def _series(tags: list[str]) -> SeriesDTO:
    return SeriesDTO("s1", "l", "s", "S", "/p", "2026-01-01", tags=tags)


def test_inherited_is_union_minus_own_sorted() -> None:
    books = [_book("b1", ["b", "own"]), _book("b2", ["a", "b"])]
    detail = series_detail(_series(["own"]), books)
    assert [t.name for t in detail.tags] == ["own"]
    assert [t.name for t in detail.inherited_tags] == ["a", "b"]


def test_inherited_empty_without_books_and_for_book() -> None:
    assert series_detail(_series(["x"]), []).inherited_tags == []
    assert book_detail(_book("b1", ["x"])).inherited_tags == []


def _rules(warn: list[str]) -> RuleSet:
    return RuleSet(version=1, reject=[], warn=warn, require=[], mapping=[])


def test_visible_tags_drops_warn_only_in_safe_mode() -> None:
    tags = [Tag(name="plain"), Tag(name="warnme"), Tag(name="x", scope="artist")]
    rules = _rules(["warnme", "artist:x"])
    assert [t.name for t in visible_tags(tags, rules, True, False)] == ["plain"]
    assert visible_tags(tags, rules, False, False) == tags
    assert visible_tags(tags, rules, True, True) == tags


def test_visible_tags_keeps_all_with_require_rule() -> None:
    rules = RuleSet(version=1, reject=[], warn=[], require=["need"], mapping=[])
    tags = [Tag(name="a"), Tag(name="b")]
    assert visible_tags(tags, rules, True, False) == tags


def test_web_book_route_hides_warn_tags_in_safe_mode(tmp_path: Path) -> None:
    client: TestClient = _client(tmp_path, [_post(1, {"general": ["plain", "warnme"]})])
    _put_rules(client, reject=[], warn=["warnme"])
    post = _post(1, {"general": ["plain", "warnme"]})

    def request() -> Request:
        return Request(
            {
                "type": "http",
                "headers": [],
                "query_string": b"",
                "app": client.app,
            }
        )

    data = build_book(post, "stash")
    _apply_safe_tags(request(), data)
    assert data.tags == {"general": ["plain", "warnme"]}
    _setting(client, "options.desktop.sfw", "1")
    data = build_book(post, "stash")
    _apply_safe_tags(request(), data)
    assert data.tags == {"general": ["plain"]}
    assert [t.name for t in data.item.tags] == ["plain"]
