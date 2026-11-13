"""Real web-source media proxy: the browser never loads a booru or nhentai CDN directly."""

from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Literal
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from app.api.errors import ApiError
from app.sources.base import Post, Source, SourceError
from app.sources.throttle import DEFAULT_PACE, Throttle

router = APIRouter(prefix="/api/media")

Kind = Literal["thumb", "preview", "full"]

VIDEO_EXTS = (".mp4", ".webm", ".mov", ".m4v", ".mkv")
# CDN files are not API calls: a tenth of the API pace, with the same back-off on 429/503.
MEDIA_PACE_FACTOR = 0.1
_MEMORY = 512
_RELAY_HEADERS = ("content-range", "content-length", "accept-ranges", "etag", "last-modified")
_DROP_REQUEST_HEADERS = {"cookie", "authorization"}
_VALID_ID_CHARS = frozenset("0123456789")


def proxy_path(source: str, post_id: str, kind: Kind) -> str:
    return f"/api/media/web/{source}/{post_id}/{kind}"


def tile_url(post: Post) -> str | None:
    """The ~850 px sample, else the preview (video samples fall back)."""
    sample = post.sample_url
    if sample and not sample.lower().split("?", 1)[0].endswith(VIDEO_EXTS):
        return sample
    return post.preview_url


def media_kind(post: Post) -> Literal["image", "video"]:
    """What the preview URL serves, from the file extension (query string ignored)."""
    url = pick_url(post, "preview") or ""
    return "video" if url.lower().split("?", 1)[0].endswith(VIDEO_EXTS) else "image"


def pick_url(post: Post, kind: Kind) -> str | None:
    if kind == "thumb":
        return tile_url(post)
    if kind == "preview":
        return post.file_url or post.preview_url
    return post.file_url or post.sample_url or post.preview_url


class _Memory:
    """Small LRU of post metadata (URLs only, never media) filled by search."""

    def __init__(self) -> None:
        self._posts: OrderedDict[tuple[str, str], Post] = OrderedDict()
        self._lock = threading.Lock()

    def put(self, post: Post) -> None:
        with self._lock:
            self._posts[(post.source, post.post_id)] = post
            self._posts.move_to_end((post.source, post.post_id))
            while len(self._posts) > _MEMORY:
                self._posts.popitem(last=False)

    def get(self, source: str, post_id: str) -> Post | None:
        with self._lock:
            return self._posts.get((source, post_id))


def _memory(request_or_app) -> _Memory:
    state = getattr(request_or_app, "app", request_or_app).state
    mem = getattr(state, "web_posts", None)
    if mem is None:
        mem = state.web_posts = _Memory()
    return mem


def remember(app, posts: list[Post]) -> None:
    mem = _memory(app)
    for p in posts:
        mem.put(p)


def _throttle(request: Request, src: Source) -> Throttle:
    state = request.app.state
    table: dict[str, Throttle] | None = getattr(state, "web_media_throttles", None)
    if table is None:
        table = state.web_media_throttles = {}
    if src.id not in table:
        table[src.id] = Throttle(DEFAULT_PACE.get(src.id, 1.0) * MEDIA_PACE_FACTOR, site=src.id)
    return table[src.id]


def _referer(src: Source) -> str:
    base = str(getattr(src, "_base_url", ""))
    parts = urlparse(base)
    host = (parts.hostname or "").removeprefix("api.")
    return f"{parts.scheme}://{host}/" if host else ""


def _request_headers(request: Request, src: Source) -> dict[str, str]:
    auth = getattr(src, "_auth", None)
    headers: dict[str, str] = {}
    if auth is not None:
        headers.update(
            {k: v for k, v in auth().headers.items() if k.lower() not in _DROP_REQUEST_HEADERS}
        )
    referer = _referer(src)
    if referer:
        headers["Referer"] = referer
    for name in ("range", "if-range"):
        if name in request.headers:
            headers[name.title()] = request.headers[name]
    return headers


def _resolve(request: Request, src: Source, post_id: str, kind: Kind) -> str:
    post = _memory(request).get(src.id, post_id)
    if post is None:
        if not post_id or not set(post_id) <= _VALID_ID_CHARS:
            raise ApiError(404, "not_found", "Media not found")
        try:
            post = src.get_post(post_id)
        except SourceError as e:
            raise ApiError(404 if e.code == "not_found" else 502, e.code, e.message) from None
        _memory(request).put(post)
    url = pick_url(post, kind)
    if not url:
        raise ApiError(404, "not_found", "Media not found")
    host = urlparse(url).hostname or ""
    if urlparse(url).scheme not in ("http", "https") or host not in src.file_hosts:
        raise ApiError(404, "not_found", "Media not found")
    return url


@router.get("/web/{source}/{post_id}/{kind}")
def web_media(request: Request, source: str, post_id: str, kind: str) -> StreamingResponse:
    sources: dict[str, Source] = request.app.state.sources
    src = sources.get(source)
    if src is None or kind not in ("thumb", "preview", "full"):
        raise ApiError(404, "not_found", "Media not found")
    url = _resolve(request, src, post_id, kind)  # type: ignore[arg-type]
    throttle = _throttle(request, src)
    client: httpx.Client = src._client  # type: ignore[attr-defined]
    throttle.wait()
    try:
        upstream = client.send(
            client.build_request("GET", url, headers=_request_headers(request, src)),
            stream=True,
        )
    except httpx.HTTPError:
        raise ApiError(502, "upstream_error", "The site is unreachable") from None
    throttle.report(upstream.status_code, _retry_after(upstream))
    media_type = upstream.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    status = upstream.status_code
    if status not in (200, 206) or not media_type.startswith(("image/", "video/")):
        upstream.close()
        if status == 404:
            raise ApiError(404, "not_found", "Media not found")
        code = "rate_limited" if status == 429 else "upstream_error"
        raise ApiError(502, code, f"The site returned {status}")
    headers = {"Cache-Control": "private, max-age=3600"}
    for h in _RELAY_HEADERS:
        if h in upstream.headers:
            headers["-".join(w.capitalize() for w in h.split("-"))] = upstream.headers[h]
    return StreamingResponse(
        upstream.iter_raw(),
        status_code=status,
        media_type=media_type,
        headers=headers,
        background=BackgroundTask(upstream.close),
    )


def _retry_after(resp: httpx.Response) -> float | None:
    try:
        return float(resp.headers["Retry-After"])
    except (KeyError, ValueError):
        return None
