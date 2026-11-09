"""Paging helpers."""

from __future__ import annotations

import math

PAGE_SIZE_CAPS: dict[str, int] = {
    "stash_images": 200,
    "stash_videos": 200,
    "komga_series": 200,
    "komga_books": 200,
    "danbooru": 200,
    "gelbooru": 100,
    "rule34": 100,
    "nhentai": 25,
}

DEFAULT_PAGE_SIZE = 60
PRESETS = [20, 40, 60, 100, 200]


def clamp_page_size(source: str, size: int) -> int:
    """Clamp a requested page size to the source cap."""
    return max(1, min(size, PAGE_SIZE_CAPS[source]))


def pages_for(total: int, page_size: int) -> int:
    """Total page count for a result set."""
    return math.ceil(total / page_size)


def clamp_page(page: int, pages: int | None) -> int:
    """Clamp a 1-based page index to the valid range."""
    if pages is None:
        return page
    return min(page, max(pages, 1))


def preset_options(source: str) -> list[int]:
    """Available page-size presets for a source."""
    if source == "nhentai":
        return [25]
    cap = PAGE_SIZE_CAPS[source]
    return [p for p in PRESETS if p <= cap]
