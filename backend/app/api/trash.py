from fastapi import APIRouter, Depends

from app.fixtures.scenarios import slow_dependency
from app.fixtures.store import store
from app.models import TrashEmptied, TrashList

router = APIRouter(prefix="/api", dependencies=[Depends(slow_dependency)])


@router.get("/trash")
def list_trash() -> TrashList:
    """List non-expired trash items."""
    return store.list_trash()


@router.delete("/trash")
def empty_trash() -> TrashEmptied:
    """Remove all trash items."""
    return store.empty_trash()
