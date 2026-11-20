"""Stump adapter: the only place that knows Stump's GraphQL fields and filters.

Trash: Pearlie moves the file, so Stump shows the item as `MISSING` after a scan; `purge_deleted`
runs `cleanLibrary` (the caller guards against foreign MISSING items).
"""

from __future__ import annotations

import io
import re
import time
from collections.abc import Callable, Iterator
from typing import TypeVar

import httpx
from PIL import Image, ImageOps

from app.bookserver.base import (
    SORT_CREATED_DESC,
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
_T = TypeVar("_T")
_MISSING = "MISSING"
WALK_TTL_S = 15.0  # how long a full series or deleted-items walk is reused
TAG_WALK_TTL_S = 600.0  # the library tag walk is big (up to 100 calls): reuse it longer
TAG_WALK_PAGES = SERIES_BOOKS_PAGES  # the cap: 10,000 books, in memory only, never in the DB

# Stump's order inputs are oneof objects: `{series: {field, direction}}` or `{media: {...}}`
_NAME_ASC = {"field": "NAME", "direction": "ASC"}
_CREATED_DESC = {"field": "CREATED_AT", "direction": "DESC"}


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


def _tag_key(tag: str) -> str:
    """A tag as compared in a tag search: no quotes, `_` as space, lower case."""
    return tag.strip().replace('"', "").replace("_", " ").lower()


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
        read_done=any(
            h.get("completedAt") for h in d.get("readHistory") or [] if isinstance(h, dict)
        ),
        deleted=d.get("status") == _MISSING,
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
        deleted=d.get("status") == _MISSING,
        oneshot=bool(d.get("oneshotBook")),
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


def _search(q: str, tags: bool = False) -> dict:
    """name / metadata title contains *q* (Stump has no full-text search).

    *tags* adds the book tag filter (`_` as space, like a booru tag); Stump has it on media only.
    """
    ors: list[dict] = [{"name": {"contains": q}}, {"metadata": {"title": {"contains": q}}}]
    if tags:
        ors.append({"tags": {"contains": q.replace("_", " ")}})
    return {"_or": ors}


def _filter(q: str, *conds: dict | None, tags: bool = False) -> dict:
    """*conds* and the search text as one filter (`{}` for no condition: Stump needs a filter)."""
    parts = [c for c in conds if c]
    if q:
        parts.append(_search(q, tags))
    if not parts:
        return {}
    return parts[0] if len(parts) == 1 else {"_and": parts}


def _eq(field: str, value: str | None) -> dict | None:
    return {field: {"eq": value}} if value else None


def _in_library(library_id: str | None) -> dict | None:
    """A media filter reaches the library through its series."""
    return {"series": {"libraryId": {"eq": library_id}}} if library_id else None


def _order(entity: str, q: str, sort: str) -> list[dict]:
    """A search lists by name; else newest first, or by name for the book order."""
    by = _CREATED_DESC if sort == SORT_CREATED_DESC and not q else _NAME_ASC
    return [{entity: by}]


def _name_asc(entity: str) -> list[dict]:
    return [{entity: _NAME_ASC}]


class StumpBookServer:
    """`BookServer` over the `Stump` client (page numbers: Pearlie 1-based, Stump 1-based)."""

    kind = "stump"

    def __init__(self, client: Stump, cache: ThumbCache | None = None) -> None:
        self._c = client
        self._cache = cache
        self._walks: dict[tuple, tuple[float, object, float]] = {}

    def _walked(self, key: tuple, walk: Callable[[], _T], ttl: float = WALK_TTL_S) -> _T:
        """Result of *walk*, reused for *ttl*; every write through this adapter clears it."""
        hit = self._walks.get(key)
        if hit is not None and time.monotonic() - hit[0] < hit[2]:
            return hit[1]  # type: ignore[return-value]
        value = walk()
        now = time.monotonic()
        for k in [k for k, (t, _v, ttl_k) in self._walks.items() if now - t >= ttl_k]:
            del self._walks[k]  # sweep, so the dict cannot grow without bound
        self._walks[key] = (now, value, ttl)
        return value

    def invalidate_walks(self) -> None:
        """Forget every cached walk (the library changed behind the adapter, e.g. a trash move)."""
        self._walks.clear()

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
        if q.strip():
            return self._search_series(page, size, q, library_id)
        conn = self._c.list_series(
            page, size, _filter("", _eq("libraryId", library_id)), _order("series", q, sort)
        )
        return _page(conn, page, size, [series_dto(d) for d in conn.get("nodes") or []])

    def _search_series(
        self, page: int, size: int, q: str, library_id: str | None
    ) -> PageResult[SeriesDTO]:
        """Series whose name, title or a tag contains *q*, by name.

        Stump v0.1.13 has no series tag filter, so this reads one cached name-ordered walk (cap
        10,000 series, in memory only) and matches here, then pages the matches.
        """
        walk = self._walked(("serieswalk", library_id), lambda: self._walk_all_series(library_id))
        want = q.strip().lower()
        want_tag = _tag_key(q)
        hits = [
            s
            for s in walk
            if want in s.name.lower()
            or want in s.title.lower()
            or any(want_tag in _tag_key(t) for t in s.tags)
        ]
        total = len(hits)
        pages = max(1, -(-total // size))
        start = (page - 1) * size
        return PageResult(
            items=hits[start : start + size],
            page=page,
            size=size,
            total_pages=pages,
            total_items=total,
        )

    def _walk_all_series(self, library_id: str | None) -> list[SeriesDTO]:
        out: list[SeriesDTO] = []
        for page in range(1, TAG_WALK_PAGES + 1):
            conn = self._c.list_series(
                page, PAGE_SIZE, _filter("", _eq("libraryId", library_id)), _name_asc("series")
            )
            out.extend(series_dto(d) for d in conn.get("nodes") or [])
            if _page(conn, page, PAGE_SIZE, []).last:
                break
        return out

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
            page,
            size,
            _filter(q, _eq("seriesId", series_id), _in_library(library_id), tags=True),
            _order("media", q, sort),
        )
        return _page(conn, page, size, [book_dto(d) for d in conn.get("nodes") or []])

    def get_series(self, id: str) -> SeriesDTO:
        return series_dto(self._c.get_series(id))

    def get_book(self, id: str) -> BookDTO:
        return book_dto(self._c.get_media(id))

    def series_books(self, series_id: str) -> tuple[list[BookDTO], bool]:
        books, truncated = self._walked(("books", series_id), lambda: self._walk_series(series_id))
        return list(books), truncated

    def _walk_series(self, series_id: str) -> tuple[list[BookDTO], bool]:
        books: list[BookDTO] = []
        for page in range(1, SERIES_BOOKS_PAGES + 1):
            conn = self._c.list_media(
                page, PAGE_SIZE, _filter("", _eq("seriesId", series_id)), _name_asc("media")
            )
            books.extend(book_dto(d) for d in conn.get("nodes") or [])
            if _page(conn, page, PAGE_SIZE, []).last:
                return books, False
        return books, True

    def tagged_books(self, q: str, tags: list[str]) -> list[BookDTO]:
        """Books matching the title text *q* that carry every tag (AND); `-tag` must be absent.

        Reads one cached walk of the title search (cap 10,000 books, newest first): the tag lists
        come with the books, so a tag tap costs no extra Stump call.
        """
        books = self._walked(("tagwalk", q), lambda: self._walk_books(q), TAG_WALK_TTL_S)
        want = {t for t in map(_tag_key, tags) if t and not t.startswith("-")}
        drop = {t[1:] for t in map(_tag_key, tags) if t.startswith("-") and len(t) > 1}
        out = []
        for b in books:
            have = {_tag_key(t) for t in b.tags}
            if want <= have and not drop & have:
                out.append(b)
        return out

    def _walk_books(self, q: str) -> list[BookDTO]:
        books: list[BookDTO] = []
        for page in range(1, TAG_WALK_PAGES + 1):
            conn = self._c.list_media(
                page, PAGE_SIZE, _filter(q, None), _order("media", q, SORT_CREATED_DESC)
            )
            books.extend(book_dto(d) for d in conn.get("nodes") or [])
            if _page(conn, page, PAGE_SIZE, []).last:
                break
        return books

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
            1,
            1,
            {"_and": [{"libraryId": {"eq": library_id}}, {"path": {"eq": path}}]},
            _name_asc("series"),
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
        self._walks.clear()
        try:
            self._c.scan_library(library_id)
        finally:
            self._walks.clear()  # a walk made during the scan saw half-scanned data

    # trash / undo (T-329)

    def list_deleted(self, kind: Kind, library_id: str) -> list[BookDTO | SeriesDTO]:
        """Items of the library Stump shows as MISSING (their file is gone)."""
        out = self._walked(
            ("deleted", kind, library_id), lambda: self._walk_deleted(kind, library_id)
        )
        return list(out)

    def _walk_deleted(self, kind: Kind, library_id: str) -> list[BookDTO | SeriesDTO]:
        # SeriesFilterInput has no `status` field (Stump rejects it): series are filtered here
        filt = {"_and": [_in_library(library_id), {"status": {"eq": _MISSING}}]}
        series_filt = _eq("libraryId", library_id) or {}
        out: list[BookDTO | SeriesDTO] = []
        for page in range(1, SERIES_BOOKS_PAGES + 1):
            if kind == "books":
                conn = self._c.list_media(page, PAGE_SIZE, filt, _name_asc("media"))
                out.extend(book_dto(d) for d in conn.get("nodes") or [])
            else:
                conn = self._c.list_series(page, PAGE_SIZE, series_filt, _name_asc("series"))
                out.extend(s for s in map(series_dto, conn.get("nodes") or []) if s.deleted)
            if _page(conn, page, PAGE_SIZE, []).last:
                break
        return out

    def purge_deleted(self, library_id: str) -> None:
        self._walks.clear()
        try:
            self._c.clean_library(library_id)
        finally:
            self._walks.clear()

    # tags / metadata / progress (T-329)

    def set_tags(self, kind: Kind, id: str, tags: list[str]) -> None:
        self._walks.clear()
        self._c.set_tags(kind, id, tags)
        self._c.lock_fields(kind, id, ["TAGS"])

    def set_metadata(self, kind: Kind, id: str, patch: MetadataPatch) -> None:
        self._walks.clear()
        fields: dict = {}
        locks: list[str] = []
        if patch.title is not None:
            fields["title"] = patch.title
            locks.append("TITLE")
        if patch.summary is not None:
            fields["summary"] = patch.summary
            locks.append("SUMMARY")
        if patch.links is not None:
            fields["links"] = [url for _label, url in patch.links]  # Stump links have no label
            locks.append("LINKS")
        if patch.writers is not None and kind == "books":
            fields["writers"] = list(patch.writers)  # Stump authors with role writer
            locks.append("WRITERS")
        if fields:
            self._c.update_metadata(kind, id, fields)
        if patch.tags is not None:
            self._c.set_tags(kind, id, patch.tags)
            locks.append("TAGS")
        if not locks:
            raise BookServerError("bad_request", "Empty metadata patch", 400)
        self._c.lock_fields(kind, id, locks)

    def set_progress(self, book_id: str, page: int, completed: bool) -> None:
        self._walks.clear()
        if completed:
            self._c.finish_progress(book_id)
            return
        if page == 0:  # not started: Stump keeps the finished state unless it is deleted
            try:
                self._c.reset_progress(book_id)
            finally:
                self._walks.clear()  # tiles and series readCount read fresh data
            return
        self._check_page(page)
        self._c.update_progress(book_id, page)

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
