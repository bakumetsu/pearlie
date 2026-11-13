"""Search filter values and the capability list the toolbar renders from."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.errors import ApiError
from app.models import FiltersResponse, SourceFilters
from app.paging import PAGE_SIZE_CAPS, preset_options
from app.sources.filters import (
    ORDERS,
    RATINGS,
    normalize_rating,
    supported_orders,
    supported_ratings,
)

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
    if value not in ORDERS:
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
    """Notice text for filters a site cannot take at all (nhentai)."""
    dropped = []
    if order and not supported_orders(source):
        dropped.append("Order")
    if rating and not supported_ratings(source):
        dropped.append("Rating")
    if not dropped:
        return None
    return f"{' and '.join(dropped)} not available on this site"


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
            sort=_LIBRARY_SORTS,
            favorite=True,
            per_page_options=preset_options(sid),
            per_page_max=PAGE_SIZE_CAPS[sid],
        )
    for sid in _WEB:
        out[sid] = SourceFilters(
            order=supported_orders(sid),
            rating=supported_ratings(sid),
            per_page_options=preset_options(sid),
            per_page_max=PAGE_SIZE_CAPS[sid],
            order_blocked_when=_danbooru_cap(request) if sid == "danbooru" else None,
        )
    return FiltersResponse(sources=out)
