"""nhentai gallery routes for the web reader: /book metadata, page images and page thumbs."""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, cast

import httpx
from fastapi import APIRouter, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.background import BackgroundTask

from app.api.errors import ApiError
from app.api.image_slots import Busy, Gone, Limiter, Prio, Slot, SlotScheduler, parse_prio
from app.api.media_web_real import proxy_path
from app.db import connect
from app.filters.rules import evaluate, load_rules
from app.models import Tag, WebBook, WebItem
from app.sources.base import Post, SourceError
from app.sources.nhentai import CDN_HOST, NHentai
from app.sources.title import LANGUAGES, parse_title

logger = logging.getLogger("pearlie.media_web_pages")

router = APIRouter(prefix="/api/media/web/nhentai")

META_TTL = 600.0
META_MAX = 64
MAX_PAGE_BYTES = 20 * 1024 * 1024
PAGE_TIMEOUT = 45.0
THUMB_TIMEOUT = 15.0
SHARDS = 4
PAGE_CACHE_CONTROL = "private, max-age=3600"
IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"})
_SETTING_KEYS = {"t": "image_slots_thumb_max", "i": "image_slots_page_max"}


@dataclass
class _Meta:
    post: Post
    expires: float
    rules_version: int
    hidden: bool


class _Refusal(Exception):
    def __init__(self, status: int, code: str, message: str, retry_after: int | None = None):
        self.status, self.code, self.message, self.retry_after = status, code, message, retry_after


def _refusal_response(r: _Refusal) -> Response:
    headers = {"Cache-Control": "no-store"}
    if r.retry_after is not None:
        headers["Retry-After"] = str(r.retry_after)
    return JSONResponse(
        status_code=r.status, content={"code": r.code, "message": r.message}, headers=headers
    )


def _nhentai(request: Request) -> NHentai:
    src = request.app.state.sources.get("nhentai")
    if src is None:
        raise ApiError(404, "not_found", "Media not found")
    return cast(NHentai, src)


def _db_int(db_path, key: str) -> int | None:
    conn = connect(db_path)
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    finally:
        conn.close()
    try:
        v = int(row["value"]) if row else None
    except (ValueError, TypeError):
        return None
    return v if v is not None and 1 <= v <= 32 else None


def _scheduler(request: Request) -> SlotScheduler:
    state = request.app.state
    sched = getattr(state, "image_slots", None)
    if sched is None:
        db_path = state.settings.db_path
        sched = state.image_slots = SlotScheduler(
            lambda host_class: _db_int(db_path, _SETTING_KEYS[host_class])
        )
    return sched


def _rules_version(db_path) -> int:
    conn = connect(db_path)
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = 'rules.version'").fetchone()
    finally:
        conn.close()
    return int(row["value"]) if row else 1


class _MetaCache:
    def __init__(self) -> None:
        self._rows: OrderedDict[str, _Meta] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> _Meta | None:
        with self._lock:
            meta = self._rows.get(key)
            if meta is not None and meta.expires < time.monotonic():
                del self._rows[key]
                return None
            if meta is not None:
                self._rows.move_to_end(key)
            return meta

    def put(self, key: str, meta: _Meta) -> None:
        with self._lock:
            self._rows[key] = meta
            self._rows.move_to_end(key)
            while len(self._rows) > META_MAX:
                self._rows.popitem(last=False)


def _meta_cache(request: Request) -> _MetaCache:
    state = request.app.state
    cache = getattr(state, "web_book_meta", None)
    if cache is None:
        cache = state.web_book_meta = _MetaCache()
    return cache


def _load_meta(request: Request, src: NHentai, gid: str) -> Post:
    """The gallery post (10-min cache, one API call per gallery); hidden by rules is 404."""
    if not gid.isdigit():
        raise _Refusal(404, "not_found", "Gallery not found")
    db_path = request.app.state.settings.db_path
    cache = _meta_cache(request)
    version = _rules_version(db_path)
    meta = cache.get(gid)
    if meta is None or meta.rules_version != version:
        try:
            post = src.get_post(gid)
        except SourceError as e:
            if e.code == "not_found":
                raise _Refusal(404, "not_found", "Gallery not found") from None
            if e.code == "rate_limited":
                raise _Refusal(429, "rate_limited", e.message, 5) from None
            raise _Refusal(502, "upstream_error", e.message) from None
        rules = load_rules(db_path)
        verdict = evaluate(post.tags, rules)
        hidden = verdict is not None and verdict.decision != "warn"
        meta = _Meta(post, time.monotonic() + META_TTL, rules.version, hidden)
        cache.put(gid, meta)
    if meta.hidden:
        raise _Refusal(404, "not_found", "Gallery not found")
    return meta.post


def _page_ext(post: Post, n: int) -> tuple[str, str]:
    """(media_id, extension) of page n; 404 when n is out of range or the data is odd."""
    media_id = str(post.extra.get("media_id") or "")
    raw = post.extra.get("page_exts")
    exts = raw if isinstance(raw, list) else []
    if not media_id.isalnum() or not 1 <= n <= len(exts):
        raise _Refusal(404, "not_found", "Page not found")
    ext = str(exts[n - 1])
    if not ext.isalnum():
        raise _Refusal(404, "not_found", "Page not found")
    return media_id, ext


def shard_host(media_id: str, host_class: str) -> str:
    """Stable CDN mirror for one gallery (t1..t4 / i1..i4), like the site spreads images."""
    try:
        n = 1 + int(media_id) % SHARDS
    except ValueError:
        return f"{host_class}.nhentai.net"
    return f"{host_class}{n}.nhentai.net"


def image_urls(media_id: str, n: int, ext: str, thumb: bool) -> list[str]:
    """Candidate URLs: the shard first, the plain host as fallback."""
    cls = "t" if thumb else "i"
    name = f"{n}t.{ext}" if thumb else f"{n}.{ext}"
    hosts = [shard_host(media_id, cls), f"{cls}.nhentai.net"]
    urls = [f"https://{h}/galleries/{media_id}/{name}" for h in hosts]
    return [u for u in urls if CDN_HOST.match(u.split("/")[2])]


def _disconnected(request: Request):
    async def gone() -> bool:
        return await request.is_disconnected()

    return gone


def _open_upstream(src: NHentai, urls: list[str], timeout: float) -> httpx.Response:
    """GET the first working URL (streamed, no redirects, no Cookie). Raises _Refusal."""
    client: httpx.Client = src._client
    headers = src.page_headers()
    for i, url in enumerate(urls):
        try:
            resp = client.send(
                client.build_request("GET", url, headers=headers, timeout=timeout),
                stream=True,
                follow_redirects=False,
            )
        except httpx.TimeoutException:
            raise _Refusal(504, "upstream_error", "The site took too long") from None
        except httpx.HTTPError:
            raise _Refusal(502, "upstream_error", "The site is unreachable") from None
        if resp.status_code == 403 and i + 1 < len(urls):
            resp.close()  # a shard that blocks: try the plain host
            continue
        return resp
    raise _Refusal(502, "upstream_error", "The site blocked the request")


def _retry_after(resp: httpx.Response) -> float | None:
    try:
        return min(60.0, float(resp.headers["Retry-After"]))
    except (KeyError, ValueError):
        return None


def _check_response(resp: httpx.Response) -> None:
    status = resp.status_code
    if status in (404, 410):
        raise _Refusal(404, "not_found", "Page not found")
    if status == 429:
        raise _Refusal(
            429, "rate_limited", "The site asked to slow down", int(_retry_after(resp) or 5)
        )
    if status != 200:
        raise _Refusal(502, "upstream_error", f"The site returned {status}")
    media_type = resp.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type not in IMAGE_TYPES:
        raise _Refusal(502, "upstream_error", "The site sent no image")
    declared = resp.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_PAGE_BYTES:
        raise _Refusal(502, "upstream_error", "The image is too large")


class _Body:
    """Streams the upstream body under the size cap; frees response and slot exactly once."""

    def __init__(self, resp: httpx.Response, slot: Slot) -> None:
        self._resp, self._slot = resp, slot
        self._status = resp.status_code
        self._complete = False

    def __iter__(self) -> Iterator[bytes]:
        sent = 0
        try:
            for chunk in self._resp.iter_raw():
                sent += len(chunk)
                if sent > MAX_PAGE_BYTES:
                    return  # cut: the client sees a short body
                yield chunk
            self._complete = True
        finally:
            self.close()

    def close(self) -> None:
        self._resp.close()
        self._slot.finish(self._status if self._complete else None)


async def _fetch_image(request: Request, gid: str, n: int, thumb: bool, prio: Prio) -> Response:
    src = _nhentai(request)
    try:
        post = await run_in_threadpool(_load_meta, request, src, gid)
        media_id, ext = _page_ext(post, n)
        urls = image_urls(media_id, n, ext, thumb)
        if not urls:
            raise _Refusal(404, "not_found", "Page not found")
        limiter: Limiter = _scheduler(request).limiter("nhentai", "t" if thumb else "i")
        try:
            slot = await limiter.acquire(prio, _disconnected(request))
        except Busy:
            raise _Refusal(503, "busy", "Too many image requests", 2) from None
        except Gone:
            return Response(status_code=499)
        try:
            resp = await run_in_threadpool(
                _open_upstream, src, urls, THUMB_TIMEOUT if thumb else PAGE_TIMEOUT
            )
        except BaseException:
            slot.finish(None)
            raise
        try:
            _check_response(resp)
        except _Refusal:
            resp.close()
            slot.finish(resp.status_code, _retry_after(resp))
            raise
        except BaseException:
            resp.close()
            slot.finish(None)
            raise
    except _Refusal as r:
        logger.warning("nhentai gallery=%s page=%d thumb=%s err %d", gid, n, thumb, r.status)
        return _refusal_response(r)
    body = _Body(resp, slot)
    media_type = resp.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    headers = {"Cache-Control": PAGE_CACHE_CONTROL}
    if "content-length" in resp.headers:
        headers["Content-Length"] = resp.headers["content-length"]
    return StreamingResponse(
        iter(body), media_type=media_type, headers=headers, background=BackgroundTask(body.close)
    )


def _prio(request: Request, default: Prio) -> Prio:
    return parse_prio(request.query_params.get("prio"), default)


def build_book(post: Post, target: str) -> WebBook:
    raw = str(post.extra.get("title_english") or post.title or "")
    jp = post.extra.get("title_japanese")
    parsed = parse_title(raw, jp if isinstance(jp, str) else None)
    language = parsed.language
    if language is None:
        for name in post.tags.get("language", []):
            if name.lower() in LANGUAGES:
                language = name.capitalize()
                break
    exts = post.extra.get("page_exts")
    count = len(exts) if isinstance(exts, list) else 0
    gid = post.post_id
    item = WebItem(
        source="nhentai",
        post_id=gid,
        thumb_url=proxy_path("nhentai", gid, "thumb") if post.preview_url else "",
        preview_url=proxy_path("nhentai", gid, "preview") if post.preview_url else "",
        title=post.title,
        tags=[Tag(name=n, scope=k) for k, names in post.tags.items() for n in names],
        width=post.width,
        height=post.height,
        page_count=count or post.page_count,
        target=cast(Any, target),
    )
    base = f"/api/media/web/nhentai/{gid}/pages/{{n}}"
    return WebBook(
        title=post.title,
        title_main=parsed.title_main,
        title_sub=parsed.title_sub,
        artist=parsed.artist,
        circle=parsed.circle,
        event=parsed.event,
        language=language,
        translator=parsed.translator,
        tags=post.tags,
        page_count=count,
        page_url=base,
        page_thumb_url=base + "/thumb",
        item=item,
    )


@router.get("/{gid}/book", response_model=WebBook)
async def book(request: Request, gid: str) -> Response:
    """Gallery metadata for the book page; no media bytes."""
    src = _nhentai(request)
    try:
        post = await run_in_threadpool(_load_meta, request, src, gid)
    except _Refusal as r:
        return _refusal_response(r)
    data = build_book(post, src.target)
    return JSONResponse(data.model_dump(mode="json"), headers={"Cache-Control": "no-store"})


@router.get("/{gid}/pages/{n}/thumb")
async def page_thumb(request: Request, gid: str, n: int) -> Response:
    return await _fetch_image(request, gid, n, True, _prio(request, "focus"))


@router.get("/{gid}/pages/{n}")
async def page(request: Request, gid: str, n: int) -> Response:
    return await _fetch_image(request, gid, n, False, _prio(request, "focus"))
