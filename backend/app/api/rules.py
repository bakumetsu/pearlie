"""Rules CRUD endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.errors import ApiError
from app.fixtures.rules import RulesInvalid, Stale, rules
from app.fixtures.scenarios import slow_dependency
from app.models import RulesBody, RulesPut, RulesTestBody, RulesTestResult

router = APIRouter(prefix="/api/rules", dependencies=[Depends(slow_dependency)])


@router.get("")
def get_rules() -> RulesBody:
    """Return current rules."""
    return rules.get()


@router.put("")
def put_rules(body: RulesPut) -> RulesBody:
    """Replace rules; reject stale versions."""
    try:
        return rules.put(body)
    except Stale:
        raise ApiError(409, "stale_version", "Rules changed elsewhere") from None
    except RulesInvalid as exc:
        raise ApiError(422, "invalid", str(exc), field=exc.field) from None


@router.post("/test")
def test_rules(body: RulesTestBody) -> RulesTestResult:
    """Evaluate rules against a tag list."""
    return rules.test(body.tags)
