"""Real rules endpoints backed by the SQLite rules store."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.errors import ApiError
from app.filters.baselist import BASE_LIST
from app.filters.rules import RuleSet, StaleVersion, evaluate, load_rules, save_rules
from app.models import (
    BaseList,
    RejectAdded,
    RejectRemoved,
    RejectTagBody,
    RuleMapping,
    RulesBody,
    RulesPut,
    RulesTestBody,
    RulesTestResult,
)

router = APIRouter(prefix="/api/rules")


def _body(request: Request) -> RulesBody:
    """Build a RulesBody from the current store."""
    rs = load_rules(request.app.state.settings.db_path)
    return RulesBody(
        version=rs.version,
        reject=rs.reject,
        warn=rs.warn,
        require=rs.require,
        mapping=[
            RuleMapping(pattern=p, to=t)  # pyright: ignore[reportArgumentType]
            for p, t in rs.mapping
        ],
        base_list=BaseList(tags=sorted(BASE_LIST)),
    )


@router.get("")
def get_rules(request: Request) -> RulesBody:
    """Return current rules."""
    return _body(request)


@router.put("")
def put_rules(body: RulesPut, request: Request) -> RulesBody:
    """Replace rules; reject stale versions."""
    db_path = request.app.state.settings.db_path
    reject = [e.strip() for e in body.reject]
    warn = [e.strip() for e in body.warn]
    require = [e.strip() for e in body.require]
    for name, entries in (("reject", reject), ("warn", warn), ("require", require)):
        for e in entries:
            if not (1 <= len(e) <= 64):
                raise ApiError(422, "invalid", f"{name} entry must be 1-64 characters", field=name)
    mapping = [(m.pattern.strip(), m.to) for m in body.mapping]
    for p, _ in mapping:
        if not (1 <= len(p) <= 64):
            raise ApiError(
                422, "invalid", "mapping pattern must be 1-64 characters", field="mapping"
            )
    try:
        save_rules(
            db_path,
            body.version,
            RuleSet(body.version, reject, warn, require, mapping),
        )
    except StaleVersion:
        raise ApiError(409, "stale_version", "Rules changed elsewhere") from None
    return _body(request)


_RETRIES = 3


def _tag(body: RejectTagBody) -> str:
    tag = body.tag.strip()
    if not (1 <= len(tag) <= 64):
        raise ApiError(422, "invalid", "reject entry must be 1-64 characters", field="tag")
    return tag


def _edit_reject(request: Request, tag: str, add: bool) -> tuple[bool, int]:
    """Add or remove one reject entry; retry on a concurrent change. Returns (changed, version)."""
    db_path = request.app.state.settings.db_path
    for _ in range(_RETRIES):
        rs = load_rules(db_path)
        present = tag in rs.reject
        if present == add:
            return False, rs.version
        reject = [*rs.reject, tag] if add else [e for e in rs.reject if e != tag]
        try:
            version = save_rules(
                db_path,
                rs.version,
                RuleSet(rs.version, reject, rs.warn, rs.require, rs.mapping),
            )
        except StaleVersion:
            continue
        return True, version
    raise ApiError(409, "stale_version", "Rules changed elsewhere")


@router.post("/reject")
def reject_tag(body: RejectTagBody, request: Request) -> RejectAdded:
    """Add one tag to the reject list."""
    changed, version = _edit_reject(request, _tag(body), True)
    return RejectAdded(added=changed, version=version)


@router.delete("/reject")
def unreject_tag(body: RejectTagBody, request: Request) -> RejectRemoved:
    """Remove one tag from the reject list (the Undo action)."""
    changed, version = _edit_reject(request, _tag(body), False)
    return RejectRemoved(removed=changed, version=version)


@router.post("/test")
def test_rules(body: RulesTestBody, request: Request) -> RulesTestResult:
    """Evaluate rules against a tag list."""
    db_path = request.app.state.settings.db_path
    tags: dict[str, list[str]] = {}
    for name in body.tags:
        if ":" in name:
            scope, val = name.split(":", 1)
        else:
            scope, val = "", name
        tags.setdefault(scope, []).append(val)
    v = evaluate(tags, load_rules(db_path))
    if v is None:
        return RulesTestResult(decision="allow")
    return RulesTestResult(
        decision=v.decision,
        layer=v.layer,
        rule=v.rule,
        tag=v.tag or None,
        alias=v.alias,
    )
