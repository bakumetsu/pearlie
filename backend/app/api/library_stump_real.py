"""Real Stump library router – delegates to the Stump REST API."""

import re
import secrets
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Query, Request

from app.api.errors import ApiError
from app.api.patch_rules import check_patch
from app.api.trash_real import result_of, stump_trash_of
from app.bookserver.base import (
    SORT_CREATED_DESC,
    BookDTO,
    BookServerError,
    Kind,
    PageResult,
    SeriesDTO,
)
from app.bookserver.factory import book_server_of
from app.bookserver.map import book_detail, book_item, series_detail, series_item
from app.db import connect
from app.filters.rules import load_rules
from app.filters.safe_mode import resolve_safe, visible_tags
from app.library.trash import TrashError
from app.models import (
    LibraryItem,
    LibraryItemDetail,
    Page,
    PatchBody,
    Problem,
    ProgressBody,
    ProgressResult,
    Tag,
    TrashResult,
)
from app.paging import clamp_page, clamp_page_size, pages_for
from app.stump_shuffle import ShuffleCache, fetch_all, page_slice, shuffled

router = APIRouter(prefix="/api")

_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")


def _check_id(request: Request, id: str) -> None:
    if not book_server_of(request.app).valid_id(id):
        raise ApiError(404, "not_found", "Item not found")


def _up(err: BookServerError) -> ApiError:
    return ApiError(err.status, err.code, err.message)


def _visible[T: (BookDTO, SeriesDTO)](request: Request, dtos: list[T]) -> list[T]:
    """Drop items Pearlie trashed that Stump still lists until its scan runs (or forever, if
    the scan or empty-trash did not happen): deleted, UNAVAILABLE or not yet scanned. Items
    Stump marks deleted are hidden for every owner (a purged row can leave a ghost)."""
    owned = request.app.state.trash.stump_owned_ids()
    return [d for d in dtos if not d.deleted and d.id not in owned]


def _hide_trashed(request: Request, id: str) -> None:
    if id in request.app.state.trash.stump_owned_ids():
        raise ApiError(404, "not_found", "Item not found")


def _cache(request: Request) -> ShuffleCache:
    cache: ShuffleCache | None = getattr(request.app.state, "stump_shuffle", None)
    if cache is None:
        cache = ShuffleCache()
        request.app.state.stump_shuffle = cache
    return cache


def _rating_of(request: Request, kind: str, id: str) -> int | None:
    return _ratings(request, kind, [id]).get(id)


def _ratings(request: Request, kind: str, ids: list[str]) -> dict[str, int]:
    """Ratings Pearlie keeps for Stump items (Stump has no rating field)."""
    if not ids:
        return {}
    conn = connect(request.app.state.settings.db_path)
    try:
        marks = ",".join("?" * len(ids))
        rows = conn.execute(
            f"SELECT item_id, rating FROM stump_ratings WHERE kind = ? AND item_id IN ({marks})",
            [kind, *ids],
        ).fetchall()
    finally:
        conn.close()
    return {r["item_id"]: r["rating"] for r in rows}


def _store_rating(request: Request, kind: str, id: str, rating: int | None) -> None:
    conn = connect(request.app.state.settings.db_path)
    try:
        if rating is None:
            conn.execute("DELETE FROM stump_ratings WHERE kind = ? AND item_id = ?", (kind, id))
        else:
            conn.execute(
                "INSERT INTO stump_ratings (kind, item_id, rating) VALUES (?, ?, ?) "
                "ON CONFLICT (kind, item_id) DO UPDATE SET rating = excluded.rating",
                (kind, id, rating),
            )
        conn.commit()
    finally:
        conn.close()


def _rated(request: Request, kind: str, items: list[LibraryItem]) -> list[LibraryItem]:
    ratings = _ratings(request, kind, [i.id for i in items])
    for item in items:
        item.rating = ratings.get(item.id)
    return items


def _random_page(
    request: Request,
    kind: str,
    list_fn: Callable[[int, int, str, str], PageResult],
    mapper: Callable[[Any], LibraryItem],
    page: int,
    page_size: int,
    q: str,
    seed: int | None,
    favorite: bool | None,
) -> Page[LibraryItem]:
    seed_val = seed if seed is not None else secrets.randbelow(10**8)
    cache = _cache(request)
    key = (kind, q, seed_val)
    cached = cache.get(key)
    if cached is None:
        try:
            all_dtos, truncated = fetch_all(
                lambda p0, size: _as_reply(list_fn(p0 + 1, size, q, SORT_CREATED_DESC))
            )
        except BookServerError as e:
            raise _up(e) from None
        ordered = shuffled(all_dtos, seed_val)
        cache.put(key, ordered, truncated)
    else:
        ordered, truncated = cached
    pages = pages_for(len(ordered), page_size)
    page = clamp_page(page, pages)
    chunk, next_page = page_slice(ordered, page, page_size)
    notice: Problem | None
    if truncated:
        notice = Problem(
            code="list_truncated",
            message="Random covers only the first 20000 items of this library",
        )
    else:
        notice = _ignored_notice("newest", favorite)
    return Page[LibraryItem](
        items=_rated(request, kind, [mapper(r) for r in _visible(request, chunk)]),
        page=page,
        page_size=page_size,
        pages=pages,
        total=len(ordered),
        next_page=next_page,
        notice=notice,
        seed=seed_val,
    )


def _as_reply(res: PageResult) -> dict:
    """Shape a `PageResult` for `fetch_all` (0-based page index, content/last)."""
    return {"content": res.items, "last": res.last}


def _ignored_notice(sort: str, favorite: bool | None) -> Problem | None:
    parts: list[str] = []
    if sort == "rating":
        parts.append(f"sort={sort}")
    if favorite is not None:
        parts.append(f"favorite={str(favorite).lower()}")
    if not parts:
        return None
    return Problem(
        code="option_ignored",
        message=f"Ignored: {', '.join(parts)} (not supported for Stump)",
    )


def fetch_book_page(
    fetch: Callable[[int, int], PageResult], page: int, page_size: int
) -> tuple[PageResult, int, int]:
    """Fetch a 1-based page; past the end, serve the last page."""
    reply = fetch(page, page_size)
    pages = pages_for(reply.total_items, page_size)
    if page > max(pages, 1):
        served = clamp_page(page, pages)
        reply = fetch(served, page_size)
    else:
        served = page
    return (reply, pages, served)


@router.get("/library/stump/series", response_model=Page[LibraryItem])
def list_stump_series(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(60, ge=1, le=200),
    q: str = Query(""),
    sort: str = Query("newest", pattern="newest|rating|random"),
    favorite: bool | None = Query(None),
    seed: int | None = Query(None, ge=0, lt=10**8),
) -> Page[LibraryItem]:
    server = book_server_of(request.app)
    page_size = clamp_page_size("stump_series", page_size)
    if sort == "random":
        return _random_page(
            request, "series", server.list_series, series_item, page, page_size, q, seed, favorite
        )
    try:
        reply, pages, served = fetch_book_page(
            lambda p, size: server.list_series(p, size, q, SORT_CREATED_DESC), page, page_size
        )
    except BookServerError as e:
        raise _up(e) from None
    return Page[LibraryItem](
        items=_rated(request, "series", [series_item(r) for r in _visible(request, reply.items)]),
        page=served,
        page_size=page_size,
        pages=pages,
        total=reply.total_items,
        next_page=served + 1 if not reply.last else None,
        notice=_ignored_notice(sort, favorite),
    )


@router.get("/library/stump/books", response_model=Page[LibraryItem])
def list_stump_books(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(60, ge=1, le=200),
    q: str = Query(""),
    sort: str = Query("newest", pattern="newest|rating|random"),
    favorite: bool | None = Query(None),
    seed: int | None = Query(None, ge=0, lt=10**8),
) -> Page[LibraryItem]:
    server = book_server_of(request.app)
    page_size = clamp_page_size("stump_books", page_size)
    if sort == "random":
        return _random_page(
            request, "books", server.list_books, book_item, page, page_size, q, seed, favorite
        )
    try:
        reply, pages, served = fetch_book_page(
            lambda p, size: server.list_books(p, size, q, SORT_CREATED_DESC), page, page_size
        )
    except BookServerError as e:
        raise _up(e) from None
    return Page[LibraryItem](
        items=_rated(request, "books", [book_item(r) for r in _visible(request, reply.items)]),
        page=served,
        page_size=page_size,
        pages=pages,
        total=reply.total_items,
        next_page=served + 1 if not reply.last else None,
        notice=_ignored_notice(sort, favorite),
    )


def _apply_safe_tags(request: Request, detail: LibraryItemDetail) -> None:
    safe, allow_blurred = resolve_safe(request, None)
    if not safe or allow_blurred:
        return
    rules = load_rules(request.app.state.settings.db_path)
    detail.tags = visible_tags(detail.tags, rules, safe, allow_blurred)
    detail.inherited_tags = visible_tags(detail.inherited_tags, rules, safe, allow_blurred)


@router.get("/library/series/{id}")
def get_series(request: Request, id: str):
    _check_id(request, id)
    _hide_trashed(request, id)
    server = book_server_of(request.app)
    try:
        series = server.get_series(id)
        books, truncated = server.series_books(id)
    except BookServerError as e:
        raise _up(e) from None
    if series.deleted:
        raise ApiError(404, "not_found", "Item not found")
    detail = series_detail(series, books, truncated)
    detail.rating = _rating_of(request, "series", id)
    _apply_safe_tags(request, detail)
    return detail


@router.get("/library/books/{id}")
def get_book(request: Request, id: str):
    _check_id(request, id)
    _hide_trashed(request, id)
    server = book_server_of(request.app)
    try:
        book = server.get_book(id)
    except BookServerError as e:
        raise _up(e) from None
    if book.deleted:
        raise ApiError(404, "not_found", "Item not found")
    detail = book_detail(book)
    detail.rating = _rating_of(request, "books", id)
    _apply_safe_tags(request, detail)
    return detail


@router.patch("/library/series/{id}")
def patch_series(request: Request, id: str, body: PatchBody):
    return _patch(request, "series", id, body)


@router.patch("/library/books/{id}")
def patch_book(request: Request, id: str, body: PatchBody):
    return _patch(request, "books", id, body)


def _with_hidden_tags(request: Request, current: list[str], sent: list[str]) -> list[str]:
    """Add back the tags that safe mode hid from the client, so a tag edit keeps them."""
    safe, allow_blurred = resolve_safe(request, None)
    if not safe or allow_blurred:
        return sent
    rules = load_rules(request.app.state.settings.db_path)
    shown = {t.name for t in visible_tags([Tag(name=t) for t in current], rules, safe, False)}
    return sent + [t for t in current if t not in shown and t not in sent]


def _patch(request: Request, kind: Kind, id: str, body: PatchBody):
    _check_id(request, id)
    # Pearlie stores the rating itself, so only the favorite check applies here.
    check_patch("Stump", body.model_copy(update={"rating": None}))
    if body.tags is not None:
        for t in body.tags:
            if not t or len(t) > 64:
                raise ApiError(422, "invalid_tag", "Bad tag", field="tags")
    server = book_server_of(request.app)
    try:
        current = server.get_series(id) if kind == "series" else server.get_book(id)
        if body.tags is not None:
            server.set_tags(kind, id, _with_hidden_tags(request, current.tags, body.tags))
    except BookServerError as e:
        raise _up(e) from None
    if "rating" in body.model_fields_set:
        _store_rating(request, kind, id, body.rating)
    if kind == "series":
        return get_series(request, id)
    return get_book(request, id)


def _delete(request: Request, plural: str, id: str) -> TrashResult:
    _check_id(request, id)
    store = request.app.state.trash
    try:
        row = stump_trash_of(request).delete(plural, id)
    except TrashError as e:
        raise ApiError(e.status, e.code, e.message) from None
    return result_of(row, store.retention_days())


@router.delete("/library/series/{id}")
def delete_series(request: Request, id: str) -> TrashResult:
    return _delete(request, "series", id)


@router.delete("/library/books/{id}")
def delete_book(request: Request, id: str) -> TrashResult:
    return _delete(request, "books", id)


@router.post("/library/stump/books/{id}/progress", response_model=ProgressResult)
def set_progress(request: Request, id: str, body: ProgressBody) -> ProgressResult:
    _check_id(request, id)
    server = book_server_of(request.app)
    try:
        book = server.get_book(id)
    except BookServerError as e:
        raise _up(e) from None
    pages_count = book.page_count
    page = body.page
    if not (0 <= page <= pages_count):  # page 0 marks the book unread
        raise ApiError(422, "invalid", "Page out of range", field="page")
    completed = page >= pages_count > 0
    try:
        server.set_progress(id, page, completed)
    except BookServerError as e:
        raise _up(e) from None
    return ProgressResult(page=page, completed=completed)
