"""Server-neutral mappers: book-server DTOs to API models. Media paths keep the `stump` segment."""

from __future__ import annotations

from app.bookserver.base import BookDTO, SeriesDTO
from app.models import LibraryItem, LibraryItemDetail, Problem, Tag

_MEDIA = "/api/media/stump"


def book_item(b: BookDTO) -> LibraryItem:
    return LibraryItem(
        kind="book",
        id=b.id,
        title=b.title,
        thumb_url=f"{_MEDIA}/books/{b.id}/thumb",
        tags=sorted(b.tags),
        page_count=b.page_count,
        read_page=b.read_page,
        added_at=b.created_at,
    )


def series_item(s: SeriesDTO) -> LibraryItem:
    return LibraryItem(
        kind="series",
        id=s.id,
        title=s.title,
        thumb_url=f"{_MEDIA}/series/{s.id}/thumb",
        book_count=s.book_count,
        read_count=s.read_count,
        tags=sorted(s.tags),
        added_at=s.created_at,
    )


def book_detail(b: BookDTO) -> LibraryItemDetail:
    return LibraryItemDetail(
        kind="book",
        id=b.id,
        title=b.title,
        thumb_url=f"{_MEDIA}/books/{b.id}/thumb",
        tags=[Tag(name=t) for t in sorted(b.tags)],
        page_count=b.page_count,
        read_page=b.read_page,
        page_url=f"{_MEDIA}/books/{b.id}/pages/{{n}}",
        page_thumb_url=f"{_MEDIA}/books/{b.id}/pages/{{n}}/thumb",
        added_at=b.created_at,
    )


def series_detail(s: SeriesDTO, books: list[BookDTO], truncated: bool = False) -> LibraryItemDetail:
    return LibraryItemDetail(
        kind="series",
        id=s.id,
        title=s.title,
        thumb_url=f"{_MEDIA}/series/{s.id}/thumb",
        book_count=s.book_count,
        read_count=s.read_count,
        tags=[Tag(name=t) for t in sorted(s.tags)],
        inherited_tags=[
            Tag(name=t) for t in sorted({t for b in books for t in b.tags} - set(s.tags))
        ],
        books=[book_item(b) for b in books],
        notice=(
            Problem(code="truncated", message="Showing the first 10,000 books")
            if truncated
            else None
        ),
        added_at=s.created_at,
    )
