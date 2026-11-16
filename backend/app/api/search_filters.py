"""Search filter values and the capability list the toolbar renders from."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.errors import ApiError
from app.models import FiltersResponse, Problem, Section, SectionId, SourceFilters
from app.paging import PAGE_SIZE_CAPS, preset_options
from app.sources.filters import (
    ALL_ORDERS,
    NOTICE_CODE,
    RATINGS,
    normalize_rating,
    supported_orders,
    supported_ratings,
)
from app.sources.query_terms import Title

router = APIRouter(prefix="/api")

_LIBRARY_SORTS = ["newest", "rating", "random"]
_LIBRARY = ("stash_images", "stash_videos", "komga_books")
_WEB = ("danbooru", "gelbooru", "rule34", "nhentai")
_DANBOORU_ANON_CAP = 2


def parse_order(order: str) -> str | None:
    """Validate the order param; None for the default (newest)."""
    value = order.strip().lower()
    if value in ("", "newest"):
        return None
    if value not in ALL_ORDERS:
        raise ApiError(422, "invalid", f"Unknown order {order}", field="order")
    return value


def parse_rating(rating: str) -> list[str]:
    """Validate the rating csv; the empty list means no filter."""
    values = [v.strip().lower() for v in rating.split(",") if v.strip()]
    for v in values:
        if v not in RATINGS:
            raise ApiError(422, "invalid", f"Unknown rating {v}", field="rating")
    return normalize_rating(values)


def unsupported_notice(source: str, order: str | None, rating: list[str]) -> str | None:
    """Notice text for filters a site cannot take (an order it lacks, nhentai ratings)."""
    dropped = []
    if order and order not in supported_orders(source):
        dropped.append("Order")
    if rating and not supported_ratings(source):
        dropped.append("Rating")
    if not dropped:
        return None
    return f"{' and '.join(dropped)} not available on this site"


_TITLE_SEARCH = ("nhentai", "komga_books")
_TITLE_EXCLUDE = ("nhentai",)


def title_notice(source: str, titles: list[Title]) -> str | None:
    """Why a source is skipped for these title chips, or None when it can run them."""
    if not titles:
        return None
    if source not in _TITLE_SEARCH:
        return "Title search not available on this site"
    if source not in _TITLE_EXCLUDE and any(t.exclude for t in titles):
        return "Title exclusion not available on this site"
    return None


def skipped_section(sid: SectionId, title: str, note: str) -> Section:
    """An empty section that says why the source was not asked (no request is sent)."""
    return Section(
        id=sid,
        title=title,
        items=[],
        total=0,
        next_page=None,
        hidden=0,
        notice=Problem(code=NOTICE_CODE, message=note),
    )


def _danbooru_cap(request: Request) -> int:
    src = getattr(request.app.state, "sources", {}).get("danbooru")
    cap = getattr(src, "tag_limit", None)
    return cap if isinstance(cap, int) else _DANBOORU_ANON_CAP


@router.get("/search/filters")
def search_filters(request: Request) -> FiltersResponse:
    """Per source: which filters its toolbar offers. No site call."""
    out: dict[str, SourceFilters] = {}
    for sid in _LIBRARY:
        out[sid] = SourceFilters(
            search=True,
            sort=_LIBRARY_SORTS,
            favorite=True,
            per_page_options=preset_options(sid),
            per_page_max=PAGE_SIZE_CAPS[sid],
            title_search=sid in _TITLE_SEARCH,
            title_exclude=sid in _TITLE_EXCLUDE,
        )
    for sid in _WEB:
        out[sid] = SourceFilters(
            search=True,
            order=supported_orders(sid),
            rating=supported_ratings(sid),
            per_page_options=preset_options(sid),
            per_page_max=PAGE_SIZE_CAPS[sid],
            order_blocked_when=_danbooru_cap(request) if sid == "danbooru" else None,
            title_search=sid in _TITLE_SEARCH,
            title_exclude=sid in _TITLE_EXCLUDE,
        )
    return FiltersResponse(sources=out)
