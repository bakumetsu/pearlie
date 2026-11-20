"""Server-neutral book-library interface: DTOs, errors and the `BookServer` Protocol."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Literal, Protocol

SORT_CREATED_DESC = "created_desc"
SORT_NUMBER_ASC = "number_asc"

Kind = Literal["series", "books"]

# Every `BookServer.kind`: the `target` of saved_items and trash_items rows of a book server.
BOOK_TARGETS = ("stump", "stump")


class BookServerError(Exception):
    """Server-neutral error. Codes: not_found, upstream_error, not_configured, bad_request."""

    def __init__(self, code: str, message: str, status: int) -> None:
        self.code = code
        self.message = message
        self.status = status
        super().__init__(message)


@dataclass(frozen=True)
class LibraryDTO:
    id: str
    name: str
    root: str  # path as the server sees it
    oneshots_dir: str | None = None


@dataclass(frozen=True)
class MetadataPatch:
    """Fields to write; `None` leaves a field alone. The adapter adds the lock flags."""

    title: str | None = None
    summary: str | None = None
    links: list[tuple[str, str]] | None = None
    writers: list[str] | None = None
    tags: list[str] | None = None


@dataclass(frozen=True)
class BookDTO:
    id: str
    library_id: str
    series_id: str
    name: str
    title: str
    path: str
    created_at: str
    page_count: int = 0
    read_page: int | None = None
    read_done: bool = False
    deleted: bool = False
    summary: str = ""
    tags: list[str] = field(default_factory=list)
    links: list[tuple[str, str]] = field(default_factory=list)
    writers: list[str] = field(default_factory=list)
    authors: list[str] = field(default_factory=list)  # every author name, any role


@dataclass(frozen=True)
class SeriesDTO:
    id: str
    library_id: str
    name: str
    title: str
    path: str
    created_at: str
    book_count: int = 0
    read_count: int = 0
    deleted: bool = False
    oneshot: bool = False
    summary: str = ""
    tags: list[str] = field(default_factory=list)
    links: list[tuple[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class PageResult[T]:
    """One page; `page` is 1-based."""

    items: list[T]
    page: int
    size: int
    total_pages: int
    total_items: int

    @property
    def last(self) -> bool:
        return self.page >= self.total_pages


class ImageStream(Protocol):
    content_type: str
    content_length: str | None

    def iter_bytes(self) -> Iterator[bytes]: ...

    def close(self) -> None: ...


class BookServer(Protocol):
    kind: str  # "stump"; later "stump". Stored in saved_items/trash_items.target.

    def valid_id(self, id: str) -> bool: ...

    # browse / library
    def list_libraries(self) -> list[LibraryDTO]: ...
    def list_series(
        self, page: int, size: int, q: str, sort: str, library_id: str | None = None
    ) -> PageResult[SeriesDTO]: ...
    def list_books(
        self,
        page: int,
        size: int,
        q: str,
        sort: str,
        series_id: str | None = None,
        library_id: str | None = None,
    ) -> PageResult[BookDTO]: ...
    def get_series(self, id: str) -> SeriesDTO: ...
    def get_book(self, id: str) -> BookDTO: ...
    def series_books(self, series_id: str) -> tuple[list[BookDTO], bool]: ...
    def tagged_books(self, q: str, tags: list[str]) -> list[BookDTO]: ...

    # search / lookup
    def find_by_path(
        self, kind: Kind, library_id: str, path: str, text: str
    ) -> BookDTO | SeriesDTO | None: ...

    # media
    def open_thumb(self, kind: Kind, id: str) -> ImageStream: ...
    def open_page(self, book_id: str, n: int) -> ImageStream: ...
    def open_page_thumb(self, book_id: str, n: int, width: int) -> ImageStream: ...

    # save target + scan
    def scan_library(self, library_id: str) -> None: ...

    # trash / undo
    def list_deleted(self, kind: Kind, library_id: str) -> list[BookDTO | SeriesDTO]: ...
    def purge_deleted(self, library_id: str) -> None: ...

    # tags / metadata / progress
    def set_tags(self, kind: Kind, id: str, tags: list[str]) -> None: ...
    def set_metadata(self, kind: Kind, id: str, patch: MetadataPatch) -> None: ...
    def set_progress(self, book_id: str, page: int, completed: bool) -> None: ...

    # health
    def ping(self) -> str | None: ...
