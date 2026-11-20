"""Stump ratings live in the Pearlie database (Stump has no rating field)."""

from __future__ import annotations

from pathlib import Path

import pytest
from starlette.requests import Request

from app.api import library_stump_real as stump_routes
from app.api.errors import ApiError
from app.bookserver.base import BookDTO
from app.bookserver.map import book_item
from app.config import Settings
from app.db import init_db
from app.main import create_app
from app.models import PatchBody


class _Server:
    def valid_id(self, id: str) -> bool:
        return True

    def get_book(self, id: str) -> BookDTO:
        return BookDTO(id, "l", "s1", id, id, "/p", "2026-01-01")

    get_series = get_book


def _request(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Request:
    db_path = tmp_path / "p.db"
    init_db(db_path)
    app = create_app(
        Settings(
            mode="real",
            db_path=db_path,
            static_dir=tmp_path / "nostatic",
            worker_enabled=False,
            _env_file=None,  # pyright: ignore[reportCallIssue]
        )
    )
    server = _Server()
    monkeypatch.setattr(stump_routes, "book_server_of", lambda app: server)
    monkeypatch.setattr(stump_routes, "get_book", lambda request, id: None)
    return Request({"type": "http", "headers": [], "query_string": b"", "app": app})


def test_patch_saves_rating_and_items_carry_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    req = _request(tmp_path, monkeypatch)
    stump_routes._patch(req, "books", "b1", PatchBody(rating=4))
    assert stump_routes._rating_of(req, "books", "b1") == 4
    assert stump_routes._rating_of(req, "series", "b1") is None
    items = [book_item(_Server().get_book(i)) for i in ("b1", "b2")]
    rated = stump_routes._rated(req, "books", items)
    assert [i.rating for i in rated] == [4, None]


def test_patch_replaces_and_clears_rating(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    req = _request(tmp_path, monkeypatch)
    stump_routes._patch(req, "books", "b1", PatchBody(rating=2))
    stump_routes._patch(req, "books", "b1", PatchBody(rating=5))
    assert stump_routes._rating_of(req, "books", "b1") == 5
    stump_routes._patch(req, "books", "b1", PatchBody(rating=None))
    assert stump_routes._rating_of(req, "books", "b1") is None


def test_patch_without_rating_keeps_it_and_favorite_still_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    req = _request(tmp_path, monkeypatch)
    stump_routes._patch(req, "books", "b1", PatchBody(rating=3))
    stump_routes._patch(req, "books", "b1", PatchBody())
    assert stump_routes._rating_of(req, "books", "b1") == 3
    with pytest.raises(ApiError):
        stump_routes._patch(req, "books", "b1", PatchBody(favorite=True))


class _ProgressServer(_Server):
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, bool]] = []

    def get_book(self, id: str) -> BookDTO:
        return BookDTO(id, "l", "s1", id, id, "/p", "2026-01-01", page_count=5)

    def set_progress(self, book_id: str, page: int, completed: bool) -> None:
        self.calls.append((book_id, page, completed))


def test_progress_route_page_zero_marks_unread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    req = _request(tmp_path, monkeypatch)
    server = _ProgressServer()
    monkeypatch.setattr(stump_routes, "book_server_of", lambda app: server)
    body = stump_routes.ProgressBody
    res = stump_routes.set_progress(req, "b1", body(page=0))
    assert (res.page, res.completed) == (0, False)
    stump_routes.set_progress(req, "b1", body(page=5))
    assert server.calls == [("b1", 0, False), ("b1", 5, True)]
    with pytest.raises(ApiError):
        stump_routes.set_progress(req, "b1", body(page=6))
    with pytest.raises(ApiError):
        stump_routes.set_progress(req, "b1", body(page=-1))
