"""Real job-queue endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query, Request, Response

from app.api.errors import ApiError
from app.filters.rules import evaluate, load_rules
from app.jobs.store import JobStore
from app.jobs.worker import JobWorker
from app.models import Job, JobList, SaveAccepted, SaveBody
from app.sources.base import Source, SourceError

router = APIRouter(prefix="/api")
logger = logging.getLogger("pearlie")

_VALID_STATES: frozenset[str] = frozenset(
    ("queued", "running", "done", "failed", "needs_click", "skipped")
)


def _store(request: Request) -> JobStore:
    return JobStore(request.app.state.settings.db_path)


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
    image_id = store.saved_image_id(body.source, body.post_id)
    if image_id and src.target == "stash":
        # The index can outlive the image: one Stash lookup, drop the row if it is gone.
        if request.app.state.stash_target.drop_if_gone(image_id):
            image_id = store.saved_image_id(body.source, body.post_id)
    if image_id is not None:
        ref: dict[str, str] | None = None if image_id == "" else {"kind": "image", "id": image_id}
        raise ApiError(409, "already_saved", "Already saved", library_ref=ref)
    existing = store.active_job_id(body.source, body.post_id)
    if existing is not None:
        return SaveAccepted(job_id=existing)
    try:
        post = src.get_post(body.post_id)
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
    )
    worker = _worker(request)
    if worker is not None:
        worker.wake()
    return SaveAccepted(job_id=job_id)


@router.get("/jobs")
def list_jobs(request: Request, state: str | None = Query(None)) -> JobList:
    """List jobs, optionally filtered by state CSV."""
    store = _store(request)
    if state is None:
        return JobList(items=store.list(None))
    states: set[str] = set()
    for s in state.split(","):
        s = s.strip()
        if not s:
            continue
        if s not in _VALID_STATES:
            raise ApiError(422, "invalid", f"Unknown state {s}", field="state")
        states.add(s)
    return JobList(items=store.list(states or None))


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
