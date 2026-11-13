from typing import cast

from fastapi import APIRouter, Depends, Query

from app.api.errors import ApiError
from app.api.search_filters import parse_order, parse_rating, unsupported_notice
from app.fixtures.scenarios import active, slow_dependency
from app.fixtures.store import store
from app.models import LibraryItem, Problem, SearchResponse, Section, SectionId, WebItem
from app.paging import clamp_page, clamp_page_size, pages_for
from app.sources.filters import (
    NOTICE_CODE,
    danbooru_plan,
    dapi_filter_tags,
    supported_ratings,
)

router = APIRouter(prefix="/api", dependencies=[Depends(slow_dependency)])

_DEFAULT = "stash_images,stash_videos,komga_books,danbooru,gelbooru,nhentai"
_VALID = {
    "stash_images",
    "stash_videos",
    "komga_books",
    "danbooru",
    "gelbooru",
    "nhentai",
    "rule34",
}
_LIB = {
    "stash_images": ("images", "Stash images"),
    "stash_videos": ("videos", "Stash videos"),
    "komga_books": ("books", "Komga books"),
}
_WEB = {"danbooru": "Danbooru", "gelbooru": "Gelbooru", "rule34": "Rule34", "nhentai": "nhentai"}


def _filtered(source: str, q: str, order: str | None, rating: list[str]) -> tuple[list, list[str]]:
    """Return web items matching the query and filters, plus the notices for the section."""
    words = q.split()
    notes: list[str] = []
    if source == "danbooru":
        _server, _local, notes = danbooru_plan(words, order, rating, 2)
        if order and len(words) >= 2:
            order = None
    elif source in ("gelbooru", "rule34"):
        _tags, notes = dapi_filter_tags(source, order, rating)
    unsupported = unsupported_notice(source, order, rating)
    if unsupported:
        notes.append(unsupported)
    allowed = supported_ratings(source)
    wanted = [r for r in rating if r in allowed]
    items = [
        it
        for it in store.web_items(source, order if allowed else None, wanted)
        if store.matches([t.name for t in it.tags], it.tags, it.title or "", q)
    ]
    return items, notes


@router.get("/search")
def search(
    q: str = "",
    sources: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(60, ge=1, le=200),
    order: str = "",
    rating: str = "",
) -> SearchResponse:
    """Search across library and web sources."""
    order_v = parse_order(order)
    rating_v = parse_rating(rating)
    ids = (
        _DEFAULT.split(",") if not sources else [s.strip() for s in sources.split(",") if s.strip()]
    )
    for sid in ids:
        if sid not in _VALID:
            raise ApiError(422, "invalid", f"Unknown source {sid}", field="sources")

    empty, errs = active("empty"), active("errors")
    single = len(ids) == 1
    sections: list[Section] = []

    for sid in ids:
        if sid in _LIB:
            kinds, title = _LIB[sid]
            hidden = 0 if empty else store.hidden_count(kinds)
            if empty:
                sections.append(
                    Section(
                        id=cast(SectionId, sid),
                        title=title,
                        items=[],
                        total=0,
                        next_page=None,
                        hidden=hidden,
                    )
                )
            else:
                if single:
                    sz = clamp_page_size(sid, page_size)
                    pg = page
                else:
                    pg, sz = 1, 12
                res = store.list_library(kinds, pg, sz, q, "newest", None)
                if res is None:
                    raise ApiError(422, "invalid", "Bad source", field="sources")
                items: list[LibraryItem | WebItem] = [*res.items]
                # Komga rows show the library count before rules;
                # the hidden footer keeps the difference.
                total = res.total + hidden if sid == "komga_books" and not q else res.total
                sections.append(
                    Section(
                        id=cast(SectionId, sid),
                        title=title,
                        items=items,
                        total=total,
                        pages=pages_for(res.total, sz),
                        next_page=res.next_page,
                        page_size=sz if single else None,
                        hidden=hidden,
                    )
                )
        else:
            title = _WEB[sid]
            hidden = 0 if empty else store.web_hidden(sid)
            if empty:
                sections.append(
                    Section(
                        id=cast(SectionId, sid),
                        title=title,
                        items=[],
                        total=0,
                        next_page=None,
                        hidden=hidden,
                    )
                )
            elif sid == "danbooru" and errs:
                sections.append(
                    Section(
                        id=cast(SectionId, sid),
                        title=title,
                        items=[],
                        total=None,
                        next_page=None,
                        hidden=hidden,
                        error=Problem(code="upstream_error", message="Danbooru returned 503"),
                    )
                )
            else:
                flt, notes = _filtered(sid, q, order_v, rating_v)
                total = len(flt)
                if single:
                    size = clamp_page_size(sid, page_size)
                    pages = pages_for(total, size)
                    pg = clamp_page(page, pages)
                    start = (pg - 1) * size
                    items, nxt = (
                        flt[start : start + size],
                        (pg + 1 if start + size < total else None),
                    )
                    _pages, _page_size = pages, size
                else:
                    items, nxt = flt[:18], (2 if total > 18 else None)
                    _pages, _page_size = None, None
                sections.append(
                    Section(
                        id=cast(SectionId, sid),
                        title=title,
                        items=cast(list[LibraryItem | WebItem], items),
                        total=total,
                        pages=_pages,
                        next_page=nxt,
                        page_size=_page_size,
                        hidden=hidden,
                        notice=(
                            Problem(code=NOTICE_CODE, message=". ".join(notes)) if notes else None
                        ),
                    )
                )

    return SearchResponse(query=q, sections=sections)
