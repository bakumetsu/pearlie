"""Komga REST client for Pearlie library integration."""

from __future__ import annotations

import httpx

from app.logs import install_http_hooks
from app.models import LibraryItem, LibraryItemDetail, Problem, Tag

# Komga page numbers are 1-based with zero_based=false, same as Pearlie's reader; no conversion.
PAGE_BASE = 1
SERIES_BOOKS_PAGES = 20
SERIES_BOOKS_SIZE = 500


class KomgaError(Exception):
    """Error raised by the Komga client."""

    def __init__(self, code: str, message: str, status: int) -> None:
        self.code = code
        self.message = message
        self.status = status
        super().__init__(message)


class Komga:
    """Komga REST API client."""

    def __init__(self, base_url: str, api_key: str, client: httpx.Client | None = None) -> None:
        """Initialise the client.

        When *client* is ``None`` a new ``httpx.Client`` is created with the
        API-key header and a 15-second timeout.  An injected client (e.g. one
        using ``httpx.MockTransport`` in tests) is used as-is.
        """
        if client is None:
            self._client: httpx.Client = install_http_hooks(
                httpx.Client(
                    base_url=base_url,
                    headers={"X-API-Key": api_key},
                    timeout=15.0,
                ),
                "komga",
            )
        else:
            self._client = client

    def _check(self, resp: httpx.Response) -> None:
        """Raise ``KomgaError`` for a 404 or any other status >= 400."""
        if resp.status_code == 404:
            raise KomgaError("not_found", "Not found", 404)
        if resp.status_code >= 400:
            raise KomgaError("upstream_error", f"Komga returned {resp.status_code}", 502)

    def list_libraries(self) -> list[dict]:
        """Return every Komga library (id, name, root)."""
        try:
            resp = self._client.get("/api/v1/libraries")
        except httpx.HTTPError:
            raise KomgaError("upstream_error", "Komga is not reachable", 502) from None
        self._check(resp)
        data = resp.json()
        return data if isinstance(data, list) else []

    def scan_library(self, library_id: str) -> None:
        """Ask Komga to scan one library for new files."""
        try:
            resp = self._client.post(f"/api/v1/libraries/{library_id}/scan")
        except httpx.HTTPError:
            raise KomgaError("upstream_error", "Komga is not reachable", 502) from None
        self._check(resp)

    def list_series(self, page: int, size: int, q: str, sort: str) -> dict:
        """Return one page of series matching *q* (full-text search).

        *page* is the 0-based Komga page index (the caller handles conversion
        from any 1-based UI page).
        """
        body: dict = {}
        if q:
            body["fullTextSearch"] = q
        try:
            resp = self._client.post(
                "/api/v1/series/list",
                params={"page": page, "size": size, "sort": sort},
                json=body,
            )
        except httpx.HTTPError:
            raise KomgaError("upstream_error", "Komga is not reachable", 502) from None
        self._check(resp)
        return resp.json()

    def list_books(
        self,
        page: int,
        size: int,
        q: str,
        sort: str,
        series_id: str | None = None,
        library_id: str | None = None,
    ) -> dict:
        """Return one page of books, optionally filtered to a series or a library."""
        body: dict = {}
        if q:
            body["fullTextSearch"] = q
        if series_id is not None:
            body["condition"] = {"seriesId": {"operator": "is", "value": series_id}}
        elif library_id is not None:
            body["condition"] = {"libraryId": {"operator": "is", "value": library_id}}
        try:
            resp = self._client.post(
                "/api/v1/books/list",
                params={"page": page, "size": size, "sort": sort},
                json=body,
            )
        except httpx.HTTPError:
            raise KomgaError("upstream_error", "Komga is not reachable", 502) from None
        self._check(resp)
        return resp.json()

    def get_series(self, id: str) -> dict:
        """Return a single series by its Komga id."""
        try:
            resp = self._client.get(f"/api/v1/series/{id}")
        except httpx.HTTPError:
            raise KomgaError("upstream_error", "Komga is not reachable", 502) from None
        self._check(resp)
        return resp.json()

    def get_book(self, id: str) -> dict:
        """Return a single book by its Komga id."""
        try:
            resp = self._client.get(f"/api/v1/books/{id}")
        except httpx.HTTPError:
            raise KomgaError("upstream_error", "Komga is not reachable", 502) from None
        self._check(resp)
        return resp.json()

    def all_series_books(self, series_id: str) -> tuple[list[dict], bool]:
        """Fetch every book belonging to *series_id* (paginated, capped at 20 pages)."""
        books: list[dict] = []
        truncated = False
        page = 0
        for _ in range(SERIES_BOOKS_PAGES):
            result = self.list_books(
                page=page, size=SERIES_BOOKS_SIZE, q="", sort="number,asc", series_id=series_id
            )
            books.extend(result["content"])
            if result["last"]:
                break
            page += 1
        else:
            truncated = True
        return books, truncated

    def set_progress(self, book_id: str, page: int, completed: bool) -> None:
        """Set the read-progress for a book (page + completed flag)."""
        try:
            resp = self._client.patch(
                f"/api/v1/books/{book_id}/read-progress",
                json={"page": page, "completed": completed},
            )
        except httpx.HTTPError:
            raise KomgaError("upstream_error", "Komga is not reachable", 502) from None
        self._check(resp)

    def set_tags(self, kind: str, id: str, tags: list[str]) -> None:
        """Set the tags on a series or book via its metadata endpoint."""
        try:
            resp = self._client.patch(
                f"/api/v1/{kind}/{id}/metadata",
                json={"tags": tags, "tagsLock": True},
            )
        except httpx.HTTPError:
            raise KomgaError("upstream_error", "Komga is not reachable", 502) from None
        self._check(resp)

    def open_image(self, path: str, params: dict | None = None) -> httpx.Response:
        """Open a streaming GET for an image.  The caller must close the response."""
        request = self._client.build_request("GET", path, params=params)
        try:
            resp = self._client.send(request, stream=True)
        except httpx.HTTPError:
            raise KomgaError("upstream_error", "Komga is not reachable", 502) from None
        try:
            self._check(resp)
        except KomgaError:
            resp.close()
            raise
        return resp


# ---------------------------------------------------------------------------
# DTO → model mapping (pure, no I/O)
# ---------------------------------------------------------------------------


def book_item(dto: dict) -> LibraryItem:
    """Map a Komga BookDto to a ``LibraryItem``."""
    metadata = dto.get("metadata") or {}
    rp = dto.get("readProgress")
    return LibraryItem(
        kind="book",
        id=dto["id"],
        title=metadata.get("title") or dto["name"],
        thumb_url=f"/api/media/komga/books/{dto['id']}/thumb",
        tags=sorted(metadata.get("tags", [])),
        page_count=dto["media"]["pagesCount"],
        read_page=rp["page"] if rp else None,
        added_at=dto["created"],
    )


def _series_tags(dto: dict) -> list[str]:
    """Return the sorted, de-duplicated union of series and book tags."""
    meta_tags = (dto.get("metadata") or {}).get("tags", [])
    book_tags = (dto.get("booksMetadata") or {}).get("tags", [])
    return sorted(set(meta_tags) | set(book_tags))


def series_item(dto: dict) -> LibraryItem:
    """Map a Komga SeriesDto to a ``LibraryItem``."""
    metadata = dto.get("metadata") or {}
    return LibraryItem(
        kind="series",
        id=dto["id"],
        title=metadata.get("title") or dto["name"],
        thumb_url=f"/api/media/komga/series/{dto['id']}/thumb",
        book_count=dto["booksCount"],
        read_count=dto["booksReadCount"],
        tags=_series_tags(dto),
        added_at=dto["created"],
    )


def book_detail(dto: dict) -> LibraryItemDetail:
    """Map a Komga BookDto to a ``LibraryItemDetail``."""
    metadata = dto.get("metadata") or {}
    rp = dto.get("readProgress")
    return LibraryItemDetail(
        kind="book",
        id=dto["id"],
        title=metadata.get("title") or dto["name"],
        thumb_url=f"/api/media/komga/books/{dto['id']}/thumb",
        tags=[Tag(name=t) for t in sorted(metadata.get("tags", []))],
        page_count=dto["media"]["pagesCount"],
        read_page=rp["page"] if rp else None,
        page_url=f"/api/media/komga/books/{dto['id']}/pages/{{n}}",
        page_thumb_url=f"/api/media/komga/books/{dto['id']}/pages/{{n}}/thumb",
        added_at=dto["created"],
    )


def series_detail(dto: dict, books: list[dict], truncated: bool = False) -> LibraryItemDetail:
    """Map a Komga SeriesDto (with its book list) to a ``LibraryItemDetail``."""
    metadata = dto.get("metadata") or {}
    return LibraryItemDetail(
        kind="series",
        id=dto["id"],
        title=metadata.get("title") or dto["name"],
        thumb_url=f"/api/media/komga/series/{dto['id']}/thumb",
        book_count=dto["booksCount"],
        read_count=dto["booksReadCount"],
        tags=[Tag(name=t) for t in _series_tags(dto)],
        books=[book_item(b) for b in books],
        notice=(
            Problem(code="truncated", message="Showing the first 10,000 books")
            if truncated
            else None
        ),
        added_at=dto["created"],
    )
