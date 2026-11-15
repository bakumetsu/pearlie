"""Library route for owned web posts (D-28): serve a saved post from Stash, else the site."""

from __future__ import annotations

import logging
import time

from fastapi import Request, Response

from app.api.errors import ApiError
from app.api.media_stash_real import _forward_range, _stream
from app.jobs.store import JobStore
from app.models import SavedRef
from app.sources.base import Source
from app.targets import stash_library
from app.targets.stash_client import StashError

logger = logging.getLogger("pearlie.media_owned")

FAILURE_TTL = 60.0
OPEN_TIMEOUT = 10.0
OFF_AFTER = 8  # this many posts failing inside one TTL: Stash is down, stop trying
_FAILURES_MAX = 2000


def is_owned(ref: SavedRef | None) -> bool:
    """A Stash copy exists (a Komga row has an empty id); Stash itself is not asked."""
    return ref is not None and ref.kind in ("image", "video") and bool(ref.id)


def lookup(app, source: str, post_id: str, md5: str | None, post_kind: str) -> tuple[str, str] | None:
    """(kind, Stash id) of the saved copy of this post, or None when it cannot be routed."""
    if getattr(app.state, "stash", None) is None:
        return None
    refs = JobStore(app.state.settings.db_path).saved_refs(
        source, [post_id], {post_id: md5} if md5 else None
    )
    ref = refs.get(post_id)
    if ref is None or ref.kind not in ("image", "video") or ref.kind != post_kind:
        return None
    if not stash_library.valid_id(ref.id):
        return None
    return ref.kind, ref.id


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

    try:
        post = _authorize(request, src, post_id)
    except ApiError:
        return None  # the site path raises the real error
    app = request.app
    found = lookup(app, src.id, post_id, post.md5, media_kind(post))
    if found is None:
        return None
    key = (src.id, post_id)
    if _skip(app, key):
        return None
    kind, entity = found
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
