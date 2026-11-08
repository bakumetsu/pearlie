"""Komga media file-serving endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import FileResponse, Response

from app.api.errors import ApiError
from app.api.media_stash import _ensure, _file, _n, _valid
from app.fixtures.mediagen import media_dir, read_cbz_page

router = APIRouter(prefix="/api/media")


@router.get("/komga/series/{id}/thumb")
def komga_series_thumb(id: str) -> FileResponse:
    """Serve series cover."""
    _ensure()
    _valid("series", id)
    return _file(media_dir() / "books" / f"{(_n(id) * 3) % 5}_thumb.jpg", "image/jpeg")


@router.get("/komga/books/{id}/thumb")
def komga_book_thumb(id: str) -> FileResponse:
    """Serve book cover."""
    _ensure()
    _valid("books", id)
    return _file(media_dir() / "books" / f"{_n(id) % 5}_thumb.jpg", "image/jpeg")


@router.get("/komga/books/{id}/pages/{n}")
def komga_book_page(id: str, n: int) -> Response:
    """Serve a CBZ page as JPEG bytes."""
    _ensure()
    raw = _valid("books", id)
    if n < 1 or n > raw.get("page_count", 0):
        raise ApiError(404, "not_found", "Media not found")
    cbz = media_dir() / "books" / f"{_n(id) % 5}.cbz"
    data = read_cbz_page(cbz, n)
    return Response(
        content=data,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=3600", "ETag": f'W/"{id}-{n}"'},
    )
