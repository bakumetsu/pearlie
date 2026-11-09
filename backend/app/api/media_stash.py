"""Media file-serving endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.api.errors import ApiError
from app.fixtures.mediagen import ensure_media, media_dir
from app.fixtures.store import store

router = APIRouter(prefix="/api/media")
_media_ready: bool = False


def _ensure() -> None:
    """Call ensure_media once."""
    global _media_ready
    if not _media_ready:
        ensure_media()
        _media_ready = True


def _n(id: str) -> int:
    """Parse id to int or raise 404."""
    try:
        return int(id)
    except ValueError:
        raise ApiError(404, "not_found", "Media not found") from None


def _file(path: Path, media_type: str) -> FileResponse:
    """Return FileResponse with cache/ETag headers, or 404 if missing."""
    if not path.is_file():
        raise ApiError(404, "not_found", "Media not found")
    st = path.stat()
    return FileResponse(
        path,
        media_type=media_type,
        headers={
            "Cache-Control": "no-store",
            "ETag": f'W/"{st.st_size}-{st.st_mtime_ns}"',
        },
    )


def _valid(col: str, id: str) -> dict:
    """Return raw item or raise 404 if absent/rejected."""
    raw: dict | None = getattr(store, col).get(id)
    if raw is None or "_rejected" in raw:
        raise ApiError(404, "not_found", "Media not found")
    return raw


@router.get("/stash/images/{id}/thumb")
def stash_image_thumb(id: str) -> FileResponse:
    """Serve image thumbnail."""
    _ensure()
    _valid("images", id)
    return _file(media_dir() / "images" / f"{_n(id) % 40}_thumb.jpg", "image/jpeg")


@router.get("/stash/images/{id}/full")
def stash_image_full(id: str) -> FileResponse:
    """Serve full-size image."""
    _ensure()
    _valid("images", id)
    return _file(media_dir() / "images" / f"{_n(id) % 40}.jpg", "image/jpeg")


@router.get("/stash/videos/{id}/poster")
def stash_video_poster(id: str) -> FileResponse:
    """Serve video poster."""
    _ensure()
    _valid("videos", id)
    return _file(media_dir() / "videos" / f"{_n(id) % 6}_poster.jpg", "image/jpeg")


@router.get("/stash/videos/{id}/stream")
def stash_video_stream(id: str) -> FileResponse:
    """Serve video stream."""
    _ensure()
    _valid("videos", id)
    return _file(media_dir() / "videos" / f"{_n(id) % 6}.mp4", "video/mp4")


@router.get(
    "/stash/scene/{id}/preview",
    response_class=FileResponse,
    responses={200: {"content": {"video/mp4": {}}}, 206: {"content": {"video/mp4": {}}}},
)
def stash_scene_preview(id: str) -> FileResponse:
    """Serve the 6 s fixture clip as the card preview (FileResponse answers Range)."""
    _ensure()
    _valid("videos", id)
    return _file(media_dir() / "videos" / f"{_n(id) % 6}.mp4", "video/mp4")


@router.get("/web/{source}/{post_id}/thumb")
def web_thumb(source: str, post_id: str) -> FileResponse:
    """Serve web post thumbnail."""
    _ensure()
    raw = store.web_raw(source, post_id)
    if raw is None or "_rejected" in raw:
        raise ApiError(404, "not_found", "Media not found")
    return _file(media_dir() / "images" / f"{_n(post_id) % 40}_thumb.jpg", "image/jpeg")


@router.get("/web/{source}/{post_id}/preview")
def web_preview(source: str, post_id: str) -> FileResponse:
    """Serve web post preview."""
    _ensure()
    raw = store.web_raw(source, post_id)
    if raw is None or "_rejected" in raw:
        raise ApiError(404, "not_found", "Media not found")
    return _file(media_dir() / "images" / f"{_n(post_id) % 40}.jpg", "image/jpeg")
