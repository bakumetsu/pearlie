"""Real Stash media proxy."""

import re
from urllib.parse import parse_qsl

from fastapi import APIRouter, Request
from fastapi.responses import Response, StreamingResponse
from starlette.background import BackgroundTask

from app.api.errors import ApiError
from app.targets import stash_library
from app.targets.stash_client import StashError

router = APIRouter(prefix="/api/media")

_NAME_RE = re.compile(r"^(stream\.(mp4|webm|m3u8|ts)|[0-9]+\.ts)$")
_RESOLUTION_RE = re.compile(r"^[A-Z0-9_]+$")
_RELAY_HEADERS = (
    "content-range",
    "content-length",
    "content-encoding",
    "accept-ranges",
    "etag",
    "last-modified",
)


def _check_id(id: str) -> None:
    if not stash_library.valid_id(id):
        raise ApiError(404, "not_found", "Media not found")


def _forward_range(request: Request) -> dict[str, str] | None:
    headers: dict[str, str] = {}
    if "range" in request.headers:
        headers["Range"] = request.headers["range"]
    if "if-range" in request.headers:
        headers["If-Range"] = request.headers["if-range"]
    return headers or None


def _stream(upstream, cache: str) -> StreamingResponse:
    media_type = upstream.headers.get("content-type", "application/octet-stream")
    headers: dict[str, str] = {"Cache-Control": cache}
    for h in _RELAY_HEADERS:
        if h in upstream.headers:
            headers[h.replace("-", " ").title().replace(" ", "-")] = upstream.headers[h]
    return StreamingResponse(
        upstream.iter_raw(),
        status_code=upstream.status_code,
        media_type=media_type,
        headers=headers,
        background=BackgroundTask(upstream.close),
    )


def _rewrite_uri(uri: str) -> str:
    """Reduce a segment URI to its last path segment, keeping only resolution."""
    if "?" in uri:
        path, query = uri.split("?", 1)
    else:
        path, query = uri, ""

    # Strip scheme + authority if absolute URL
    for prefix in ("https://", "http://"):
        if path.startswith(prefix):
            path = path[len(prefix):]
            break

    # After scheme removal path may be "host:port/a/b/c" or "/a/b/c" or "a/b/c"
    if "/" in path:
        path = path[path.index("/"):]

    parts = [p for p in path.split("/") if p]
    if not parts:
        return uri
    last = parts[-1]

    if query:
        res = [v for k, v in parse_qsl(query) if k == "resolution"]
        if res:
            return f"{last}?resolution={res[0]}"
    return last


def rewrite_m3u8(text: str) -> str:
    """Rewrite an m3u8 playlist so every URI is relative and apikey-free."""
    lines = text.splitlines()
    out: list[str] = []
    for line in lines:
        if line.startswith("#"):
            line = re.sub(
                r'URI="([^"]*)"',
                lambda m: f'URI="{_rewrite_uri(m.group(1))}"',
                line,
            )
            out.append(line)
        elif line.strip():
            out.append(_rewrite_uri(line.strip()))
        else:
            out.append(line)
    return "\n".join(out)


@router.get("/stash/images/{id}/thumb")
def image_thumb(request: Request, id: str) -> StreamingResponse:
    _check_id(id)
    stash = request.app.state.stash
    try:
        upstream = stash.open_media(f"/image/{id}/thumbnail")
    except StashError as err:
        raise ApiError(err.status, err.code, err.message) from None
    return _stream(upstream, "private, max-age=3600")


@router.get("/stash/images/{id}/full")
def image_full(request: Request, id: str) -> StreamingResponse:
    _check_id(id)
    stash = request.app.state.stash
    try:
        upstream = stash.open_media(f"/image/{id}/image")
    except StashError as err:
        raise ApiError(err.status, err.code, err.message) from None
    return _stream(upstream, "private, max-age=3600")


@router.get("/stash/videos/{id}/poster")
def video_poster(request: Request, id: str) -> StreamingResponse:
    _check_id(id)
    stash = request.app.state.stash
    try:
        upstream = stash.open_media(f"/scene/{id}/screenshot")
    except StashError as err:
        raise ApiError(err.status, err.code, err.message) from None
    return _stream(upstream, "private, max-age=3600")


@router.get(
    "/stash/scene/{id}/preview",
    response_class=StreamingResponse,
    responses={200: {"content": {"video/mp4": {}}}, 206: {"content": {"video/mp4": {}}}},
)
def scene_preview(request: Request, id: str):
    _check_id(id)
    stash = request.app.state.stash
    fwd = _forward_range(request)
    try:
        upstream = stash.open_media(f"/scene/{id}/preview", headers=fwd)
    except StashError as err:
        raise ApiError(err.status, err.code, err.message) from None
    return _stream(upstream, "private, max-age=3600")


@router.get("/stash/videos/{id}/stream")
def video_stream(request: Request, id: str):
    _check_id(id)
    stash = request.app.state.stash
    fwd = _forward_range(request)
    try:
        upstream = stash.open_media(f"/scene/{id}/stream", headers=fwd)
    except StashError as err:
        raise ApiError(err.status, err.code, err.message) from None
    return _stream(upstream, "private, max-age=0")


@router.get("/stash/videos/{id}/s/{name}")
def video_segment(request: Request, id: str, name: str):
    _check_id(id)
    if not _NAME_RE.match(name):
        raise ApiError(404, "not_found", "Media not found")

    # Forward only a valid resolution param; drop everything else (incl. apikey)
    params: dict[str, str] | None = None
    resolution = request.query_params.get("resolution")
    if resolution and _RESOLUTION_RE.match(resolution):
        params = {"resolution": resolution}

    stash = request.app.state.stash
    fwd = _forward_range(request)
    # Stash serves HLS segments under the playlist path: stream.m3u8/{n}.ts
    upstream_path = (
        f"/scene/{id}/stream.m3u8/{name}"
        if name[0].isdigit()
        else f"/scene/{id}/{name}"
    )
    try:
        upstream = stash.open_media(upstream_path, params=params, headers=fwd)
    except StashError as err:
        raise ApiError(err.status, err.code, err.message) from None

    # HLS manifest: read fully, rewrite, return as text
    if name == "stream.m3u8":
        body = upstream.read()
        upstream.close()
        text = body.decode("utf-8", errors="replace")
        rewritten = rewrite_m3u8(text)
        return Response(content=rewritten, media_type="application/vnd.apple.mpegurl")

    # Regular segment / stream
    return _stream(upstream, "private, max-age=0")
