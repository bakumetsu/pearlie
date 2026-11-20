"""Author on the Stump book and series detail."""

from __future__ import annotations

from app.bookserver.base import BookDTO, SeriesDTO
from app.bookserver.map import book_detail, series_detail


def _book(title: str, authors: list[str] | None = None) -> BookDTO:
    return BookDTO("b1", "l", "s1", title, title, "/p", "2026-01-01", authors=authors or [])


def test_book_author_prefers_author_field_then_title_artist() -> None:
    assert book_detail(_book("[Group (Artist)] T", ["Writer"])).author == "Writer"
    assert book_detail(_book("[Group (Artist)] T")).author == "Artist"
    assert book_detail(_book("T", ["Writer"])).author == "Writer"
    assert book_detail(_book("T")).author == ""


def test_series_author_from_title_prefix() -> None:
    s = SeriesDTO("s1", "l", "s", "[Solo] S", "/p", "2026-01-01")
    assert series_detail(s, []).author == "Solo"
    s2 = SeriesDTO("s1", "l", "s", "S", "/p", "2026-01-01")
    assert series_detail(s2, []).author == ""
