"""Real Komga media proxy."""

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from app.api.errors import ApiError
from app.komga import KomgaError

router = APIRouter(prefix="/api/media")


def _proxy(
    request: Request,
    path: str,
    params: dict | None = None,
    max_age: int = 3600,
) -> StreamingResponse:
    komga = request.app.state.komga
    try:
        upstream = komga.open_image(path, params)
    except KomgaError as err:
        raise ApiError(err.status, err.code, err.message) from None

    media_type = upstream.headers.get("content-type", "application/octet-stream")
    headers: dict[str, str] = {"Cache-Control": f"private, max-age={max_age}"}
    if "content-length" in upstream.headers:
        headers["Content-Length"] = upstream.headers["content-length"]

    return StreamingResponse(
        upstream.iter_bytes(chunk_size=65536),
        media_type=media_type,
        headers=headers,
        background=BackgroundTask(upstream.close),
    )


@router.get("/komga/series/{id}/thumb")
def series_thumb(request: Request, id: str) -> StreamingResponse:
    return _proxy(request, f"/api/v1/series/{id}/thumbnail")


@router.get("/komga/books/{id}/thumb")
def book_thumb(request: Request, id: str) -> StreamingResponse:
    return _proxy(request, f"/api/v1/books/{id}/thumbnail")


@router.get("/komga/books/{id}/pages/{n}")
def book_page(request: Request, id: str, n: int) -> StreamingResponse:
    if n < 1:
        raise ApiError(404, "not_found", "Media not found")
    return _proxy(request, f"/api/v1/books/{id}/pages/{n}", params={"zero_based": "false"})


@router.get("/komga/books/{id}/pages/{n}/thumb")
def book_page_thumb(request: Request, id: str, n: int) -> StreamingResponse:
    if n < 1:
        raise ApiError(404, "not_found", "Media not found")
    return _proxy(
        request,
        f"/api/v1/books/{id}/pages/{n}/thumbnail",
        params={"zero_based": "false"},
        max_age=86400,
    )
