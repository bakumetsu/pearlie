"""Komga adapter: the only place that knows Komga paths, JSON fields and the sort syntax."""

from __future__ import annotations

import re
from collections.abc import Iterator

import httpx

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
from app.komga import Komga
from app.targets.placement import ONESHOTS_FIELD

_ID_RE = re.compile(r"[A-Za-z0-9]{1,64}")
_SORTS = {SORT_CREATED_DESC: "createdDate,desc", SORT_NUMBER_ASC: "number,asc"}


class _KomgaImage:
    """A streaming Komga image answer."""

    def __init__(self, resp: httpx.Response) -> None:
        self._resp = resp
        self.content_type = resp.headers.get("content-type", "application/octet-stream")
        self.content_length = resp.headers.get("content-length")

    def iter_bytes(self, chunk_size: int = 65536) -> Iterator[bytes]:
        return self._resp.iter_bytes(chunk_size=chunk_size)

    def close(self) -> None:
        self._resp.close()


def _links(meta: dict) -> list[tuple[str, str]]:
    return [(str(x.get("label", "")), str(x.get("url", ""))) for x in meta.get("links") or []]


def book_dto(d: dict) -> BookDTO:
    meta = d.get("metadata") or {}
    rp = d.get("readProgress")
    return BookDTO(
        id=str(d.get("id", "")),
        library_id=str(d.get("libraryId", "")),
        series_id=str(d.get("seriesId", "")),
        name=d.get("name", ""),
        title=meta.get("title") or d.get("name", ""),
        path=str(d.get("url", "")),
        created_at=d.get("created", ""),
        page_count=(d.get("media") or {}).get("pagesCount", 0),
        read_page=rp["page"] if rp else None,
        read_done=bool(rp and rp.get("completed")),
        deleted=bool(d.get("deleted")),
        summary=meta.get("summary") or "",
        tags=sorted(meta.get("tags", [])),
        links=_links(meta),
        writers=[a["name"] for a in meta.get("authors") or [] if a.get("role") == "writer"],
        authors=[str(a.get("name", "")) for a in meta.get("authors") or []],
    )


def series_dto(d: dict) -> SeriesDTO:
    meta = d.get("metadata") or {}
    book_tags = (d.get("booksMetadata") or {}).get("tags", [])
    return SeriesDTO(
        id=str(d["id"]),
        library_id=str(d.get("libraryId", "")),
        name=d["name"],
        title=meta.get("title") or d["name"],
        path=str(d.get("url", "")),
        created_at=d["created"],
        book_count=d["booksCount"],
        read_count=d["booksReadCount"],
        deleted=bool(d.get("deleted")),
        oneshot=bool(d.get("oneshot")),
        summary=meta.get("summary") or "",
        tags=sorted(set(meta.get("tags", [])) | set(book_tags)),
        links=_links(meta),
    )


def _page[T](reply: dict, page: int, size: int, items: list[T]) -> PageResult[T]:
    return PageResult(
        items=items,
        page=page,
        size=size,
        total_pages=int(reply.get("totalPages", 1)),
        total_items=int(reply.get("totalElements", len(items))),
    )


class KomgaBookServer:
    """`BookServer` over the raw `Komga` client (page numbers: Pearlie 1-based, Komga 0-based)."""

    kind = "komga"

    def __init__(self, client: Komga) -> None:
        self._c = client

    @property
    def client(self) -> Komga:
        return self._c

    def valid_id(self, id: str) -> bool:
        return _ID_RE.fullmatch(id) is not None

    # browse / library

    def list_libraries(self) -> list[LibraryDTO]:
        out = []
        for d in self._c.list_libraries():
            raw = d.get(ONESHOTS_FIELD)
            out.append(
                LibraryDTO(
                    id=str(d["id"]),
                    name=str(d.get("name", "")),
                    root=str(d.get("root", "")),
                    oneshots_dir=raw if isinstance(raw, str) else None,
                )
            )
        return out

    def list_series(
        self, page: int, size: int, q: str, sort: str, library_id: str | None = None
    ) -> PageResult[SeriesDTO]:
        reply = self._c.list_series(page - 1, size, q, _SORTS.get(sort, sort))
        return _page(reply, page, size, [series_dto(d) for d in reply["content"]])

    def list_books(
        self,
        page: int,
        size: int,
        q: str,
        sort: str,
        series_id: str | None = None,
        library_id: str | None = None,
    ) -> PageResult[BookDTO]:
        reply = self._c.list_books(
            page - 1, size, q, _SORTS.get(sort, sort), series_id=series_id, library_id=library_id
        )
        return _page(reply, page, size, [book_dto(d) for d in reply["content"]])

    def get_series(self, id: str) -> SeriesDTO:
        return series_dto(self._c.get_series(id))

    def get_book(self, id: str) -> BookDTO:
        return book_dto(self._c.get_book(id))

    def series_books(self, series_id: str) -> tuple[list[BookDTO], bool]:
        books, truncated = self._c.all_series_books(series_id)
        return [book_dto(d) for d in books], truncated

    # search / lookup

    def find_by_path(
        self, kind: Kind, library_id: str, path: str, text: str
    ) -> BookDTO | SeriesDTO | None:
        d = self._c.find_by_url(kind, library_id, path, text)
        if d is None:
            return None
        return book_dto(d) if kind == "books" else series_dto(d)

    # media

    def _open(self, path: str, params: dict | None = None) -> ImageStream:
        return _KomgaImage(self._c.open_image(path, params))

    def open_thumb(self, kind: Kind, id: str) -> ImageStream:
        return self._open(f"/api/v1/{kind}/{id}/thumbnail")

    def open_page(self, book_id: str, n: int) -> ImageStream:
        return self._open(f"/api/v1/books/{book_id}/pages/{n}", {"zero_based": "false"})

    def open_page_thumb(self, book_id: str, n: int, width: int) -> ImageStream:
        return self._open(f"/api/v1/books/{book_id}/pages/{n}/thumbnail", {"zero_based": "false"})

    # save target + scan

    def scan_library(self, library_id: str) -> None:
        self._c.scan_library(library_id)

    # trash / undo

    def list_deleted(self, kind: Kind, library_id: str) -> list[BookDTO | SeriesDTO]:
        mk = book_dto if kind == "books" else series_dto
        return [mk(d) for d in self._c.list_deleted(kind, library_id)]

    def purge_deleted(self, library_id: str) -> None:
        self._c.empty_trash(library_id)

    # tags / metadata / progress

    def set_tags(self, kind: Kind, id: str, tags: list[str]) -> None:
        self._c.set_tags(kind, id, tags)

    def set_metadata(self, kind: Kind, id: str, patch: MetadataPatch) -> None:
        body: dict = {}
        if patch.tags is not None:
            body.update(tags=patch.tags, tagsLock=True)
        if patch.title is not None:
            body.update(title=patch.title, titleLock=True)
        if patch.summary is not None:
            body.update(summary=patch.summary, summaryLock=True)
        if patch.links is not None:
            body.update(links=[{"label": a, "url": b} for a, b in patch.links], linksLock=True)
        if patch.writers is not None:
            body.update(
                authors=[{"name": n, "role": "writer"} for n in patch.writers], authorsLock=True
            )
        if not body:
            raise BookServerError("bad_request", "Empty metadata patch", 400)
        self._c.set_metadata(kind, id, body)

    def set_progress(self, book_id: str, page: int, completed: bool) -> None:
        self._c.set_progress(book_id, page, completed)

    # health

    def ping(self) -> str | None:
        self._c.list_libraries()  # raises on an unreachable or refusing server
        return None
