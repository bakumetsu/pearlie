"""Discover merged row: the first page of every rail site, mixed in turns."""

from __future__ import annotations

import logging
import time
import typing
from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import dataclass

from fastapi import APIRouter, Request

from app.api.errors import ApiError
from app.api.media_owned import is_owned
from app.api.media_web_real import media_kind, pick_url, proxy_path, remember, tile_url
from app.api.options import read_option
from app.api.search_real import _SAVE_TARGETS, _TITLES, _cache_of, site_items
from app.discover_merge import PER_SITE, dedupe, interleave, rail_sites
from app.filters.rules import evaluate, load_rules
from app.filters.safe_mode import is_hidden_in_safe_mode, resolve_safe
from app.gif_grid import grid_gif_ok
from app.jobs.store import JobStore
from app.models import Blur, MergedRow, MergedSite, MergedState, Tag, Target, WebItem, WebSource
from app.sources.base import Post, SearchPage, Source, SourceError
from app.sources.nhentai import reject_terms
from app.sources.throttle import DEFAULT_PACE

router = APIRouter(prefix="/api")
logger = logging.getLogger("pearlie.discover_merge")

MERGE_WAIT_S = 4.0


@dataclass
class _Outcome:
    """What one site call gave: a page, or the Problem code and message of its error."""

    page: SearchPage | None = None
    code: str = ""
    message: str = ""
    elapsed_ms: int = 0


def _rail(request: Request) -> list[str]:
    """Rail sites in rail order, read from the options (the client never picks them)."""
    order = [s for s in (read_option(request, "options.global.site_order") or "").split(",") if s]
    order = list(dict.fromkeys(s for s in order if s in DEFAULT_PACE))
    order += [s for s in DEFAULT_PACE if s not in order]
    hidden = (read_option(request, "options.global.hidden_sites") or "").split(",")
    return rail_sites(order, hidden, request.app.state.sources)


def _call(request_cache, sid: str, src: Source, tags: list[str]) -> _Outcome:
    """One first-page call through the shared cache; a running call is joined."""
    t0 = time.monotonic()
    try:
        page = site_items(request_cache, sid, src, tags, 1, None, None, [])
    except SourceError as e:
        return _Outcome(code=e.code, message=e.message, elapsed_ms=_ms(t0))
    except Exception as e:  # a site bug must not break the row; the log keeps the type only
        logger.warning(
            "site=%s state=error elapsed_ms=%d reason=%s", sid, _ms(t0), type(e).__name__
        )
        return _Outcome(code="error", message="Site call failed", elapsed_ms=_ms(t0))
    return _Outcome(page=page, elapsed_ms=_ms(t0))


def _ms(t0: float) -> int:
    return int((time.monotonic() - t0) * 1000)


def _state_of(out: _Outcome) -> MergedState:
    if out.page is None:
        return "rate_limited" if out.code == "rate_limited" else "error"
    return "ok" if out.page.posts else "empty"


def _log_late(sid: str, fut: Future[_Outcome]) -> None:
    """Called when a site that missed the wait ends: one line, reason code only."""
    try:
        out = fut.result()
    except Exception:
        logger.warning("site=%s state=error elapsed_ms=0 reason=error", sid)
        return
    if out.page is None:
        logger.warning(
            "site=%s state=%s elapsed_ms=%d reason=%s",
            sid,
            _state_of(out),
            out.elapsed_ms,
            out.code,
        )
    else:
        logger.info("site=%s state=late elapsed_ms=%d reason=arrived", sid, out.elapsed_ms)


def _web_item(post: Post, blur: Blur | None, src: Source) -> WebItem:
    target = typing.cast(str, getattr(src, "target", "stash"))
    return WebItem(
        source=typing.cast(WebSource, post.source),
        post_id=post.post_id,
        thumb_url=proxy_path(post.source, post.post_id, "thumb") if tile_url(post) else "",
        preview_url=(
            proxy_path(post.source, post.post_id, "preview") if pick_url(post, "preview") else ""
        ),
        media_kind=media_kind(post),
        gif_url=(
            proxy_path(post.source, post.post_id, "preview")
            if grid_gif_ok(pick_url(post, "preview"), post.file_size)
            else None
        ),
        title=post.title,
        tags=[Tag(name=n, scope=kind) for kind, names in post.tags.items() for n in names],
        width=post.width,
        height=post.height,
        page_count=post.page_count,
        target=typing.cast(Target, target),
        saveable=target in _SAVE_TARGETS,
        blur=blur,
    )


@router.get("/discover/merged")
def discover_merged(
    request: Request,
    have: str = "",
    safe: bool | None = None,
) -> MergedRow:
    """The merged first row. A site that is slow after the wait is pending, not waited for."""
    wait_s = MERGE_WAIT_S
    rail = _rail(request)
    if len(rail) < 2:
        raise ApiError(409, "not_merged", "Fewer than two sites in the rail")
    have_ids = {s.strip() for s in have.split(",") if s.strip()}
    safe_on, allow_blurred = resolve_safe(request, safe)
    rules = load_rules(request.app.state.settings.db_path)
    sources: dict[str, Source] = request.app.state.sources
    cache = _cache_of(request)

    pool = ThreadPoolExecutor(max_workers=len(rail), thread_name_prefix="discover-merged")
    futures: dict[str, Future[_Outcome]] = {}
    for sid in rail:
        # same tags as a split row in multi mode, so both share one cache entry
        tags = reject_terms(rules.reject) if sid == "nhentai" else []
        futures[sid] = pool.submit(_call, cache, sid, sources[sid], tags)
    wait(futures.values(), timeout=wait_s)
    pool.shutdown(wait=False)

    outcomes: dict[str, _Outcome] = {}
    states: dict[str, MergedState] = {}
    for sid, fut in futures.items():
        if fut.done():
            outcomes[sid] = fut.result()
            states[sid] = _state_of(outcomes[sid])
        else:
            states[sid] = "pending"
            logger.warning(
                "site=%s state=pending elapsed_ms=%d reason=wait_expired",
                sid,
                int(wait_s * 1000),
            )
            fut.add_done_callback(lambda f, s=sid: _log_late(s, f))
    for sid, out in outcomes.items():
        if states[sid] in ("error", "rate_limited"):
            logger.warning(
                "site=%s state=%s elapsed_ms=%d reason=%s",
                sid,
                states[sid],
                out.elapsed_ms,
                out.code,
            )

    hidden = 0
    blurs: dict[tuple[str, str], Blur | None] = {}
    visible: dict[str, list[Post]] = {}
    for sid, out in outcomes.items():
        if out.page is None:
            continue
        posts: list[Post] = []
        for post in out.page.posts:
            verdict = evaluate(post.tags, rules)
            if verdict is not None and verdict.decision != "warn":
                hidden += 1
                continue
            blur = Blur(tag=verdict.tag) if verdict else None
            if is_hidden_in_safe_mode(blur, safe_on, allow_blurred):
                hidden += 1
                continue
            blurs[(sid, post.post_id)] = blur
            posts.append(post)
        visible[sid] = posts

    row = dedupe(interleave(visible, rail, have_ids, per_site=PER_SITE))
    items = [_web_item(p, blurs[(p.source, p.post_id)], sources[p.source]) for p in row]
    store = JobStore(request.app.state.settings.db_path)
    for sid in visible:
        mine = [it for it in items if it.source == sid]
        posts_of = [p for p in row if p.source == sid]
        saved = store.saved_refs(
            sid, [p.post_id for p in posts_of], {p.post_id: p.md5 for p in posts_of if p.md5}
        )
        for it in mine:
            it.saved = saved.get(it.post_id)
            it.owned = is_owned(it.saved)
    remember(request.app, row, rules.version)

    sites = [
        MergedSite(
            id=typing.cast(WebSource, sid),
            title=_TITLES[sid],
            state=states[sid],
            count=sum(1 for p in row if p.source == sid),
            message=(outcomes[sid].message or None) if sid in outcomes else None,
        )
        for sid in rail
    ]
    return MergedRow(
        items=items,
        sites=sites,
        hidden=hidden,
        pending=any(s.state == "pending" for s in sites),
    )
