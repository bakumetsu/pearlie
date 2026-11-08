"""Real Komga library router – delegates to the Komga REST API."""

from fastapi import APIRouter, Query, Request

from app.api.errors import ApiError
from app.komga import (
    Komga,
    KomgaError,
    book_detail,
    book_item,
    series_detail,
    series_item,
)
from app.models import (
    LibraryItem,
    Page,
    PatchBody,
    Problem,
    ProgressBody,
    ProgressResult,
)

router = APIRouter(prefix="/api")


def _up(err: KomgaError) -> ApiError:
    return ApiError(err.status, err.code, err.message)


def _ignored_notice(sort: str, favorite: bool | None) -> Problem | None:
    parts: list[str] = []
    if sort in ("rating", "random"):
        parts.append(f"sort={sort}")
    if favorite is not None:
        parts.append(f"favorite={str(favorite).lower()}")
    if not parts:
        return None
    return Problem(
        code="option_ignored",
        message=f"Ignored: {', '.join(parts)} (Komga has no ratings or favorites)",
    )


@router.get("/library/komga/series", response_model=Page[LibraryItem])
def list_komga_series(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(60, ge=1, le=200),
    q: str = Query(""),
    sort: str = Query("newest", pattern="newest|rating|random"),
    favorite: bool | None = Query(None),
) -> Page[LibraryItem]:
    komga: Komga = request.app.state.komga
    try:
        # Pearlie pages are 1-based; Komga expects 0-based (sole conversion point).
        reply = komga.list_series(page=page - 1, size=page_size, sort="createdDate,desc", q=q)
    except KomgaError as e:
        raise _up(e) from None
    return Page[LibraryItem](
        items=[series_item(r) for r in reply["content"]],
        page=page,
        page_size=page_size,
        total=reply["totalElements"],
        next_page=page + 1 if not reply["last"] else None,
        notice=_ignored_notice(sort, favorite),
    )


@router.get("/library/komga/books", response_model=Page[LibraryItem])
def list_komga_books(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(60, ge=1, le=200),
    q: str = Query(""),
    sort: str = Query("newest", pattern="newest|rating|random"),
    favorite: bool | None = Query(None),
) -> Page[LibraryItem]:
    komga: Komga = request.app.state.komga
    try:
        # Pearlie pages are 1-based; Komga expects 0-based (sole conversion point).
        reply = komga.list_books(page=page - 1, size=page_size, sort="createdDate,desc", q=q)
    except KomgaError as e:
        raise _up(e) from None
    return Page[LibraryItem](
        items=[book_item(r) for r in reply["content"]],
        page=page,
        page_size=page_size,
        total=reply["totalElements"],
        next_page=page + 1 if not reply["last"] else None,
        notice=_ignored_notice(sort, favorite),
    )


@router.get("/library/series/{id}")
def get_series(request: Request, id: str):
    komga: Komga = request.app.state.komga
    try:
        series = komga.get_series(id)
        books = komga.all_series_books(id)
    except KomgaError as e:
        raise _up(e) from None
    return series_detail(series, books)


@router.get("/library/books/{id}")
def get_book(request: Request, id: str):
    komga: Komga = request.app.state.komga
    try:
        book = komga.get_book(id)
    except KomgaError as e:
        raise _up(e) from None
    return book_detail(book)


def _patch_handler(id: str, body: PatchBody) -> None:
    raise ApiError(501, "not_supported", "Editing and deleting Komga items is not available yet")


def _delete_handler(id: str) -> None:
    raise ApiError(501, "not_supported", "Editing and deleting Komga items is not available yet")


for _p in ("/library/series/{id}", "/library/books/{id}"):
    router.patch(_p)(_patch_handler)
    router.delete(_p)(_delete_handler)


@router.post("/library/komga/books/{id}/progress", response_model=ProgressResult)
def set_progress(request: Request, id: str, body: ProgressBody) -> ProgressResult:
    komga: Komga = request.app.state.komga
    try:
        book = komga.get_book(id)
    except KomgaError as e:
        raise _up(e) from None
    pages_count = book["media"]["pagesCount"]
    page = body.page
    if not (1 <= page <= pages_count):
        raise ApiError(422, "invalid", "Page out of range", field="page")
    completed = page >= pages_count
    try:
        komga.set_progress(id, page, completed)
    except KomgaError as e:
        raise _up(e) from None
    return ProgressResult(page=page, completed=completed)
