"""Real search router backed by live sources."""

from __future__ import annotations

import typing

from fastapi import APIRouter, Query, Request

from app.api.errors import ApiError
from app.models import (
    LibraryItem,
    Problem,
    SearchResponse,
    Section,
    SectionId,
    Tag,
    WebItem,
    WebSource,
)
from app.paging import PAGE_SIZE_CAPS, clamp_page_size
from app.sources.base import Source, SourceError

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


@router.get("/search")
def search(
    request: Request,
    q: str = "",
    sources: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(60, ge=1, le=200),
) -> SearchResponse:
    """Search across configured sources and library sections."""
    raw = sources.split(",") if sources else _DEFAULT
    ids = [s.strip() for s in raw if s.strip()]
    for sid in ids:
        if sid not in _VALID:
            raise ApiError(422, "invalid", f"Unknown source {sid}", field="sources")
    source_map: dict[str, Source] = request.app.state.sources
    multi = len(ids) > 1
    sections: list[Section] = []
    for sid in ids:
        title = _TITLES[sid]
        cast_sid = typing.cast(SectionId, sid)
        if sid in source_map:
            src = source_map[sid]
            tags = q.split()
            pg = page if not multi else 1
            try:
                page_result = src.search(tags, pg, page_size if not multi else None)
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
                items: list[LibraryItem | WebItem] = [
                    WebItem(
                        source=typing.cast(WebSource, post.source),
                        post_id=post.post_id,
                        thumb_url=post.preview_url or "",
                        preview_url=post.file_url or post.preview_url or "",
                        title=None,
                        tags=[
                            Tag(name=n, scope=kind)
                            for kind, names in post.tags.items()
                            for n in names
                        ],
                        width=post.width,
                        height=post.height,
                        target="stash",
                    )
                    for post in page_result.posts
                ]
                if multi:
                    items = items[:18]
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
                        hidden=0,
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
                        message=f"{title} is not connected yet",
                    ),
                )
            )
    return SearchResponse(query=q, sections=sections)
