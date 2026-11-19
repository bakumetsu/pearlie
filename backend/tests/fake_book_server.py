"""In-memory `BookServer` for contract and shared-code tests (never imported by app code)."""

from __future__ import annotations

from dataclasses import replace

from app.bookserver.base import (
    BookDTO,
    BookServerError,
    Kind,
    LibraryDTO,
    MetadataPatch,
    PageResult,
    SeriesDTO,
)


class FakeImage:
    content_type = "image/jpeg"
    content_length: str | None = "3"

    def __init__(self, data: bytes = b"jpg") -> None:
        self._data = data
        self.closed = False

    def iter_bytes(self):  # noqa: ANN201
        yield self._data

    def close(self) -> None:
        self.closed = True


class FakeBookServer:
    kind = "fake"

    def __init__(
        self,
        libraries: list[LibraryDTO] | None = None,
        series: list[SeriesDTO] | None = None,
        books: list[BookDTO] | None = None,
    ) -> None:
        self.libraries = libraries or []
        self.series = {s.id: s for s in series or []}
        self.books = {b.id: b for b in books or []}
        self.scans: list[str] = []
        self.purged: list[str] = []
        self.progress: dict[str, tuple[int, bool]] = {}

    def valid_id(self, id: str) -> bool:
        return id.isalnum() and len(id) <= 64

    def list_libraries(self) -> list[LibraryDTO]:
        return list(self.libraries)

    @staticmethod
    def _slice[T](items: list[T], page: int, size: int) -> PageResult[T]:
        pages = max(1, -(-len(items) // size))
        start = (page - 1) * size
        return PageResult(items[start : start + size], page, size, pages, len(items))

    def list_series(
        self, page: int, size: int, q: str, sort: str, library_id: str | None = None
    ) -> PageResult[SeriesDTO]:
        rows = [
            s
            for s in self.series.values()
            if not s.deleted
            and q.lower() in s.title.lower()
            and (library_id is None or s.library_id == library_id)
        ]
        return self._slice(rows, page, size)

    def list_books(
        self,
        page: int,
        size: int,
        q: str,
        sort: str,
        series_id: str | None = None,
        library_id: str | None = None,
    ) -> PageResult[BookDTO]:
        rows = [
            b
            for b in self.books.values()
            if not b.deleted
            and q.lower() in b.title.lower()
            and (series_id is None or b.series_id == series_id)
            and (library_id is None or b.library_id == library_id)
        ]
        return self._slice(rows, page, size)

    def get_series(self, id: str) -> SeriesDTO:
        if id not in self.series:
            raise BookServerError("not_found", "Not found", 404)
        return self.series[id]

    def get_book(self, id: str) -> BookDTO:
        if id not in self.books:
            raise BookServerError("not_found", "Not found", 404)
        return self.books[id]

    def series_books(self, series_id: str) -> tuple[list[BookDTO], bool]:
        return [b for b in self.books.values() if b.series_id == series_id], False

    def find_by_path(
        self, kind: Kind, library_id: str, path: str, text: str
    ) -> BookDTO | SeriesDTO | None:
        rows = self.books if kind == "books" else self.series
        for r in rows.values():
            if r.library_id == library_id and r.path == path and not r.deleted:
                return r
        return None

    def open_thumb(self, kind: Kind, id: str) -> FakeImage:
        (self.get_book if kind == "books" else self.get_series)(id)
        return FakeImage()

    def open_page(self, book_id: str, n: int) -> FakeImage:
        book = self.get_book(book_id)
        if not 1 <= n <= book.page_count:
            raise BookServerError("not_found", "Not found", 404)
        return FakeImage()

    def open_page_thumb(self, book_id: str, n: int, width: int) -> FakeImage:
        return self.open_page(book_id, n)

    def scan_library(self, library_id: str) -> None:
        self.scans.append(library_id)

    def list_deleted(self, kind: Kind, library_id: str) -> list[BookDTO | SeriesDTO]:
        rows = self.books if kind == "books" else self.series
        return [r for r in rows.values() if r.library_id == library_id and r.deleted]

    def purge_deleted(self, library_id: str) -> None:
        self.purged.append(library_id)
        for rows in (self.books, self.series):
            for k in [k for k, r in rows.items() if r.library_id == library_id and r.deleted]:
                del rows[k]

    def set_tags(self, kind: Kind, id: str, tags: list[str]) -> None:
        self.set_metadata(kind, id, MetadataPatch(tags=sorted(tags)))

    def set_metadata(self, kind: Kind, id: str, patch: MetadataPatch) -> None:
        rows: dict = self.books if kind == "books" else self.series
        if id not in rows:
            raise BookServerError("not_found", "Not found", 404)
        changes = {
            k: v
            for k, v in (("tags", patch.tags), ("title", patch.title), ("summary", patch.summary))
            if v is not None
        }
        rows[id] = replace(rows[id], **changes)

    def set_progress(self, book_id: str, page: int, completed: bool) -> None:
        book = self.get_book(book_id)
        self.books[book_id] = replace(book, read_page=page, read_done=completed)

    def ping(self) -> str | None:
        return "fake"
