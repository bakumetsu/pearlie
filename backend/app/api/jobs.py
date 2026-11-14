"""Job management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response

from app.api.errors import ApiError
from app.fixtures.jobs import BadState, Conflict, Rejected
from app.fixtures.scenarios import active, slow_dependency
from app.fixtures.store import store
from app.models import Job, JobList, PlacementSuggestion, SaveAccepted, SaveBody, WebSource

router = APIRouter(prefix="/api", dependencies=[Depends(slow_dependency)])


@router.post("/save", status_code=202)
def save(body: SaveBody) -> SaveAccepted:
    """Queue a new save job."""
    if active("conflict"):
        raise ApiError(
            409, "already_saved", "Already saved", library_ref={"kind": "image", "id": "0"}
        )
    if store.web_raw(body.source, body.post_id) is None:
        raise ApiError(404, "not_found", "Job not found")
    try:
        job_id = store.jobs.save(body.source, body.post_id)
    except Conflict as exc:
        raise ApiError(409, "already_saved", "Already saved", library_ref=exc.library_ref) from None
    except Rejected:
        raise ApiError(
            422,
            "rejected_by_rule",
            "Blocked by reject list: reject_alpha",
            layer="reject",
            rule="reject_alpha",
            tag="reject_alpha",
            alias=None,
        ) from None
    return SaveAccepted(job_id=job_id)


@router.get("/save/placement")
def save_placement(
    source: WebSource = Query(...), post_id: str = Query(...)
) -> PlacementSuggestion:
    """Suggest series or oneshot for a Komga save (fixture: always a oneshot)."""
    if store.web_raw(source, post_id) is None:
        raise ApiError(404, "not_found", "Post not found")
    return PlacementSuggestion(
        kind="oneshot",
        series=None,
        number=None,
        joins_existing=False,
        moves_first=False,
        reason="oneshot",
    )


@router.get("/jobs")
def list_jobs(state: str | None = Query(None)) -> JobList:
    """List jobs, optionally filtered by state CSV."""
    states: set[str] | None = set(state.split(",")) if state else None
    return JobList(items=store.jobs.list(states))


@router.get("/jobs/{id}")
def get_job(id: str) -> Job:
    """Fetch a single job by id."""
    job = store.jobs.get(id)
    if job is None:
        raise ApiError(404, "not_found", "Job not found")
    return job


@router.post("/jobs/{id}/retry")
def retry_job(id: str) -> Job:
    """Retry a failed job."""
    if active("errors"):
        raise ApiError(502, "upstream_error", "Retry failed")
    if store.jobs.get(id) is None:
        raise ApiError(404, "not_found", "Job not found")
    try:
        job = store.jobs.retry(id)
    except BadState:
        raise ApiError(409, "bad_state", "Only failed or needs_click jobs can be retried") from None
    if job is None:
        raise ApiError(404, "not_found", "Job not found")
    return job


@router.delete("/jobs/{id}", status_code=204)
def delete_job(id: str) -> Response:
    """Delete a job."""
    if store.jobs.get(id) is None:
        raise ApiError(404, "not_found", "Job not found")
    try:
        store.jobs.delete(id)
    except BadState:
        raise ApiError(409, "bad_state", "Job is running") from None
    return Response(status_code=204)
