"""Library route for owned web posts (D-28): serve a saved post from Stash, else the site."""

from __future__ import annotations

import logging
import time

from fastapi import Request, Response
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from app.api.media_stash_real import _forward_range, _stream
from app.bookserver.base import SORT_CREATED_DESC, BookServerError
from app.bookserver.factory import book_server_of
from app.db import connect
from app.jobs.store import JobStore
from app.models import SavedRef
from app.sources.base import Source
from app.targets import stash_library
from app.targets.komga import VERIFY_PAGE_SIZE, KomgaTarget
from app.targets.stash_client import StashError

logger = logging.getLogger("pearlie.media_owned")

FAILURE_TTL = 60.0
OPEN_TIMEOUT = 10.0
OFF_AFTER = 8  # this many posts failing inside one TTL: Stash is down, stop trying
_FAILURES_MAX = 2000
_PAGE_THUMB_WIDTH = 300


def is_owned(ref: SavedRef | None) -> bool:
    """A library copy exists (Stash image or video, Komga book); the library is not asked."""
    return ref is not None and ref.kind in ("image", "video", "book") and bool(ref.id)


def lookup(
    app, source: str, post_id: str, md5: str | None, post_kind: str
) -> tuple[str, str] | None:
    """(kind, Stash id) of the saved copy of this post, or None when it cannot be routed."""
    refs = JobStore(app.state.settings.db_path).saved_refs(
        source, [post_id], {post_id: md5} if md5 else None
    )
    ref = refs.get(post_id)
    if ref is not None and ref.kind == "book":
        if getattr(app.state, "komga", None) is None:
            return None
        book_id = ref.id or _backfill_book(app, source, post_id)
        return ("book", book_id) if book_id and book_server_of(app).valid_id(book_id) else None
    if getattr(app.state, "stash", None) is None:
        return None
    if ref is None or ref.kind not in ("image", "video") or ref.kind != post_kind:
        return None
    if not stash_library.valid_id(ref.id):
        return None
    return ref.kind, ref.id


def _backfill_book(app, source: str, post_id: str) -> str | None:
    """Find the Komga book of an old index row with one title search, then keep its id."""
    key = (source, post_id)
    if _skip(app, key):
        return None
    try:
        page = book_server_of(app).list_books(1, VERIFY_PAGE_SIZE, post_id, SORT_CREATED_DESC)
        books = page.items
        match = next((b for b in books if KomgaTarget._book_matches(b, post_id)), None)
    except Exception:  # Komga down or odd answer: the site path stays
        match = None
    book_id = match.id if match else ""
    if not book_id:
        _note_failure(app, key)
        return None
    conn = connect(app.state.settings.db_path)
    try:
        conn.execute(
            "UPDATE saved_items SET library_id = ? WHERE target = 'komga' "
            "AND source = ? AND post_id = ? AND library_id IS NULL",
            (book_id, source, post_id),
        )
        conn.commit()
    finally:
        conn.close()
    return book_id


def _state(app) -> dict:
    state = getattr(app.state, "owned_failures", None)
    if state is None:
        state = app.state.owned_failures = {"posts": {}, "off_until": 0.0}
    return state


def _skip(app, key: tuple[str, str]) -> bool:
    state = _state(app)
    now = time.monotonic()
    if state["off_until"] > now:
        return True
    until = state["posts"].get(key)
    if until is None:
        return False
    if until < now:
        state["posts"].pop(key, None)
        return False
    return True


def _note_failure(app, key: tuple[str, str]) -> None:
    state = _state(app)
    posts: dict = state["posts"]
    now = time.monotonic()
    if len(posts) > _FAILURES_MAX:
        for k in [k for k, until in posts.items() if until < now]:
            posts.pop(k, None)
    posts[key] = now + FAILURE_TTL
    if sum(1 for until in posts.values() if until >= now) >= OFF_AFTER:
        state["off_until"] = now + FAILURE_TTL


def _path(app, kind: str, entity: str, media: str) -> str:
    if kind == "image":
        return f"/image/{entity}/image"
    if media == "preview":
        try:
            path = app.state.stash.scene_preview_path(entity)
        except StashError:
            path = None
        return path or f"/scene/{entity}/preview"
    return f"/scene/{entity}/stream"


def try_library(request: Request, src: Source, post_id: str, media: str) -> Response | None:
    """The Stash response for an owned post, or None to use the site (sync, run in a thread)."""
    from app.api.media_web_real import _authorize, media_kind  # late: media_web_real imports us

    post = _authorize(request, src, post_id)  # its ApiError is the site path's own error
    app = request.app
    found = lookup(app, src.id, post_id, post.md5, media_kind(post))
    if found is None:
        return None
    key = (src.id, post_id)
    if _skip(app, key):
        return None
    kind, entity = found
    if kind == "book":
        return _open_book(app, key, src.id, post_id, entity, 1, False)
    reason = "stash_error"
    try:
        path = _path(app, kind, entity, media)
        upstream = app.state.stash.open_media(
            path, headers=_forward_range(request), timeout=OPEN_TIMEOUT
        )
    except StashError as err:
        reason = err.code
    except Exception:  # a broken library must never break the site path
        reason = "error"
    else:
        ctype = upstream.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if ctype.startswith(("image/", "video/")):
            video = kind == "video" and media == "full"
            return _stream(upstream, "private, max-age=0" if video else "private, max-age=3600")
        upstream.close()
        reason = "bad_type"
    _note_failure(app, key)
    logger.info("OWNED route=site reason=%s source=%s post=%s", reason, src.id, post_id)
    return None


def _open_book(
    app,
    key: tuple[str, str],
    source: str,
    post_id: str,
    book_id: str,
    n: int,
    thumb: bool,
) -> Response | None:
    """Page *n* of the saved Komga book, or None to use the site."""
    reason = "komga_error"
    try:
        server = book_server_of(app)
        upstream = (
            server.open_page_thumb(book_id, n, _PAGE_THUMB_WIDTH)
            if thumb
            else server.open_page(book_id, n)
        )
    except BookServerError as err:
        reason = err.code
    except Exception:  # a broken library must never break the site path
        reason = "error"
    else:
        ctype = upstream.content_type.split(";", 1)[0].strip().lower()
        if ctype.startswith("image/"):
            headers = {"Cache-Control": "private, max-age=3600"}
            if upstream.content_length is not None:
                headers["Content-Length"] = upstream.content_length
            return StreamingResponse(
                upstream.iter_bytes(),
                media_type=upstream.content_type,
                headers=headers,
                background=BackgroundTask(upstream.close),
            )
        upstream.close()
        reason = "bad_type"
    _note_failure(app, key)
    logger.info("OWNED route=site reason=%s source=%s post=%s", reason, source, post_id)
    return None


def try_book_page(request: Request, post_id: str, n: int, thumb: bool) -> Response | None:
    """A reader page of an owned nhentai book from Komga, or None (sync, run in a thread)."""
    app = request.app
    if n < 1 or getattr(app.state, "komga", None) is None:
        return None
    key = ("nhentai", post_id)
    if _skip(app, key):
        return None
    refs = JobStore(app.state.settings.db_path).saved_refs("nhentai", [post_id])
    ref = refs.get(post_id)
    if ref is None or ref.kind != "book":
        return None
    book_id = ref.id or _backfill_book(app, "nhentai", post_id)
    if not book_id or not book_server_of(app).valid_id(book_id):
        return None
    return _open_book(app, key, "nhentai", post_id, book_id, n, thumb)
