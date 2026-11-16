"""Which animated GIFs may play in a grid tile (one cap, used by the web and library mappers)."""

from __future__ import annotations

GIF_GRID_MAX_BYTES = 8 * 1024 * 1024


def grid_gif_ok(name: str | None, size: int | None) -> bool:
    """True for a .gif name (query ignored) with a known size at or under the cap."""
    if not name or size is None or size < 0:
        return False
    return name.lower().split("?", 1)[0].endswith(".gif") and size <= GIF_GRID_MAX_BYTES
