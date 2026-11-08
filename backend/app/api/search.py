from typing import cast

from fastapi import APIRouter, Depends, Query

from app.api.errors import ApiError
from app.fixtures.scenarios import active, slow_dependency
from app.fixtures.store import store
from app.models import LibraryItem, Problem, SearchResponse, Section, SectionId, WebItem

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


def _filtered(source: str, q: str) -> list:
    """Return web items matching the query."""
    return [
        it
        for it in store.web_items(source)
        if store.matches([t.name for t in it.tags], it.tags, it.title or "", q)
    ]


@router.get("/search")
def search(q: str = "", sources: str = "", page: int = Query(1, ge=1)) -> SearchResponse:
    """Search across library and web sources."""
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
                pg, sz = (page, 60) if single else (1, 12)
                res = store.list_library(kinds, pg, sz, q, "newest", None)
                if res is None:
                    raise ApiError(422, "invalid", "Bad source", field="sources")
                items: list[LibraryItem | WebItem] = [*res.items]
                sections.append(
                    Section(
                        id=cast(SectionId, sid),
                        title=title,
                        items=items,
                        total=res.total,
                        next_page=res.next_page,
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
                flt = _filtered(sid, q)
                total = len(flt)
                if single:
                    start = (page - 1) * 60
                    items, nxt = flt[start : start + 60], (page + 1 if start + 60 < total else None)
                else:
                    items, nxt = flt[:18], (2 if total > 18 else None)
                sections.append(
                    Section(
                        id=cast(SectionId, sid),
                        title=title,
                        items=cast(list[LibraryItem | WebItem], items),
                        total=total,
                        next_page=nxt,
                        hidden=hidden,
                    )
                )

    return SearchResponse(query=q, sections=sections)
