"""Real search router backed by live sources."""

from __future__ import annotations

import typing

from fastapi import APIRouter, Query, Request

from app.api.errors import ApiError
from app.api.library_komga_real import fetch_komga_page
from app.api.library_stash_real import fetch_stash_page
from app.api.search_filters import parse_order, parse_rating, unsupported_notice
from app.filters.rules import evaluate, load_rules
from app.komga import Komga, KomgaError, book_item
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
from app.paging import PAGE_SIZE_CAPS, clamp_page_size, pages_for
from app.sources.base import Post, Source, SourceError
from app.sources.filters import NOTICE_CODE
from app.targets.stash_client import StashClient, StashError
from app.targets.stash_library import image_item, map_items, stash_sort, video_item

router = APIRouter(prefix="/api")

_DEFAULT = ["stash_images", "stash_videos", "komga_books", "danbooru", "gelbooru", "nhentai"]
_VALID = {*_DEFAULT, "rule34"}
_TITLES = {
    "stash_images": "Stash images",
    "stash_videos": "Stash videos",
    "komga_books": "Komga books",
    "danbooru": "Danbooru",
    "gelbooru": "Gelbooru",
    "rule34": "Rule34",
    "nhentai": "nhentai",
}


_LIBRARY = {"stash_images", "stash_videos", "komga_books"}

# Targets a save job can reach today; T-131b adds "komga".
_SAVE_TARGETS = {"stash", "komga"}

VIDEO_EXTS = (".mp4", ".webm", ".mov", ".m4v", ".mkv")


def _web_thumb(post: Post) -> str:
    """Pick the tile image: the ~850 px sample, else the preview (video samples fall back)."""
    sample = post.sample_url
    if sample and not sample.lower().split("?", 1)[0].endswith(VIDEO_EXTS):
        return sample
    return post.preview_url or ""


def _library_section(request: Request, sid: str, q: str, page: int, page_size: int, multi: bool):
    """Section for a Stash or Komga library source, or None when it is not configured."""
    state = request.app.state
    client = state.komga if sid == "komga_books" else state.stash
    if client is None:
        return None
    title = _TITLES[sid]
    cast_sid = typing.cast(SectionId, sid)
    pg = 1 if multi else page
    size = 18 if multi else clamp_page_size(sid, page_size)
    try:
        if sid == "komga_books":
            komga: Komga = client
            # Pearlie pages are 1-based; fetch_komga_page converts to Komga's 0-based.
            reply, pages, served = fetch_komga_page(
                lambda p0, n: komga.list_books(page=p0, size=n, sort="createdDate,desc", q=q),
                pg,
                size,
            )
            items = [book_item(r) for r in reply["content"]]
            total = reply["totalElements"]
            next_page = served + 1 if not reply["last"] else None
        else:
            stash: StashClient = client
            field, direction = stash_sort("newest", None)
            if sid == "stash_images":
                dtos, total, _agg, served = fetch_stash_page(
                    lambda p, n: stash.list_images(p, n, q, field, direction), pg, size
                )
                items, _bad = map_items(dtos, image_item)
            else:
                dtos, total, _agg, served = fetch_stash_page(
                    lambda p, n: stash.list_scenes(p, n, q, field, direction), pg, size
                )
                items, _bad = map_items(dtos, video_item)
            pages = pages_for(total, size)
            next_page = served + 1 if served * size < total else None
    except (StashError, KomgaError) as e:
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
) -> SearchResponse:
    """Search across configured sources and library sections."""
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
    for sid in ids:
        title = _TITLES[sid]
        cast_sid = typing.cast(SectionId, sid)
        lib = _library_section(request, sid, q, page, page_size, multi) if sid in _LIBRARY else None
        if lib is not None:
            sections.append(lib)
        elif sid in source_map:
            src = source_map[sid]
            tags = q.split()
            pg = page if not multi else 1
            try:
                page_result = src.search(
                    tags, pg, page_size if not multi else None, order_v, rating_v
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
                for post in page_result.posts:
                    verdict = evaluate(post.tags, rules)
                    if verdict is not None and verdict.decision != "warn":
                        hidden += 1
                        continue
                    items.append(
                        WebItem(
                            source=typing.cast(WebSource, post.source),
                            post_id=post.post_id,
                            thumb_url=_web_thumb(post),
                            preview_url=post.file_url or post.preview_url or "",
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
                            blur=Blur(tag=verdict.tag) if verdict else None,
                        )
                    )
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
