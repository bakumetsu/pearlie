# Per-side PATCH support rule shared by fixture and real handlers.

from __future__ import annotations

from app.api.errors import ApiError
from app.models import PatchBody


def check_patch(side: str, body: PatchBody) -> None:
    """Raise ApiError if *body* contains fields unsupported by *side*."""
    if body.favorite is not None:
        raise ApiError(
            422, "unsupported_field", f"{side} cannot store favorite", field="favorite"
        )
    if side == "Komga" and body.rating is not None:
        raise ApiError(
            422, "unsupported_field", f"{side} cannot store rating", field="rating"
        )
