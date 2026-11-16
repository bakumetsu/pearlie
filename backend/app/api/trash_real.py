"""Real-mode trash routes: list, restore, Empty, Delete for good, purge preview."""

import re
import uuid

from fastapi import APIRouter, Query, Request

from app.api import options
from app.api.errors import ApiError
from app.library.komga_trash import KomgaTrash
from app.library.stash_trash import StashTrash
from app.library.trash import TrashError, TrashStore
from app.models import (
    GroupRestoreResult,
    RestoreResult,
    TrashBatchBody,
    TrashBatchFailure,
    TrashBatchResult,
    TrashEmptied,
    TrashItem,
    TrashList,
    TrashPurgePreview,
    TrashRestoreFailure,
    TrashResult,
    TrashRoot,
    TrashStatus,
)
from app.targets.stash_client import StashError
from app.targets.stash_library import valid_id

router = APIRouter(prefix="/api")


def store_of(request: Request) -> TrashStore:
    return request.app.state.trash


def komga_trash_of(request: Request) -> KomgaTrash:
    return komga_trash_of_app(request.app)


def komga_trash_of_app(app) -> KomgaTrash:  # noqa: ANN001
    """One KomgaTrash per app: it holds the scan debounce timers."""
    kt = getattr(app.state, "komga_trash", None)
    if kt is None:
        kt = KomgaTrash(
            app.state.settings,
            app.state.trash,
            app.state.komga,
            wait_s=lambda: options.komga_scan_wait_s(app),
        )
        app.state.komga_trash = kt
    return kt


def err(e: TrashError) -> ApiError:
    return ApiError(e.status, e.code, e.message)


KOMGA_ID = re.compile(r"[A-Za-z0-9]{1,64}")
PLURAL_OF = {"image": "images", "video": "videos", "series": "series", "book": "books"}


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


@router.post("/library/trash")
def trash_batch(request: Request, body: TrashBatchBody) -> TrashBatchResult:
    """Move 1-50 library items to the trash, one at a time, under one group id."""
    store = store_of(request)
    days = store.retention_days()
    group = uuid.uuid4().hex
    results: list[TrashResult] = []
    failed: list[TrashBatchFailure] = []
    seen: set[tuple[str, str]] = set()
    for it in body.items:
        if (it.kind, it.id) in seen:
            continue
        seen.add((it.kind, it.id))
        try:
            ok = KOMGA_ID.fullmatch(it.id) if it.kind in ("series", "book") else valid_id(it.id)
            if not ok:
                raise TrashError(404, "not_found", "Item not found")
            if it.kind in ("series", "book"):
                if request.app.state.komga is None:
                    raise TrashError(503, "not_configured", "Komga is not configured")
                row = komga_trash_of(request).delete(PLURAL_OF[it.kind], it.id, group_id=group)
            else:
                client = request.app.state.stash
                if client is None:
                    raise TrashError(503, "not_configured", "Stash is not configured")
                row = StashTrash(request.app.state.settings, store, client).delete(
                    PLURAL_OF[it.kind], it.id, group_id=group
                )
            results.append(result_of(row, days))
        except TrashError as e:
            failed.append(TrashBatchFailure(kind=it.kind, id=it.id, code=e.code))
    return TrashBatchResult(group=group, results=results, failed=failed)


@router.post("/trash/group/{group}/restore")
def restore_group(request: Request, group: str) -> GroupRestoreResult:
    """Restore every trashed item of one group; failures are listed, not raised."""
    rows = [r for r in store_of(request).list_rows() if r["group_id"] == group]
    if not rows:
        raise ApiError(404, "not_found", "Item not found")
    restored: list[RestoreResult] = []
    failed: list[TrashRestoreFailure] = []
    for row in rows:
        try:
            restored.append(restore(request, row["token"]))
        except ApiError as e:
            failed.append(TrashRestoreFailure(token=row["token"], code=e.code))
    return GroupRestoreResult(restored=restored, failed=failed)


@router.get("/trash/status")
def trash_status(request: Request) -> TrashStatus:
    """Per Stash library root: can a file be renamed into the trash folder (60 s cache)."""
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
    if row["target"] == "komga":
        if request.app.state.komga is None:
            raise ApiError(503, "not_configured", "Komga is not configured")
        try:
            return RestoreResult(item=komga_trash_of(request).restore(token))
        except TrashError as e:
            raise err(e) from None
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
