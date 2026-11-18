"""Stump adapter (read side): the only place that knows Stump's GraphQL fields and filters.

Write methods are stubs that raise `not_supported`: scan is T-328; trash listing and purge
are T-329; tags, metadata and progress writes are also marked T-329.
"""

from __future__ import annotations

import io
import re
from collections.abc import Iterator

import httpx
from PIL import Image, ImageOps

from app.bookserver.base import (
    SORT_CREATED_DESC,
    SORT_NUMBER_ASC,
    BookDTO,
    BookServerError,
    ImageStream,
    Kind,
    LibraryDTO,
    MetadataPatch,
    PageResult,
    SeriesDTO,
)
from app.stump import PAGE_SIZE, SERIES_BOOKS_PAGES, Stump
from app.thumbcache import PAGE_THUMB_SOURCE, ThumbCache

_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")
MAX_PAGE_BYTES = 40 * 1024 * 1024  # a page we downscale; larger is refused
MIN_THUMB_W, MAX_THUMB_W = 16, 2000
THUMB_QUALITY = 80
_MISSING = "MISSING"

# `{field, direction}` entries of Stump's order inputs
_NAME_ASC = [{"field": "NAME", "direction": "ASC"}]
_CREATED_DESC = [{"field": "CREATED_AT", "direction": "DESC"}]


class _StumpImage:
    """A streaming Stump image answer."""

    def __init__(self, resp: httpx.Response) -> None:
        self._resp = resp
        self.content_type = resp.headers.get("content-type", "application/octet-stream")
        self.content_length = resp.headers.get("content-length")

    def iter_bytes(self, chunk_size: int = 65536) -> Iterator[bytes]:
        return self._resp.iter_bytes(chunk_size=chunk_size)

    def close(self) -> None:
        self._resp.close()


class _BytesImage:
    """An in-memory image (a downscaled page thumbnail)."""

    def __init__(self, data: bytes, content_type: str) -> None:
        self._data = data
        self.content_type = content_type
        self.content_length: str | None = str(len(data))

    def iter_bytes(self, chunk_size: int = 65536) -> Iterator[bytes]:
        for i in range(0, len(self._data), chunk_size):
            yield self._data[i : i + chunk_size]

    def close(self) -> None:
        pass


def _links(meta: dict) -> list[tuple[str, str]]:
    """Stump links are plain URLs; the label is the URL itself."""
    return [(str(u), str(u)) for u in meta.get("links") or []]


def _tags(d: dict) -> list[str]:
    return sorted(str(t.get("name", "")) for t in d.get("tags") or [] if isinstance(t, dict))


def book_dto(d: dict) -> BookDTO:
    meta = d.get("metadata") or {}
    rp = d.get("readProgress")
    writers = [str(w) for w in meta.get("writers") or []]
    return BookDTO(
        id=str(d.get("id", "")),
        library_id=str(d.get("libraryId") or ""),
        series_id=str(d.get("seriesId") or ""),
        name=d.get("name", ""),
        title=meta.get("title") or d.get("name", ""),
        path=str(d.get("path", "")),
        created_at=d.get("createdAt") or "",
        page_count=int(d.get("pages") or 0),
        read_page=rp.get("page") if rp else None,
        read_done=bool(rp and rp.get("isCompleted")),
        deleted=bool(d.get("deletedAt")) or d.get("status") == _MISSING,
        summary=meta.get("summary") or "",
        tags=_tags(d),
        links=_links(meta),
        writers=writers,
        authors=writers,
    )


def series_dto(d: dict) -> SeriesDTO:
    meta = d.get("metadata") or {}
    return SeriesDTO(
        id=str(d.get("id", "")),
        library_id=str(d.get("libraryId") or ""),
        name=d.get("name", ""),
        title=meta.get("title") or d.get("name", ""),
        path=str(d.get("path", "")),
        created_at=d.get("createdAt") or "",
        book_count=int(d.get("mediaCount") or 0),
        read_count=int(d.get("readCount") or 0),
        deleted=bool(d.get("deletedAt")),
        oneshot=bool(d.get("isOneshot")),
        summary=meta.get("summary") or "",
        tags=_tags(d),
        links=_links(meta),
    )


def _page[T](conn: dict, page: int, size: int, items: list[T]) -> PageResult[T]:
    info = conn.get("pageInfo") or {}
    return PageResult(
        items=items,
        page=page,
        size=size,
        total_pages=max(1, int(info.get("totalPages") or 1)),
        total_items=int(info.get("totalItems") or len(items)),
    )


def _search(q: str) -> dict:
    """name / metadata title / path contains *q* (Stump has no full-text search)."""
    return {
        "_or": [
            {"name": {"contains": q}},
            {"metadata": {"title": {"contains": q}}},
            {"path": {"contains": q}},
        ]
    }


def _filter(q: str, **eq: str | None) -> dict | None:
    parts: list[dict] = [{k: {"eq": v}} for k, v in eq.items() if v]
    if q:
        parts.append(_search(q))
    if not parts:
        return None
    return parts[0] if len(parts) == 1 else {"_and": parts}


def _order(q: str, sort: str) -> list[dict]:
    """A search lists by name; else newest first, or by name for the book order."""
    if q or sort == SORT_NUMBER_ASC:
        return _NAME_ASC
    return _CREATED_DESC if sort == SORT_CREATED_DESC else _NAME_ASC


def _not_supported(what: str) -> BookServerError:
    return BookServerError("not_supported", f"Stump {what} is not supported yet", 501)


class StumpBookServer:
    """`BookServer` over the `Stump` client (page numbers: Pearlie 1-based, Stump 1-based)."""

    kind = "stump"

    def __init__(self, client: Stump, cache: ThumbCache | None = None) -> None:
        self._c = client
        self._cache = cache

    @property
    def client(self) -> Stump:
        return self._c

    def valid_id(self, id: str) -> bool:
        return _ID_RE.fullmatch(id) is not None

    # browse / library

    def list_libraries(self) -> list[LibraryDTO]:
        out = []
        for d in self._c.list_libraries():
            raw = (d.get("config") or {}).get("oneshotsDirectory")
            out.append(
                LibraryDTO(
                    id=str(d.get("id", "")),
                    name=str(d.get("name", "")),
                    root=str(d.get("path", "")),
                    oneshots_dir=raw if isinstance(raw, str) and raw else None,
                )
            )
        return out

    def list_series(
        self, page: int, size: int, q: str, sort: str, library_id: str | None = None
    ) -> PageResult[SeriesDTO]:
        conn = self._c.list_series(page, size, _filter(q, libraryId=library_id), _order(q, sort))
        return _page(conn, page, size, [series_dto(d) for d in conn.get("nodes") or []])

    def list_books(
        self,
        page: int,
        size: int,
        q: str,
        sort: str,
        series_id: str | None = None,
        library_id: str | None = None,
    ) -> PageResult[BookDTO]:
        conn = self._c.list_media(
            page, size, _filter(q, seriesId=series_id, libraryId=library_id), _order(q, sort)
        )
        return _page(conn, page, size, [book_dto(d) for d in conn.get("nodes") or []])

    def get_series(self, id: str) -> SeriesDTO:
        return series_dto(self._c.get_series(id))

    def get_book(self, id: str) -> BookDTO:
        return book_dto(self._c.get_media(id))

    def series_books(self, series_id: str) -> tuple[list[BookDTO], bool]:
        books: list[BookDTO] = []
        for page in range(1, SERIES_BOOKS_PAGES + 1):
            conn = self._c.list_media(page, PAGE_SIZE, _filter("", seriesId=series_id), _NAME_ASC)
            books.extend(book_dto(d) for d in conn.get("nodes") or [])
            if _page(conn, page, PAGE_SIZE, []).last:
                return books, False
        return books, True

    # search / lookup

    def find_by_path(
        self, kind: Kind, library_id: str, path: str, text: str
    ) -> BookDTO | SeriesDTO | None:
        """The live book or series at *path* (exact match; *text* is not needed)."""
        if kind == "books":
            d = self._c.media_by_path(path)
            book = book_dto(d) if d else None
            return book if book is not None and not book.deleted else None
        conn = self._c.list_series(
            1, 1, {"_and": [{"libraryId": {"eq": library_id}}, {"path": {"eq": path}}]}, _NAME_ASC
        )
        nodes = conn.get("nodes") or []
        series = series_dto(nodes[0]) if nodes else None
        return series if series is not None and not series.deleted else None

    # media

    def open_thumb(self, kind: Kind, id: str) -> ImageStream:
        seg = "series" if kind == "series" else "media"
        return _StumpImage(self._c.open_image(f"/api/v2/{seg}/{id}/thumbnail"))

    @staticmethod
    def _check_page(n: int) -> None:
        if n < 1:
            raise BookServerError("bad_request", "Page numbers start at 1", 400)

    def open_page(self, book_id: str, n: int) -> ImageStream:
        self._check_page(n)
        return _StumpImage(self._c.open_image(f"/api/v2/media/{book_id}/page/{n}"))

    def open_page_thumb(self, book_id: str, n: int, width: int) -> ImageStream:
        """The page, downscaled to *width* by Pearlie (Stump has no page thumbnail route)."""
        self._check_page(n)
        width = max(MIN_THUMB_W, min(MAX_THUMB_W, width))
        key = f"{book_id}:{n}:{width}"
        if self._cache is not None:
            hit = self._cache.get(PAGE_THUMB_SOURCE, key)
            if hit is not None:
                try:
                    return _BytesImage(hit.read_bytes(), "image/jpeg")
                except OSError:
                    pass
        resp = self._c.open_image(f"/api/v2/media/{book_id}/page/{n}")
        try:
            chunks: list[bytes] = []
            size = 0
            for chunk in resp.iter_bytes():
                size += len(chunk)
                if size > MAX_PAGE_BYTES:
                    raise BookServerError("upstream_error", "Stump page is too large", 502)
                chunks.append(chunk)
            raw = b"".join(chunks)
        except httpx.HTTPError:
            raise BookServerError("upstream_error", "Stump is not reachable", 502) from None
        finally:
            resp.close()
        data = _downscale(raw, width)
        if self._cache is not None:
            self._cache.put(PAGE_THUMB_SOURCE, key, data)
        return _BytesImage(data, "image/jpeg")

    # save target + scan (T-328)

    def scan_library(self, library_id: str) -> None:
        self._c.scan_library(library_id)

    # trash / undo (T-329)

    def list_deleted(self, kind: Kind, library_id: str) -> list[BookDTO | SeriesDTO]:
        raise _not_supported("trash listing")  # T-329

    def purge_deleted(self, library_id: str) -> None:
        raise _not_supported("trash purge")  # T-329

    # tags / metadata / progress (T-329)

    def set_tags(self, kind: Kind, id: str, tags: list[str]) -> None:
        raise _not_supported("tag write")  # T-329

    def set_metadata(self, kind: Kind, id: str, patch: MetadataPatch) -> None:
        raise _not_supported("metadata write")  # T-329

    def set_progress(self, book_id: str, page: int, completed: bool) -> None:
        raise _not_supported("progress write")  # T-329

    # health

    def ping(self) -> str | None:
        self._c.list_libraries()  # raises on an unreachable or refusing server
        return None


def _downscale(raw: bytes, width: int) -> bytes:
    """JPEG of *raw* at most *width* px wide (never enlarged)."""
    try:
        with Image.open(io.BytesIO(raw)) as im:
            im = ImageOps.exif_transpose(im) or im
            if im.width > width:
                im = im.resize((width, max(1, round(im.height * width / im.width))))
            out = io.BytesIO()
            im.convert("RGB").save(out, "JPEG", quality=THUMB_QUALITY)
    except (OSError, ValueError, Image.DecompressionBombError):
        raise BookServerError("upstream_error", "Stump page is not a readable image", 502) from None
    return out.getvalue()
