"""View settings router: per-source grid mode, page size and zoom."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import TypedDict, cast, get_args

from fastapi import APIRouter, Request

from app.api.errors import ApiError
from app.db import connect
from app.models import ViewMode, ViewSettingBody, ViewSettingItem, ViewSettings, ViewSource
from app.paging import DEFAULT_PAGE_SIZE, PAGE_SIZE_CAPS, preset_options

router = APIRouter(prefix="/api")

SOURCES = list(get_args(ViewSource))
MODES = get_args(ViewMode)


class View(TypedDict):
    mode: ViewMode
    per_page: int
    zoom: int


def _default(source: str) -> View:
    return {
        "mode": "grid",
        "per_page": 25 if source == "nhentai" else DEFAULT_PAGE_SIZE,
        "zoom": 3,
    }


def _stored(request: Request) -> dict[str, View]:
    if request.app.state.settings.mode == "fixture":
        mem: dict[str, View] | None = getattr(
            request.app.state, "view_settings_mem", None
        )
        if mem is None:
            mem = {}
            request.app.state.view_settings_mem = mem
        return mem
    conn = connect(request.app.state.settings.db_path)
    try:
        rows = conn.execute("SELECT key, value FROM settings WHERE key LIKE 'view.%'").fetchall()
    finally:
        conn.close()
    result: dict[str, View] = {}
    for row in rows:
        key: str = row["key"]
        source: str = key.split(".", 1)[1]
        if source not in SOURCES:
            continue
        try:
            value: View = json.loads(row["value"])
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(value, dict):
            continue
        result[source] = value
    return result


def _save(request: Request, source: str, value: View) -> None:
    if request.app.state.settings.mode == "fixture":
        mem: dict[str, View] | None = getattr(
            request.app.state, "view_settings_mem", None
        )
        if mem is None:
            mem = {}
            request.app.state.view_settings_mem = mem
        mem[source] = value
    else:
        conn = connect(request.app.state.settings.db_path)
        try:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (f"view.{source}", json.dumps(value)),
            )
            conn.commit()
        finally:
            conn.close()


def _valid(source: str, raw: Mapping[str, object] | None) -> View | None:
    if raw is None:
        return None
    mode = raw.get("mode")
    per_page = raw.get("per_page")
    zoom = raw.get("zoom")
    if (
        isinstance(mode, str)
        and mode in MODES
        and isinstance(per_page, int)
        and not isinstance(per_page, bool)
        and 1 <= per_page <= PAGE_SIZE_CAPS[source]
        and isinstance(zoom, int)
        and not isinstance(zoom, bool)
        and 1 <= zoom <= 5
    ):
        return {"mode": cast(ViewMode, mode), "per_page": per_page, "zoom": zoom}
    return None


def _item(source: str, values: View) -> ViewSettingItem:
    return ViewSettingItem(
        mode=values["mode"],
        per_page=values["per_page"],
        zoom=values["zoom"],
        per_page_options=preset_options(source),
        per_page_max=PAGE_SIZE_CAPS[source],
    )


@router.get("/view-settings", response_model=ViewSettings)
def get_view_settings(request: Request) -> ViewSettings:
    stored = _stored(request)
    sources: dict[str, ViewSettingItem] = {}
    for source in SOURCES:
        values = _valid(source, stored.get(source))
        if values is None:
            values = _default(source)
        sources[source] = _item(source, values)
    return ViewSettings(sources=sources)


@router.put("/view-settings/{source}", response_model=ViewSettingItem)
def put_view_setting(request: Request, source: str, body: ViewSettingBody) -> ViewSettingItem:
    if source not in SOURCES:
        raise ApiError(422, "invalid", f"Unknown source {source}", field="source")
    if body.mode not in MODES:
        raise ApiError(422, "invalid", "mode must be grid, wall, masonry or list", field="mode")
    cap = PAGE_SIZE_CAPS[source]
    if body.per_page < 1 or body.per_page > cap:
        raise ApiError(422, "invalid", f"per_page must be 1 to {cap}", field="per_page")
    if body.zoom < 1 or body.zoom > 5:
        raise ApiError(422, "invalid", "zoom must be 1 to 5", field="zoom")
    mode = cast(ViewMode, body.mode)
    value: View = {
        "mode": mode,
        "per_page": body.per_page,
        "zoom": body.zoom,
    }
    _save(request, source, value)
    return _item(source, value)
