"""Real-mode trash routes: list, restore, Empty, Delete for good, purge preview."""

from fastapi import APIRouter, Query, Request

from app.api.errors import ApiError
from app.library.stash_trash import StashTrash
from app.targets.stash_client import StashError
from app.library.trash import TrashError, TrashStore
from app.models import (
    RestoreResult,
    TrashEmptied,
    TrashItem,
    TrashList,
    TrashPurgePreview,
    TrashResult,
    TrashRoot,
    TrashStatus,
)

router = APIRouter(prefix="/api")


def store_of(request: Request) -> TrashStore:
    return request.app.state.trash


def err(e: TrashError) -> ApiError:
    return ApiError(e.status, e.code, e.message)


def result_of(row: dict, retention_days: int) -> TrashResult:
    return TrashResult(
        token=row["token"],
        expires_at=row["expires_at"],
        retention_days=retention_days,
        item=TrashItem(
            kind=row["kind"],
            id=row["entity_id"],
            title=row["title"],
            size_bytes=row["size_bytes"],
            group_id=row["group_id"],
        ),
    )


@router.get("/trash/status")
def trash_status(request: Request) -> TrashStatus:
    """Per Stash library root: can Pearlie rename a file into the trash folder (probe, 60 s cache)."""
    client = request.app.state.stash
    if client is None:
        raise ApiError(503, "not_configured", "Stash is not configured")
    store = store_of(request)
    try:
        store.check_dir()
        roots = StashTrash(request.app.state.settings, store, client).probe_roots()
    except TrashError as e:
        raise err(e) from None
    except StashError as e:
        raise ApiError(502, "upstream_error", e.message) from None
    return TrashStatus(roots=[TrashRoot(**r) for r in roots])


@router.get("/trash/purge-preview")
def purge_preview(request: Request, days: int = Query(ge=1, le=365)) -> TrashPurgePreview:
    return TrashPurgePreview(count=store_of(request).purge_preview(days))


@router.get("/trash")
def list_trash(request: Request) -> TrashList:
    store = store_of(request)
    days = store.retention_days()
    return TrashList(items=[result_of(r, days) for r in store.list_rows()], retention_days=days)


@router.delete("/trash")
def empty_trash(request: Request) -> TrashEmptied:
    return TrashEmptied(removed=store_of(request).empty())


@router.delete("/trash/{token}", status_code=204)
def delete_for_good(request: Request, token: str) -> None:
    try:
        store_of(request).delete_for_good(token)
    except TrashError as e:
        raise err(e) from None


@router.post("/trash/{token}/restore")
def restore(request: Request, token: str) -> RestoreResult:
    store = store_of(request)
    row = store.get(token)
    if row is None:
        raise ApiError(404, "not_found", "Item not found")
    if row["target"] != "stash":
        raise ApiError(501, "not_supported", "Restoring this item is not available yet")
    client = request.app.state.stash
    if client is None:
        raise ApiError(503, "not_configured", "Stash is not configured")
    try:
        item = StashTrash(request.app.state.settings, store, client).restore(token)
    except TrashError as e:
        raise err(e) from None
    return RestoreResult(item=item)
