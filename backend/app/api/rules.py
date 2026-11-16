"""Rules CRUD endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.errors import ApiError
from app.fixtures.rules import RulesInvalid, Stale, rules
from app.fixtures.scenarios import slow_dependency
from app.models import (
    RejectAdded,
    RejectRemoved,
    RejectTagBody,
    RulesBody,
    RulesPut,
    RulesTestBody,
    RulesTestResult,
)
from app.sources.query_terms import is_reserved

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


def _tag(body: RejectTagBody) -> str:
    tag = body.tag.strip()
    if not (1 <= len(tag) <= 64):
        raise ApiError(422, "invalid", "reject entry must be 1-64 characters", field="tag")
    if is_reserved(tag):
        raise ApiError(422, "invalid", "reject entry uses a reserved prefix", field="tag")
    return tag


@router.post("/reject")
def reject_tag(body: RejectTagBody) -> RejectAdded:
    """Add one tag to the reject list."""
    tag = _tag(body)
    if tag in rules.reject:
        return RejectAdded(added=False, version=rules.version)
    rules.reject.append(tag)
    rules.version += 1
    return RejectAdded(added=True, version=rules.version)


@router.delete("/reject")
def unreject_tag(body: RejectTagBody) -> RejectRemoved:
    """Remove one tag from the reject list (the Undo action)."""
    tag = _tag(body)
    if tag not in rules.reject:
        return RejectRemoved(removed=False, version=rules.version)
    rules.reject.remove(tag)
    rules.version += 1
    return RejectRemoved(removed=True, version=rules.version)


@router.post("/test")
def test_rules(body: RulesTestBody) -> RulesTestResult:
    """Evaluate rules against a tag list."""
    if any(is_reserved(n) for n in body.tags):
        raise ApiError(422, "invalid", "title: and id: are search chips, not tags", field="tags")
    return rules.test(body.tags)
