"""Index Stash images saved before Pearlie tracked them (BUG 8 stop-gap)."""

from __future__ import annotations

import re

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from app.api.errors import ApiError
from app.jobs.store import JobStore
from app.targets.servers import StashClient, StashError

router = APIRouter(prefix="/api")

_FOLDER = "rule34"
_PAGE = 200
_NAME = re.compile(r"^rule34_(\d+)_([0-9a-fA-F]{32})\.[A-Za-z0-9]+$")


class ScanResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    found: int
    imported: int
    skipped: int


def _parse(image: dict) -> tuple[str, str, str] | None:
    """(post id, MD5, image id) when a file sits in the folder and its name matches."""
    for f in image.get("visual_files") or []:
        path = (f.get("path") or "").replace("\\", "/")
        parent = path.rsplit("/", 2)
        if len(parent) < 3 or parent[1] != _FOLDER:
            continue
        m = _NAME.match(f.get("basename") or parent[2])
        if m:
            return m.group(1), m.group(2).lower(), str(image["id"])
    return None


@router.post("/library/scan-rule34", response_model=ScanResult)
def scan_rule34(request: Request) -> ScanResult:
    client: StashClient | None = request.app.state.stash
    if client is None:
        raise ApiError(502, "not_configured", "Stash is not configured")
    rows: list[tuple[str, str, str]] = []
    found = 0
    try:
        page = 1
        while True:
            images, total = client.list_folder_images(f"/{_FOLDER}/", page, _PAGE)
            for image in images:
                found += 1
                row = _parse(image)
                if row:
                    rows.append(row)
            if not images or page * _PAGE >= total:
                break
            page += 1
    except StashError as err:
        raise ApiError(err.status, err.code, err.message) from None
    store = JobStore(request.app.state.settings.db_path)
    added = store.import_saved("rule34", rows)
    return ScanResult(found=found, imported=added, skipped=found - added)
