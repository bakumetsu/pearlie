"""Safe-mode display filter: which warn-blurred posts a list drops."""

from __future__ import annotations

from fastapi import Request

from app.api.options import _detect_profile, _read_db, _read_mem
from app.models import Blur


def is_hidden_in_safe_mode(blur: Blur | None, safe: bool, allow_blurred: bool) -> bool:
    """True when a blurred post must be dropped from a list."""
    return blur is not None and safe and not allow_blurred


def _stored(request: Request, key: str) -> bool:
    if request.app.state.settings.mode == "fixture":
        raw = _read_mem(request, key)
    else:
        raw = _read_db(request, key)
    return raw == "1"


def resolve_safe(request: Request, safe_param: bool | None) -> tuple[bool, bool]:
    """Return (safe, allow_blurred) for one request.

    `safe` is the request parameter, else the stored option of the detected profile.
    `allow_blurred` is always the stored global option.
    """
    safe = (
        safe_param
        if safe_param is not None
        else _stored(request, f"options.{_detect_profile(request)}.sfw")
    )
    return safe, _stored(request, "options.global.allow_blurred_tags")
