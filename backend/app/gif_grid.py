"""Which animated GIFs may play in a grid tile (one cap, used by the web and library mappers)."""

from __future__ import annotations

GIF_GRID_MAX_BYTES = 8 * 1024 * 1024


def grid_gif_reject(
    name: str | None, size: int | None, cap: int | None = GIF_GRID_MAX_BYTES
) -> str | None:
    """None when the GIF may play, else the reason: not_gif, no_size or too_big.

    With cap=None (local Stash) any size passes, a missing size too.
    """
    if not name or not name.lower().split("?", 1)[0].endswith(".gif"):
        return "not_gif"
    if cap is None:
        return None
    if size is None or size < 0:
        return "no_size"
    return "too_big" if size > cap else None


def grid_gif_ok(name: str | None, size: int | None) -> bool:
    """True for a .gif name (query ignored) with a known size at or under the cap."""
    return grid_gif_reject(name, size) is None
