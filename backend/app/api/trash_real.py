"""Real-mode trash routes: list, restore, Empty, Delete for good, purge preview."""

import logging
import os
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Query, Request

from app.api import options
from app.api.errors import ApiError
from app.bookserver.base import BOOK_TARGETS, BookServerError
from app.bookserver.factory import book_server_of
from app.library.trash import TrashError, TrashStore
from app.models import (
    GroupRestoreResult,
    RestoreResult,
    TrashBatchBody,
    TrashBatchFailure,
    TrashBatchResult,
    TrashEmptied,
    TrashFolder,
    TrashFolderBody,
    TrashItem,
    TrashList,
    TrashPurgePreview,
    TrashRestoreFailure,
    TrashResult,
    TrashRoot,
    TrashStatus,
)
from app.targets.servers import StashError, StashTrash, StumpTrash, valid_id

logger = logging.getLogger("pearlie")

router = APIRouter(prefix="/api")


def store_of(request: Request) -> TrashStore:
    return request.app.state.trash


def stump_trash_of(request: Request) -> StumpTrash:
    return stump_trash_of_app(request.app)


def stump_trash_of_app(app) -> StumpTrash:  # noqa: ANN001
    """One book-server trash per app: it holds the scan debounce timers."""
    kt = getattr(app.state, "stump_trash", None)
    if kt is None:
        kt = StumpTrash(
            app.state.settings,
            app.state.trash,
            book_server_of(app),
            wait_s=lambda: options.stump_scan_wait_s(app),
        )
        app.state.stump_trash = kt
    return kt


def book_server_ready(app) -> bool:  # noqa: ANN001
    return bool(app.state.settings.stump_url)


def _book_server_name(app) -> str:  # noqa: ANN001
    return "Stump"


def err(e: TrashError) -> ApiError:
    return ApiError(e.status, e.code, e.message)


STUMP_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
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
            ok = STUMP_ID.fullmatch(it.id) if it.kind in ("series", "book") else valid_id(it.id)
            if not ok:
                raise TrashError(404, "not_found", "Item not found")
            if it.kind in ("series", "book"):
                if not book_server_ready(request.app):
                    name = _book_server_name(request.app)
                    raise TrashError(503, "not_configured", f"{name} is not configured")
                row = stump_trash_of(request).delete(PLURAL_OF[it.kind], it.id, group_id=group)
            else:
                client = request.app.state.stash
                if client is None:
                    raise TrashError(503, "not_configured", "Stash is not configured")
                row = StashTrash(request.app.state.settings, store, client).delete(
                    PLURAL_OF[it.kind], it.id, group_id=group
                )
            results.append(result_of(row, days))
        except TrashError as e:
            logger.warning(
                "trash refused kind=%s id=%s code=%s status=%s", it.kind, it.id, e.code, e.status
            )
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


def _folder_state(path: Path) -> str:
    if not path.is_dir():
        return "missing"
    return "ok" if os.access(path, os.W_OK) else "not_writable"


def _folder_of(store: TrashStore) -> TrashFolder:
    stored = store.stored_dir()
    path = store.dir
    return TrashFolder(
        path=str(path),
        source="stored" if stored else "env",
        env_path=str(store.default_dir),
        state=_folder_state(path),  # type: ignore[arg-type]
        items=store.item_count(),
    )


def _abs_path(raw: str) -> Path:
    p = Path(raw.strip())
    if not raw.strip() or not p.is_absolute():
        raise ApiError(422, "invalid_path", "Enter an absolute folder path")
    return p


def _library_roots(request: Request) -> list[str]:
    """Real paths of every Stash and Stump library root (Pearlie side)."""
    app = request.app
    roots: list[str] = []
    try:
        if app.state.stash is not None:
            st = StashTrash(app.state.settings, store_of(request), app.state.stash)
            roots += [os.path.realpath(st._to_local(p)) for p in app.state.stash.library_paths()]
        if book_server_ready(app):
            roots += stump_trash_of(request)._roots()
    except (StashError, BookServerError) as e:
        raise ApiError(502, "upstream_error", e.message) from None
    return roots


def _check_candidate(request: Request, path: Path) -> None:
    """Writable, outside every library root, same volume as each Stash library root."""
    if not path.is_dir():
        raise ApiError(422, "folder_missing", "Folder does not exist; create it first")
    if not os.access(path, os.W_OK):
        raise ApiError(422, "not_writable", "Folder is not writable")
    real = os.path.realpath(path)
    for root in _library_roots(request):
        if real == root or real.startswith(root + os.sep):
            raise ApiError(422, "inside_library", "Folder is inside a library")
    client = request.app.state.stash
    if client is not None:
        try:
            probes = StashTrash(request.app.state.settings, store_of(request), client)
            roots = probes.probe_candidate(path)
        except StashError as e:
            raise ApiError(502, "upstream_error", e.message) from None
        for r in roots:
            if r["state"] == "other_volume":
                raise ApiError(422, "other_volume", "Folder is not on the same mount as Stash")
            if r["state"] == "not_reachable":
                msg = "Stash library folder is not reachable"
                raise ApiError(422, "stash_root_unreachable", msg)


@router.get("/trash/folder")
def trash_folder(request: Request) -> TrashFolder:
    return _folder_of(store_of(request))


@router.put("/trash/folder")
def set_trash_folder(request: Request, body: TrashFolderBody) -> TrashFolder:
    store = store_of(request)
    raw = body.path.strip()
    target = Path(raw) if not raw else _abs_path(raw)
    # Reset uses the .env folder; it must pass the same checks.
    check = target if raw else store.default_dir
    try:
        store.set_dir(raw or None, lambda: _check_candidate(request, check))
    except TrashError as e:
        raise err(e) from None
    return _folder_of(store)


@router.post("/trash/folder/create")
def create_trash_folder(request: Request, body: TrashFolderBody) -> TrashFolder:
    store = store_of(request)
    path = _abs_path(body.path) if body.path.strip() else store.dir
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        raise ApiError(422, "cannot_create", "Cannot create the folder") from None
    return _folder_of(store)


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
    if row["target"] in BOOK_TARGETS:
        if not book_server_ready(request.app):
            name = _book_server_name(request.app)
            raise ApiError(503, "not_configured", f"{name} is not configured")
        try:
            return RestoreResult(item=stump_trash_of(request).restore(token))
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
