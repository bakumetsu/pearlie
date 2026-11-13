"""Real web-source media proxy: the browser never loads a booru or nhentai CDN directly."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urljoin, urlparse

import httpx
from fastapi import APIRouter, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.background import BackgroundTask

from app.api.errors import ApiError
from app.db import connect
from app.filters.rules import evaluate, load_rules
from app.sources.base import Post, Source, SourceError
from app.sources.throttle import DEFAULT_PACE, Throttle
from app.thumbcache import MAX_THUMB_BYTES, ThumbCache, sniff_image_type
from app.thumbcache import SOURCES as CACHED_SOURCES

logger = logging.getLogger("pearlie.media_web")

router = APIRouter(prefix="/api/media")

Kind = Literal["thumb", "preview", "full"]

VIDEO_EXTS = (".mp4", ".webm", ".mov", ".m4v", ".mkv")
# CDN files are not API calls: a tenth of the API pace, with the same back-off on 429/503.
MEDIA_PACE_FACTOR = 0.1
_MEMORY = 5000
# Thumbnail lane (D-17): own throttle per site, one miss at a time.
THUMB_PACE = 0.25
MAX_REDIRECTS = 2
FAILURE_TTL = 60.0
THUMB_TIMEOUT = 10.0
THUMB_CACHE_CONTROL = "private, max-age=86400"
_THUMB_ID = re.compile(r"[A-Za-z0-9_-]{1,32}")
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
        self._rules_version: int | None = None

    def sync_rules(self, version: int) -> None:
        """Empty the map when the rules changed: a newly hidden post must not stay served."""
        with self._lock:
            if self._rules_version is not None and self._rules_version != version:
                self._posts.clear()
            self._rules_version = version

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


def remember(app, posts: list[Post], rules_version: int | None = None) -> None:
    """Record posts that passed the rules (never hidden ones)."""
    mem = _memory(app)
    if rules_version is not None:
        mem.sync_rules(rules_version)
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
    if not _host_ok(src, url, ("http", "https")):
        raise ApiError(404, "not_found", "Media not found")
    return url


def _host_ok(src: Source, url: str, schemes: tuple[str, ...]) -> bool:
    parts = urlparse(url)
    return parts.scheme in schemes and (parts.hostname or "") in src.file_hosts


@router.get("/web/{source}/{post_id}/{kind}")
async def web_media(request: Request, source: str, post_id: str, kind: str) -> Response:
    sources: dict[str, Source] = request.app.state.sources
    src = sources.get(source)
    if src is None or kind not in ("thumb", "preview", "full"):
        raise ApiError(404, "not_found", "Media not found")
    if kind == "thumb":
        return await _thumb(request, src, post_id)
    return await run_in_threadpool(_stream_media, request, src, post_id, kind)


def _stream_media(request: Request, src: Source, post_id: str, kind: str) -> StreamingResponse:
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


# ---- thumbnails: cache, own lane, shared in-flight fetch (D-17) ----


@dataclass
class _Thumb:
    data: bytes
    media_type: str
    etag: str


@dataclass
class _Refused:
    status: int
    code: str
    message: str
    retry_after: int | None = None


@dataclass
class _Lane:
    throttle: Throttle
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


@dataclass
class _Flight:
    task: asyncio.Task[_Thumb | _Refused | None] | None = None
    waiters: int = 0


def _table(app, name: str) -> dict:
    table = getattr(app.state, name, None)
    if table is None:
        table = {}
        setattr(app.state, name, table)
    return table


def _lane(app, src: Source) -> _Lane:
    lanes = _table(app, "web_thumb_lanes")
    if src.id not in lanes:
        lanes[src.id] = _Lane(Throttle(THUMB_PACE, site=src.id))
    return lanes[src.id]


def _etag(source: str, post_id: str, size: int) -> str:
    digest = hashlib.sha256(f"{source}\0{post_id}".encode()).hexdigest()
    return f'"{digest[:16]}-{size}"'


def _rules_version(db_path) -> int:
    conn = connect(db_path)
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = 'rules.version'").fetchone()
    finally:
        conn.close()
    return int(row["value"]) if row else 1


def _authorize(request: Request, src: Source, post_id: str) -> Post:
    """The post, only when it passed the rules: known from search, else get_post + evaluate."""
    mem = _memory(request)
    db_path = request.app.state.settings.db_path
    mem.sync_rules(_rules_version(db_path))
    post = mem.get(src.id, post_id)
    if post is not None:
        return post
    if not post_id.isdigit():
        raise ApiError(404, "not_found", "Media not found")
    try:
        post = src.get_post(post_id)
    except SourceError as e:
        raise ApiError(404 if e.code == "not_found" else 502, e.code, e.message) from None
    rules = load_rules(db_path)
    verdict = evaluate(post.tags, rules)
    if verdict is not None and verdict.decision != "warn":
        raise ApiError(404, "not_found", "Media not found")
    mem.sync_rules(rules.version)
    mem.put(post)
    return post


def _cached(cache: ThumbCache | None, source: str, post_id: str) -> _Thumb | None:
    if cache is None:
        return None
    path = cache.get(source, post_id)
    if path is None:
        return None
    try:
        data = path.read_bytes()
    except OSError:
        return None
    media_type = sniff_image_type(data[:16])
    if media_type is None:
        return None
    return _Thumb(data, media_type, _etag(source, post_id, len(data)))


def _thumb_response(request: Request, thumb: _Thumb) -> Response:
    headers = {"Cache-Control": THUMB_CACHE_CONTROL, "ETag": thumb.etag}
    if request.headers.get("if-none-match") == thumb.etag:
        return Response(status_code=304, headers=headers)
    return Response(thumb.data, media_type=thumb.media_type, headers=headers)


def _refusal_response(refused: _Refused) -> Response:
    if refused.status == 503:
        return JSONResponse(
            status_code=503,
            content={"code": refused.code, "message": refused.message},
            headers={"Retry-After": str(refused.retry_after or 5)},
        )
    raise ApiError(refused.status, refused.code, refused.message)


def _recent_failure(app, key: tuple[str, str]) -> _Refused | None:
    failures = _table(app, "web_thumb_failures")
    entry = failures.get(key)
    if entry is None:
        return None
    if entry[0] < time.monotonic():
        failures.pop(key, None)
        return None
    return entry[1]


def _note_failure(app, key: tuple[str, str], refused: _Refused) -> None:
    failures = _table(app, "web_thumb_failures")
    now = time.monotonic()
    if len(failures) > 2000:
        for k in [k for k, (until, _r) in failures.items() if until < now]:
            failures.pop(k, None)
    failures[key] = (now + FAILURE_TTL, refused)


async def _thumb(request: Request, src: Source, post_id: str) -> Response:
    if src.id not in CACHED_SOURCES or not _THUMB_ID.fullmatch(post_id):
        raise ApiError(404, "not_found", "Media not found")
    post = await run_in_threadpool(_authorize, request, src, post_id)
    cache: ThumbCache | None = getattr(request.app.state, "thumb_cache", None)
    hit = await run_in_threadpool(_cached, cache, src.id, post_id)
    if hit is not None:
        logger.debug("site=%s post=%s hit", src.id, post_id)
        return _thumb_response(request, hit)
    key = (src.id, post_id)
    failed = _recent_failure(request.app, key)
    if failed is not None:
        return _refusal_response(failed)
    url = tile_url(post)
    if not url or not _host_ok(src, url, ("http", "https")):
        raise ApiError(404, "not_found", "Media not found")
    flights: dict[tuple[str, str], _Flight] = _table(request.app, "web_thumb_flights")
    outcome: _Thumb | _Refused | None = None
    for _ in range(2):
        flight = flights.get(key)
        if flight is None:
            flight = flights[key] = _Flight()
            flight.task = asyncio.create_task(_run_miss(request.app, src, key, url, cache, flight))
        task = flight.task
        assert task is not None
        flight.waiters += 1
        try:
            while not task.done():
                await asyncio.wait({task}, timeout=0.25)
                if not task.done() and await request.is_disconnected():
                    return Response(status_code=499)
        finally:
            flight.waiters -= 1
        outcome = task.result()
        if outcome is not None:
            break
    if isinstance(outcome, _Thumb):
        return _thumb_response(request, outcome)
    if isinstance(outcome, _Refused):
        return _refusal_response(outcome)
    raise ApiError(502, "upstream_error", "The thumbnail could not be loaded")


async def _run_miss(
    app,
    src: Source,
    key: tuple[str, str],
    url: str,
    cache: ThumbCache | None,
    flight: _Flight,
) -> _Thumb | _Refused | None:
    """Fetch through the site's thumb lane. None means: abandoned, nobody waits any more."""
    flights = _table(app, "web_thumb_flights")
    try:
        lane = _lane(app, src)
        async with lane.lock:
            if flight.waiters <= 0:
                return None
            main: Throttle | None = getattr(src, "_throttle", None)
            floor = main.interval if main is not None and main.backing_off else 0.0
            delay = lane.throttle.reserve(floor)
            if delay > 0:
                await asyncio.sleep(delay)
            if flight.waiters <= 0:
                return None
            outcome = await run_in_threadpool(_fetch_thumb, src, key[1], url, lane.throttle)
        if isinstance(outcome, _Refused):
            logger.warning("site=%s post=%s err status=%d", key[0], key[1], outcome.status)
            if outcome.status in (404, 502):
                _note_failure(app, key, outcome)
            return outcome
        stored = False
        if cache is not None:
            stored = await run_in_threadpool(cache.put, key[0], key[1], outcome.data)
        logger.info("site=%s post=%s miss stored=%s", key[0], key[1], stored)
        return outcome
    except Exception as exc:  # noqa: BLE001 - the waiters get a 502, never a traceback
        logger.warning("site=%s post=%s err %s", key[0], key[1], type(exc).__name__)
        return _Refused(502, "upstream_error", "The thumbnail could not be loaded")
    finally:
        if flights.get(key) is flight:
            del flights[key]


def _fetch_thumb(src: Source, post_id: str, url: str, lane: Throttle) -> _Thumb | _Refused:
    """One upstream GET: allow-listed host, at most 2 re-checked redirects, 5 MB image only."""
    client: httpx.Client = src._client  # type: ignore[attr-defined]
    main: Throttle | None = getattr(src, "_throttle", None)
    referer = _referer(src)
    headers = {"Referer": referer} if referer else {}
    current = url
    hops = 0
    while True:
        try:
            resp = client.send(
                client.build_request("GET", current, headers=headers, timeout=THUMB_TIMEOUT),
                stream=True,
                follow_redirects=False,
            )
        except httpx.HTTPError:
            return _Refused(502, "upstream_error", "The site is unreachable")
        try:
            status = resp.status_code
            if status in (301, 302, 303, 307, 308):
                target = urljoin(current, resp.headers.get("location", ""))
                if hops >= MAX_REDIRECTS or not _host_ok(src, target, ("https",)):
                    return _Refused(502, "upstream_error", "The site redirected the thumbnail")
                hops += 1
                current = target
                continue
            retry_after = _retry_after(resp)
            lane.report(status, retry_after)
            if status in (429, 503):
                if main is not None:
                    main.report(status, retry_after)
                wait = int(retry_after or 5)
                return _Refused(503, "rate_limited", "The site asked to slow down", wait)
            if status in (404, 410):
                return _Refused(404, "not_found", "Media not found")
            media_type = resp.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            is_image = media_type.startswith("image/") and media_type != "image/svg+xml"
            if status != 200 or not is_image:
                return _Refused(502, "upstream_error", f"The site returned {status}")
            declared = resp.headers.get("content-length", "")
            if declared.isdigit() and int(declared) > MAX_THUMB_BYTES:
                return _Refused(502, "upstream_error", "The thumbnail is too large")
            buf = bytearray()
            for chunk in resp.iter_bytes():
                buf += chunk
                if len(buf) > MAX_THUMB_BYTES:
                    return _Refused(502, "upstream_error", "The thumbnail is too large")
            data = bytes(buf)
            sniffed = sniff_image_type(data[:16])
            if sniffed is None:
                return _Refused(502, "upstream_error", "The site sent no image")
            return _Thumb(data, sniffed, _etag(src.id, post_id, len(data)))
        except httpx.HTTPError:
            return _Refused(502, "upstream_error", "The site is unreachable")
        finally:
            resp.close()
