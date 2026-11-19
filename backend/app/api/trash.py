from fastapi import APIRouter, Depends, Query

from app.api.errors import ApiError
from app.fixtures.scenarios import slow_dependency
from app.fixtures.store import store
from app.models import (
    GroupRestoreResult,
    TrashBatchBody,
    TrashBatchResult,
    TrashEmptied,
    TrashList,
    TrashPurgePreview,
)

router = APIRouter(prefix="/api", dependencies=[Depends(slow_dependency)])


@router.get("/trash/purge-preview")
def purge_preview(days: int = Query(ge=1, le=365)) -> TrashPurgePreview:
    """Count demo trash items a lower retention would purge now."""
    return TrashPurgePreview(count=store.purge_preview(days))


@router.get("/trash")
def list_trash() -> TrashList:
    """List non-expired trash items."""
    return store.list_trash()


@router.delete("/trash")
def empty_trash() -> TrashEmptied:
    """Remove all trash items."""
    return store.empty_trash()


@router.post("/library/trash")
def trash_batch(body: TrashBatchBody) -> TrashBatchResult:
    """Move 1-50 demo items to the trash under one group id."""
    return store.delete_batch([(i.kind, i.id) for i in body.items])


@router.post("/trash/group/{group}/restore")
def restore_group(group: str) -> GroupRestoreResult:
    """Restore every trashed demo item of one group."""
    result = store.restore_group(group)
    if result is None:
        raise ApiError(404, "not_found", "Item not found")
    return result
