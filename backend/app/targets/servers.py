"""The one place where API routes reach the concrete storage servers.

Routes import server names only from here; they never import the Stash or Stump
adapter modules themselves. Swapping a server then touches this module only.
"""

from __future__ import annotations

from typing import Any

from app.bookserver.base import BookDTO
from app.library.stash_trash import StashTrash
from app.library.stump_trash import StumpTrash
from app.targets import stash_library
from app.targets.stash import SaveError
from app.targets.stash_client import StashClient, StashError
from app.targets.stash_library import (
    image_detail,
    image_item,
    list_notice,
    log_gif_rejects,
    map_items,
    stash_sort,
    valid_id,
    video_detail,
    video_item,
)
from app.targets.stump import VERIFY_PAGE_SIZE, StumpTarget

__all__ = [
    "VERIFY_PAGE_SIZE",
    "SaveError",
    "StashClient",
    "StashError",
    "StashTrash",
    "StumpTrash",
    "book_matches",
    "image_detail",
    "image_item",
    "list_notice",
    "log_gif_rejects",
    "map_items",
    "stash_sort",
    "valid_id",
    "video_detail",
    "video_item",
    "stash_of",
    "stash_library",
]


def book_matches(book: BookDTO, post_id: str) -> bool:
    """True when a library book is the saved copy of *post_id*."""
    return StumpTarget._book_matches(book, post_id)


def stash_of(app: Any) -> StashClient | None:
    """The Stash client of the running app (None when Stash is not configured)."""
    return app.state.stash
