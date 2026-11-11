from fastapi import APIRouter, Depends, Query

from app.fixtures.scenarios import slow_dependency
from app.fixtures.store import store
from app.models import TrashEmptied, TrashList, TrashPurgePreview

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
