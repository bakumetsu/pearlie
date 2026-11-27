"""Real search router backed by live sources."""

from __future__ import annotations

import typing

from fastapi import APIRouter, Query, Request

from app.api.errors import ApiError
from app.api.library_stash_real import fetch_stash_page
from app.api.library_stump_real import fetch_book_page
from app.api.media_owned import is_owned
from app.api.media_web_real import media_kind, pick_url, proxy_path, remember, tile_url
from app.api.search_filters import (
    parse_order,
    parse_rating,
    skipped_section,
    title_notice,
    unsupported_notice,
)
from app.bookserver.base import SORT_CREATED_DESC, BookServerError
from app.bookserver.factory import book_server_of
from app.bookserver.map import book_item
from app.filters.rules import evaluate, load_rules
from app.filters.safe_mode import is_hidden_in_safe_mode, resolve_safe
from app.gif_grid import grid_gif_ok
from app.jobs.store import JobStore
from app.models import (
    Blur,
    LibraryItem,
    Problem,
    SearchResponse,
    Section,
    SectionId,
    Tag,
    Target,
    WebItem,
    WebSource,
)
from app.paging import PAGE_SIZE_CAPS, clamp_page, clamp_page_size, pages_for
from app.search_cache import SearchCache
from app.sources.base import Post, SearchPage, Source, SourceError
from app.sources.filters import NOTICE_CODE
from app.sources.nhentai import reject_terms
from app.sources.query_terms import split_terms, title_terms
from app.targets.stash_client import StashClient, StashError
from app.targets.stash_library import (
    image_item,
    log_gif_rejects,
    map_items,
    stash_sort,
    video_item,
)

router = APIRouter(prefix="/api")

_DEFAULT = ["stash_images", "stash_videos", "stump_books", "danbooru", "gelbooru", "nhentai"]
_VALID = {*_DEFAULT, "rule34"}
_TITLES = {
    "stash_images": "Stash images",
    "stash_videos": "Stash videos",
    "stump_books": "Stump books",
    "danbooru": "Danbooru",
    "gelbooru": "Gelbooru",
    "rule34": "Rule34",
    "nhentai": "nhentai",
}


_LIBRARY = {"stash_images", "stash_videos", "stump_books"}

# Targets a save job can reach today; T-131b adds "stump".
_SAVE_TARGETS = {"stash", "stump"}


def _cache_of(request: Request) -> SearchCache:
    """The app's site-search cache (library sources never use it)."""
    state = request.app.state
    cache = getattr(state, "search_cache", None)
    if cache is None:
        cache = state.search_cache = SearchCache()
    return cache


def site_items(
    cache: SearchCache,
    sid: str,
    src: Source,
    tags: list[str],
    pg: int,
    size: int | None,
    order: typing.Any,
    rating: typing.Any,
) -> SearchPage:
    """One site page through the cache; a call that is already running is joined, not repeated."""
    # order picks which words a capped source sends, so sort only when nothing is cut
    cap = getattr(src, "tag_limit", None)
    same_query = cap is None or len(tags) <= cap
    ckey = (
        sid,
        tuple(sorted(tags) if same_query else tags),
        pg,
        size,
        order,
        tuple(rating),
    )
    return cache.get_or_join(ckey, lambda: src.search(tags, pg, size, order, rating))


def _web_thumb(post: Post) -> str:
    """Pick the tile image: the ~850 px sample, else the preview (video samples fall back)."""
    return tile_url(post) or ""


def _library_section(
    request: Request,
    sid: str,
    q: str,
    page: int,
    page_size: int,
    multi: bool,
    tags: list[str] | None = None,
):
    """Section for a Stash or Stump library source, or None when it is not configured.

    *tags* (Stump only): tag terms read from the cached tag walk (AND), paged here.
    """
    state = request.app.state
    client = state.stump if sid == "stump_books" else state.stash
    if client is None:
        return None
    title = _TITLES[sid]
    cast_sid = typing.cast(SectionId, sid)
    pg = 1 if multi else page
    size = 18 if multi else clamp_page_size(sid, page_size)
    try:
        if sid == "stump_books":
            server = book_server_of(request.app)
            trash = getattr(state, "trash", None)
            owned = trash.stump_owned_ids() if trash is not None else set()
            if tags:
                rows = [
                    r for r in server.tagged_books(q, tags) if not r.deleted and r.id not in owned
                ]
                total = len(rows)
                pages = pages_for(total, size)
                served = clamp_page(pg, pages)
                items = [book_item(r) for r in rows[(served - 1) * size : served * size]]
                next_page = served + 1 if served < pages else None
            else:
                reply, pages, served = fetch_book_page(
                    lambda p, n: server.list_books(p, n, q, SORT_CREATED_DESC), pg, size
                )
                items = [book_item(r) for r in reply.items if not r.deleted and r.id not in owned]
                total = reply.total_items
                next_page = served + 1 if not reply.last else None
        else:
            stash: StashClient = client
            field, direction = stash_sort("newest", None)
            if sid == "stash_images":
                dtos, total, _agg, served = fetch_stash_page(
                    lambda p, n: stash.list_images(p, n, q, field, direction), pg, size
                )
                items, _bad = map_items(dtos, image_item)
                log_gif_rejects(dtos)
            else:
                dtos, total, _agg, served = fetch_stash_page(
                    lambda p, n: stash.list_scenes(p, n, q, field, direction), pg, size
                )
                items, _bad = map_items(dtos, video_item)
            pages = pages_for(total, size)
            next_page = served + 1 if served * size < total else None
    except (StashError, BookServerError) as e:
        return Section(
            id=cast_sid,
            title=title,
            items=[],
            total=None,
            next_page=None,
            hidden=0,
            error=Problem(code=e.code, message=e.message),
        )
    return Section(
        id=cast_sid,
        title=title,
        items=typing.cast(list[LibraryItem | WebItem], items),
        total=total,
        pages=pages,
        next_page=next_page,
        page_size=None if multi else size,
        hidden=0,
    )


@router.get("/search")
def search(
    request: Request,
    q: str = "",
    sources: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(60, ge=1, le=200),
    order: str = "",
    rating: str = "",
    safe: bool | None = None,
) -> SearchResponse:
    """Search across configured sources and library sections."""
    safe_on, allow_blurred = resolve_safe(request, safe)
    order_v = parse_order(order)
    rating_v = parse_rating(rating)
    raw = sources.split(",") if sources else _DEFAULT
    ids = [s.strip() for s in raw if s.strip()]
    rules = load_rules(request.app.state.settings.db_path)
    for sid in ids:
        if sid not in _VALID:
            raise ApiError(422, "invalid", f"Unknown source {sid}", field="sources")
    source_map: dict[str, Source] = request.app.state.sources
    multi = len(ids) > 1
    sections: list[Section] = []
    titles, others = title_terms(split_terms(q))
    for sid in ids:
        title = _TITLES[sid]
        cast_sid = typing.cast(SectionId, sid)
        skip = title_notice(sid, titles)
        if skip:
            sections.append(skipped_section(cast_sid, title, skip))
            continue
        lib_q, lib_tags = q, None
        if sid == "stump_books" and (titles or others):
            # Stump search is full text: it gets only the title text. Tag terms read the walk.
            lib_q = " ".join(t.value for t in titles)
            lib_tags = others or None
        lib = (
            _library_section(request, sid, lib_q, page, page_size, multi, lib_tags)
            if sid in _LIBRARY
            else None
        )
        if lib is not None:
            sections.append(lib)
        elif sid in source_map:
            src = source_map[sid]
            tags = [*others, *(t.token for t in titles)]
            if sid == "nhentai":
                tags += [t for t in reject_terms(rules.reject) if t not in tags]
            pg = page if not multi else 1
            size_v = page_size if not multi else None
            try:
                page_result = site_items(
                    _cache_of(request), sid, src, tags, pg, size_v, order_v, rating_v
                )
            except SourceError as e:
                sections.append(
                    Section(
                        id=cast_sid,
                        title=title,
                        items=[],
                        total=None,
                        next_page=None,
                        hidden=0,
                        error=Problem(code=e.code, message=e.message),
                    )
                )
            else:
                items: list[LibraryItem | WebItem] = []
                hidden = 0
                visible: list[Post] = []
                for post in page_result.posts:
                    verdict = evaluate(post.tags, rules)
                    if verdict is not None and verdict.decision != "warn":
                        hidden += 1
                        continue
                    blur = Blur(tag=verdict.tag) if verdict else None
                    if is_hidden_in_safe_mode(blur, safe_on, allow_blurred):
                        hidden += 1
                        continue
                    visible.append(post)
                    items.append(
                        WebItem(
                            source=typing.cast(WebSource, post.source),
                            post_id=post.post_id,
                            thumb_url=(
                                proxy_path(post.source, post.post_id, "thumb")
                                if _web_thumb(post)
                                else ""
                            ),
                            preview_url=(
                                proxy_path(post.source, post.post_id, "preview")
                                if pick_url(post, "preview")
                                else ""
                            ),
                            media_kind=media_kind(post),
                            gif_url=(
                                proxy_path(post.source, post.post_id, "preview")
                                if grid_gif_ok(pick_url(post, "preview"), post.file_size)
                                else None
                            ),
                            title=post.title,
                            tags=[
                                Tag(name=n, scope=kind)
                                for kind, names in post.tags.items()
                                for n in names
                            ],
                            width=post.width,
                            height=post.height,
                            page_count=post.page_count,
                            target=typing.cast(Target, getattr(src, "target", "stash")),
                            saveable=getattr(src, "target", "stash") in _SAVE_TARGETS,
                            blur=blur,
                        )
                    )
                saved = JobStore(request.app.state.settings.db_path).saved_refs(
                    sid,
                    [p.post_id for p in visible],
                    {p.post_id: p.md5 for p in visible if p.md5},
                )
                for it in items:
                    if isinstance(it, WebItem):
                        it.saved = saved.get(it.post_id)
                        it.owned = is_owned(it.saved)
                remember(request.app, visible, rules.version)
                if multi:
                    items = items[:18]
                notes = [*page_result.notices]
                unsupported = unsupported_notice(sid, order_v, rating_v)
                if unsupported:
                    notes.append(unsupported)
                sections.append(
                    Section(
                        id=cast_sid,
                        title=title,
                        items=items,
                        total=page_result.total,
                        pages=page_result.pages,
                        next_page=page_result.next_page,
                        page_size=clamp_page_size(sid, page_size)
                        if not multi and sid in PAGE_SIZE_CAPS
                        else None,
                        hidden=hidden,
                        error=(
                            Problem(
                                code="filter_dropped",
                                message=(
                                    f"Ignored: {', '.join(page_result.dropped)} "
                                    "(Danbooru allows 2 tags)"
                                ),
                            )
                            if page_result.dropped
                            else None
                        ),
                        notice=(
                            Problem(code=NOTICE_CODE, message=". ".join(notes)) if notes else None
                        ),
                    )
                )
        else:
            sections.append(
                Section(
                    id=cast_sid,
                    title=title,
                    items=[],
                    total=None,
                    hidden=0,
                    error=Problem(
                        code="not_configured",
                        message=f"{title} search is not available yet",
                    ),
                )
            )
    return SearchResponse(query=q, sections=sections)
