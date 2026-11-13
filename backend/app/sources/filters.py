"""Order and rating filters for web sources: values, per-site tag mapping, slot planning."""

from __future__ import annotations

ORDERS = ("newest", "score")
RATINGS = ("g", "s", "q", "e")

SCORE_TAG_DANBOORU = "order:score"
SCORE_TAG_DAPI = "sort:score:desc"

# Rating letters each site can take; None-valued sites take no filter at all.
DAPI_RATING_NAMES: dict[str, dict[str, str]] = {
    "gelbooru": {"g": "general", "s": "sensitive", "q": "questionable", "e": "explicit"},
    "rule34": {"g": "safe", "q": "questionable", "e": "explicit"},
}

NOTICE_CODE = "filter_notice"


def normalize_rating(values: list[str]) -> list[str]:
    """Ratings in g,s,q,e order without duplicates."""
    return [r for r in RATINGS if r in values]


def supported_orders(source: str) -> list[str]:
    """Order values a web source offers (empty: none)."""
    return [] if source == "nhentai" else list(ORDERS)


def supported_ratings(source: str) -> list[str]:
    """Rating letters a web source offers (empty: none)."""
    if source == "nhentai":
        return []
    if source in DAPI_RATING_NAMES:
        return list(DAPI_RATING_NAMES[source])
    return list(RATINGS)


def dapi_filter_tags(
    source: str, order: str | None, rating: list[str]
) -> tuple[list[str], list[str]]:
    """Server tags for a dapi site and the notices for what it cannot take."""
    names = DAPI_RATING_NAMES[source]
    tags: list[str] = []
    notices: list[str] = []
    if order == "score":
        tags.append(SCORE_TAG_DAPI)
    wanted = [r for r in normalize_rating(rating) if r in names]
    if rating and not wanted:
        notices.append("Rating is not available on this site")
    elif wanted and len(wanted) < len(names):
        if len(wanted) == 1:
            tags.append(f"rating:{names[wanted[0]]}")
        else:
            tags.extend(f"-rating:{n}" for k, n in names.items() if k not in wanted)
    return tags, notices


def danbooru_plan(
    tags: list[str], order: str | None, rating: list[str], limit: int
) -> tuple[list[str], list[str], list[str]]:
    """Split search words and filters into (server tags, local tags, notices).

    Slot order: the user's words first, then Order, then Rating. Words past the cap stay local.
    """
    server = tags[:limit]
    local = tags[limit:]
    notices: list[str] = []
    free = limit - len(server)
    if order == "score":
        if free > 0:
            server.append(SCORE_TAG_DANBOORU)
            free -= 1
        else:
            notices.append("Order needs a free tag slot; not applied")
    ratings = normalize_rating(rating)
    if 0 < len(ratings) < len(RATINGS):
        tag = "rating:" + ",".join(ratings)
        if free > 0:
            server.append(tag)
        else:
            local.append(tag)
            notices.append("Rating filtered on this page only")
    return server, local, notices
