"""Real book-server media proxy."""

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from app.api.errors import ApiError
from app.api.library_komga_real import _check_id
from app.bookserver.base import BookServerError, ImageStream
from app.bookserver.factory import book_server_of

router = APIRouter(prefix="/api/media")

# Page-thumbnail width asked of servers that cannot make one natively.
_PAGE_THUMB_WIDTH = 300


def _proxy(request: Request, open_stream, max_age: int = 3600) -> StreamingResponse:
    server = book_server_of(request.app)
    try:
        upstream: ImageStream = open_stream(server)
    except BookServerError as err:
        raise ApiError(err.status, err.code, err.message) from None

    media_type = upstream.content_type
    if not media_type.split(";", 1)[0].strip().lower().startswith("image/"):
        upstream.close()
        raise ApiError(502, "upstream_error", "Komga returned a non-image")
    headers: dict[str, str] = {"Cache-Control": f"private, max-age={max_age}"}
    if upstream.content_length is not None:
        headers["Content-Length"] = upstream.content_length

    return StreamingResponse(
        upstream.iter_bytes(),
        media_type=media_type,
        headers=headers,
        background=BackgroundTask(upstream.close),
    )


@router.get("/komga/series/{id}/thumb")
def series_thumb(request: Request, id: str) -> StreamingResponse:
    _check_id(request, id)
    return _proxy(request, lambda s: s.open_thumb("series", id))


@router.get("/komga/books/{id}/thumb")
def book_thumb(request: Request, id: str) -> StreamingResponse:
    _check_id(request, id)
    return _proxy(request, lambda s: s.open_thumb("books", id))


@router.get("/komga/books/{id}/pages/{n}")
def book_page(request: Request, id: str, n: int) -> StreamingResponse:
    _check_id(request, id)
    if n < 1:
        raise ApiError(404, "not_found", "Media not found")
    return _proxy(request, lambda s: s.open_page(id, n))


@router.get("/komga/books/{id}/pages/{n}/thumb")
def book_page_thumb(request: Request, id: str, n: int) -> StreamingResponse:
    _check_id(request, id)
    if n < 1:
        raise ApiError(404, "not_found", "Media not found")
    return _proxy(request, lambda s: s.open_page_thumb(id, n, _PAGE_THUMB_WIDTH), max_age=86400)
