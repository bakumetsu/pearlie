"""Real job-queue endpoints."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from app.api.errors import ApiError
from app.filters.rules import evaluate, load_rules
from app.jobs.store import JobStore
from app.jobs.worker import JobWorker
from app.models import Job, JobList, PlacementSuggestion, SaveAccepted, SaveBody, WebSource
from app.sources.base import Post, Source, SourceError
from app.targets.servers import SaveError

router = APIRouter(prefix="/api")
logger = logging.getLogger("pearlie")

_VALID_STATES: frozenset[str] = frozenset(
    ("queued", "running", "scan_wait", "verifying", "done", "failed", "needs_click", "skipped")
)


def _store(request: Request) -> JobStore:
    return JobStore(request.app.state.settings.db_path)


def _get_post(request: Request, src: Source, post_id: str) -> Post:
    """get_post, reusing the gallery the book page cached (no second site call)."""
    if src.id == "nhentai":
        from app.api.media_web_pages import cached_post

        post = cached_post(request, post_id.strip())
        if post is not None:
            return post
    return src.get_post(post_id)


def _worker(request: Request) -> JobWorker | None:
    return getattr(request.app.state, "worker", None)


@router.post("/save", status_code=202)
def save(body: SaveBody, request: Request) -> SaveAccepted:
    """Queue a new save job."""
    sources: dict[str, Source] = request.app.state.sources
    src = sources.get(body.source)
    if src is None:
        raise ApiError(422, "source_unavailable", f"{body.source} is not connected")
    if getattr(request.app.state, src.target, None) is None:
        raise ApiError(422, "no_target", f"saving from {body.source} is not available")
    store = _store(request)
    trashed = request.app.state.trash.find_in_trash(body.source, body.post_id)
    if trashed is not None:
        raise ApiError(
            409, "in_trash", "Already saved, in the trash", in_trash=True, token=trashed["token"]
        )
    stump_target = getattr(request.app.state, "stump_target", None)
    if src.target == "stump" and stump_target is not None:
        token = stump_target.trash_token(body.source, body.post_id)
        if token is not None:
            raise ApiError(
                409, "in_trash", "Already saved, in the trash", in_trash=True, token=token
            )
    image_id = store.saved_image_id(body.source, body.post_id)
    if image_id and src.target == "stash":
        # The index can outlive the image: one Stash lookup, drop the row if it is gone.
        kind = store.saved_kind(body.source, body.post_id)
        if request.app.state.stash_target.drop_if_gone(image_id, kind):
            image_id = store.saved_image_id(body.source, body.post_id)
    elif image_id == "" and src.target == "stump":
        # Same for Stump: one search, drop the row if the book was deleted there.
        stump_target = getattr(request.app.state, "stump_target", None)
        if stump_target is not None and stump_target.drop_if_gone(body.source, body.post_id):
            image_id = store.saved_image_id(body.source, body.post_id)
    if image_id is not None:
        kind = store.saved_kind(body.source, body.post_id) if src.target == "stash" else "image"
        ref: dict[str, str] | None = None if image_id == "" else {"kind": kind, "id": image_id}
        raise ApiError(409, "already_saved", "Already saved", library_ref=ref)
    existing = store.active_job_id(body.source, body.post_id)
    if existing is not None:
        return SaveAccepted(job_id=existing)
    try:
        post = _get_post(request, src, body.post_id)
    except SourceError as e:
        if e.status == 404 or e.code == "not_found":
            raise ApiError(404, "not_found", "Post not found") from None
        raise ApiError(502, e.code, e.message) from None
    verdict = evaluate(post.tags, load_rules(request.app.state.settings.db_path))
    if verdict is not None and verdict.decision != "warn":
        logger.info(
            "save blocked: layer=%s rule=%s tag=%s", verdict.layer, verdict.rule, verdict.tag
        )
        raise ApiError(
            422,
            "rejected_by_rule",
            f"Blocked by {verdict.layer} list: {verdict.rule}",
            layer=verdict.layer,
            rule=verdict.rule,
            tag=verdict.tag,
            alias=verdict.alias,
        )
    job_id = store.enqueue(
        post,
        src.target,
        title=post.title or f"{post.source} {post.post_id}",
        thumb_url=post.preview_url or "",
        placement=body.placement.kind if body.placement else None,
    )
    worker = _worker(request)
    if worker is not None:
        worker.wake()
    return SaveAccepted(job_id=job_id)


@router.get("/save/placement")
def save_placement(
    request: Request,
    source: Annotated[WebSource, Query()],
    post_id: Annotated[str, Query()],
) -> PlacementSuggestion:
    """Suggest series or oneshot for a Stump save. Pure: nothing is written."""
    src = request.app.state.sources.get(source)
    target = getattr(request.app.state, "stump_target", None)
    if src is None or src.target != "stump" or target is None:
        raise ApiError(422, "no_target", f"{source} does not save to Stump")
    try:
        post = _get_post(request, src, post_id)
    except SourceError as e:
        if e.status == 404 or e.code == "not_found":
            raise ApiError(404, "not_found", "Post not found") from None
        raise ApiError(502, e.code, e.message) from None
    try:
        plan = target.suggest(post)
    except SaveError as e:
        raise ApiError(e.status, e.code, e.message) from None
    joins = plan.via in ("folder", "absorb", "oneshot_pair")
    return PlacementSuggestion(
        kind="series" if plan.kind == "series" else "oneshot",
        series=plan.series,
        number=plan.number or None,
        joins_existing=joins,
        moves_first=bool(plan.move_from),
        reason=plan.via,
    )


@router.get("/jobs")
def list_jobs(
    request: Request,
    state: str | None = Query(None),
    limit: int = Query(500, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> JobList:
    """List jobs, optionally filtered by state CSV and paged by limit/offset."""
    store = _store(request)
    if state is None:
        return JobList(items=store.list(None, limit, offset))
    states: set[str] = set()
    for s in state.split(","):
        s = s.strip()
        if not s:
            continue
        if s not in _VALID_STATES:
            raise ApiError(422, "invalid", f"Unknown state {s}", field="state")
        states.add(s)
    return JobList(items=store.list(states or None, limit, offset))


@router.get("/jobs/{id}")
def get_job(id: str, request: Request) -> Job:
    """Fetch a single job by id."""
    store = _store(request)
    job = store.get(id)
    if job is None:
        raise ApiError(404, "not_found", "Job not found")
    return job


@router.post("/jobs/{id}/retry")
def retry_job(id: str, request: Request) -> Job:
    """Retry a failed or needs_click job."""
    store = _store(request)
    res: str = store.retry(id)
    if res == "missing":
        raise ApiError(404, "not_found", "Job not found")
    if res == "bad_state":
        raise ApiError(409, "bad_state", "Only failed or needs_click jobs can be retried")
    if res == "conflict":
        raise ApiError(
            409,
            "bad_state",
            "Another job for this post is already queued or running",
        )
    worker = _worker(request)
    if worker is not None:
        worker.wake()
    job = store.get(id)
    if job is None:
        raise ApiError(404, "not_found", "Job not found")
    return job


@router.delete("/jobs/{id}", status_code=204)
def delete_job(id: str, request: Request) -> Response:
    """Delete a job."""
    store = _store(request)
    res: str = store.delete(id)
    if res == "missing":
        raise ApiError(404, "not_found", "Job not found")
    if res == "bad_state":
        raise ApiError(409, "bad_state", "Job is running")
    return Response(status_code=204)
