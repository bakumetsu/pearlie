from __future__ import annotations

from fastapi import APIRouter

from app.api.errors import ApiError
from app.fixtures.scenarios import set_scenario
from app.fixtures.store import store
from app.models import ScenarioBody

router = APIRouter(prefix="/api/_fixture")


@router.post("/reset")
async def reset() -> dict[str, bool]:
    """Reset fixtures and return to the default scenario."""
    store.reset()
    set_scenario("default")
    return {"ok": True}


@router.post("/scenario")
async def switch(body: ScenarioBody) -> dict[str, str]:
    """Activate a named fixture scenario."""
    try:
        set_scenario(body.name)
    except ValueError:
        raise ApiError(422, "unknown_scenario", f"Unknown scenario {body.name}") from None
    return {"scenario": body.name}
