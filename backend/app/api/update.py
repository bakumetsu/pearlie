"""Update API: status, settings, and apply endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, StrictBool

from app.api.errors import ApiError
from app.api.guard import write_guard
from app.db import connect
from app.update import runner
from app.update import version as update_version

router = APIRouter(prefix="/api/update")


# ── Pydantic models ──────────────────────────────────────────────────────────


class InstalledOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    channel: str
    commit: str | None


class LatestOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    commit: str | None
    url: str


class StatusOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    installed: InstalledOut
    latest: LatestOut | None
    available: bool
    checked_at: str | None
    check_enabled: bool
    channel: Literal["main", "dev"]
    state: str
    step: str | None
    error: str | None
    retry_after: int | None
    can_apply: bool


class SettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel: Literal["main", "dev"] | None = None
    check_enabled: StrictBool | None = None


class ChangeGroupOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["Added", "Fixed", "Reworked"]
    items: list[str]


class ChangeBlockOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    range: str | None
    version: str | None
    date: str | None
    groups: list[ChangeGroupOut]
    total: int
    more: int
    more_url: str | None


class ChangelogOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel: Literal["main", "dev"]
    unavailable: bool
    stale: bool
    whats_new: ChangeBlockOut | None
    history: list[ChangeBlockOut]
    has_more: bool


class ApplyOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: Literal["running"]


# ── Settings helpers ─────────────────────────────────────────────────────────


def _get(db_path: Path, key: str) -> str | None:
    conn = connect(db_path)
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None
    finally:
        conn.close()


def _set(db_path: Path, key: str, value: str) -> None:
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()
    finally:
        conn.close()


# ── Shared status builder ────────────────────────────────────────────────────


def _status(request: Request, refresh: bool, manual: bool) -> StatusOut:
    app_state = request.app.state
    db_path: Path = app_state.settings.db_path
    mode: str = app_state.settings.mode
    root: Path = app_state.update_root
    run = app_state.update_run
    checker = app_state.update_checker

    raw_channel = _get(db_path, "update.channel")
    channel: Literal["main", "dev"] = raw_channel if raw_channel in ("main", "dev") else "main"

    raw_check = _get(db_path, "update.check")
    check_enabled = raw_check != "off"  # default "on"

    if refresh and (check_enabled or manual):
        result = checker.check(channel, force=True)
    else:
        result = checker.cached(channel)

    installed = update_version.current_version()

    available = False
    if result and result.latest:
        latest_ref = result.latest.version if channel == "main" else (result.latest.commit or "")
        installed_ref = installed.version if channel == "main" else (installed.commit or "")
        available = update_version.is_newer(latest_ref, installed_ref, channel)

    status = runner.read_status(root)
    state: str = status.get("state") or "idle"
    step: str | None = status.get("step")
    status_error: str | None = status.get("error")
    check_error: str | None = result.error if result else None
    # check error wins only when status-file error is absent
    error: str | None = status_error if status_error is not None else check_error

    if state == "idle" and runner.is_running(run=run):
        state = "running"

    can_apply = mode == "real" and runner.supported(root)

    latest_out: LatestOut | None = None
    if result and result.latest:
        latest_out = LatestOut(
            version=result.latest.version,
            commit=result.latest.commit,
            url=result.latest.url,
        )

    return StatusOut(
        installed=InstalledOut(
            version=installed.version,
            channel=installed.channel,
            commit=installed.commit,
        ),
        latest=latest_out,
        available=available,
        checked_at=result.checked_at if result else None,
        check_enabled=check_enabled,
        channel=channel,
        state=state,
        step=step,
        error=error,
        retry_after=result.retry_after if result else None,
        can_apply=can_apply,
    )


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/status")
def get_status(
    request: Request,
    refresh: bool = Query(False),
    manual: bool = Query(False),
) -> StatusOut:
    return _status(request, refresh, manual)


@router.get("/changelog")
def get_changelog(
    request: Request,
    channel: Literal["main", "dev"] | None = Query(None),
    refresh: bool = Query(False),
    offset: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=10),
) -> ChangelogOut:
    app_state = request.app.state
    db_path: Path = app_state.settings.db_path
    checker = app_state.update_checker

    raw_channel = _get(db_path, "update.channel")
    own: Literal["main", "dev"] = raw_channel if raw_channel in ("main", "dev") else "main"
    view: Literal["main", "dev"] = channel or own
    enabled = _get(db_path, "update.check") != "off"

    result = checker.cached(view)
    if result is None and (enabled or refresh):
        result = checker.check(view)
    latest_ref: str | None = None
    if result and result.latest:
        latest_ref = result.latest.version if view == "main" else result.latest.commit

    installed = update_version.current_version()
    data = app_state.update_changelog.get(
        view,
        installed_version=installed.version,
        installed_commit=installed.commit,
        installed_known=not (installed.channel == "dev" and installed.commit is None),
        latest_ref=latest_ref,
        enabled=enabled,
        force=refresh,
        offset=offset,
        limit=limit,
    )
    return ChangelogOut.model_validate(data)


@router.put("/settings", dependencies=[Depends(write_guard)])
def put_settings(request: Request, body: SettingsIn) -> StatusOut:
    if body.channel is None and body.check_enabled is None:
        raise ApiError(422, "invalid", "at least one field required")

    app_state = request.app.state
    db_path: Path = app_state.settings.db_path
    root: Path = app_state.update_root

    if runner.supported(root):
        conf_kw: dict[str, str] = {}
        if body.channel is not None:
            conf_kw["channel"] = body.channel
        if body.check_enabled is not None:
            conf_kw["check"] = "on" if body.check_enabled else "off"
        runner.write_conf(root, **conf_kw)

    if body.channel is not None:
        _set(db_path, "update.channel", body.channel)
    if body.check_enabled is not None:
        _set(db_path, "update.check", "on" if body.check_enabled else "off")

    return _status(request, refresh=False, manual=False)


@router.post("/apply", status_code=202)
def apply_update(request: Request) -> ApplyOut:
    app_state = request.app.state
    db_path: Path = app_state.settings.db_path
    mode: str = app_state.settings.mode
    root: Path = app_state.update_root
    run = app_state.update_run
    checker = app_state.update_checker

    if not (mode == "real" and runner.supported(root)):
        raise ApiError(503, "unsupported", "update not supported here")

    status = runner.read_status(root)
    if status.get("state") == "running" or runner.is_running(run=run):
        raise ApiError(409, "already_running", "update already in progress")

    raw_channel = _get(db_path, "update.channel")
    channel: Literal["main", "dev"] = raw_channel if raw_channel in ("main", "dev") else "main"

    result = checker.cached(channel) or checker.check(channel)

    installed = update_version.current_version()
    available = False
    if result and result.latest:
        latest_ref = result.latest.version if channel == "main" else (result.latest.commit or "")
        installed_ref = installed.version if channel == "main" else (installed.commit or "")
        available = update_version.is_newer(latest_ref, installed_ref, channel)

    if not available:
        raise ApiError(409, "up_to_date", "no update available")

    if not runner.start_update(run=run):
        if runner.is_running(run=run):
            raise ApiError(409, "already_running", "update already in progress")
        raise ApiError(500, "start_failed", "could not start update process")

    return ApplyOut(state="running")
