"""Read-only debug endpoints behind the debug key (D-34).

GET only, no outbound call, no media. Every answer is an explicit allow-list model; free text
passes logs.scrub(). The key check lives in app.debug_key.DebugKeyGuard (ASGI middleware).
"""

from __future__ import annotations

import json
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from app import logs
from app.api import logs as logs_api
from app.api.errors import ApiError
from app.connections_store import NAMES, ConnectionStore
from app.db import SCHEMA_VERSION, connect, db_reachable
from app.update.version import current_version

router = APIRouter(prefix="/api/debug")

SCOPE = ["jobs", "logs", "state", "rules", "trash", "saved"]

# Closed list: output name -> settings key. Never add a key that can hold a secret or a path.
STATE_SETTINGS: dict[str, str] = {
    "logs.debug": "logs.debug",
    "images_per_site": "options.global.images_per_site",
    "thumbcache.max_mb": "thumbcache.max_mb",
    "stump.place_mode": "stump.place_mode",
    "rules.version": "rules.version",
    "player.autoplay": "player.autoplay",
}

_JOB_COLUMNS = (
    "id, source, post_id, status, error_code, error, target, title, attempts, restarts, "
    "started_at, finished_at, created_at, updated_at"
)
_QUEUE_STATES = ("queued", "running", "scan_wait", "verifying", "done", "failed", "needs_click")

Limit = Annotated[int, Query(ge=1, le=200)]


class Whoami(BaseModel):
    key_id: str
    expires_at: str
    scope: list[str]


class DebugJob(BaseModel):
    id: int
    source: str
    post_id: str
    status: str
    error_code: str | None
    error: str | None
    target: str
    title: str
    attempts: int
    restarts: int
    started_at: str | None
    finished_at: str | None
    created_at: str
    updated_at: str


class DebugJobDetail(DebugJob):
    notices: list[str]
    dest_path: str | None


class DebugJobList(BaseModel):
    jobs: list[DebugJob]
    limit: int
    offset: int


class DebugConnection(BaseModel):
    name: str
    address_host: str
    secret: str


class DebugState(BaseModel):
    version: str
    schema_version: int
    mode: str
    health: dict[str, str]
    connections: list[DebugConnection]
    settings: dict[str, str | None]
    queue_counts: dict[str, int]


class DebugRule(BaseModel):
    id: int
    list: str
    scope: str | None
    enabled: bool


class DebugRules(BaseModel):
    version: int
    counts: dict[str, int]
    rules: list[DebugRule]


class DebugTrashItem(BaseModel):
    group: str | None
    source: str | None
    post_id: str | None
    trashed_at: str
    purge_at: str


class DebugSavedItem(BaseModel):
    source: str
    post_id: str
    md5: str
    target: str
    created_at: str


def _scrub(text: str | None) -> str | None:
    return None if text is None else logs.scrub(text)


def _job(row) -> dict:
    data = {k: row[k] for k in row.keys()}
    data["error"] = _scrub(data["error"])
    data["title"] = logs.scrub(data["title"] or "")
    return data


def _notices(raw: str | None) -> list[str]:
    try:
        items = json.loads(raw or "[]")
    except ValueError:
        return []
    if not isinstance(items, list):
        return []
    return [logs.scrub(str(i)) for i in items[:50]]


def _host_only(address: str) -> str:
    """Scheme and host (and port) only: no path, query or credentials."""
    if not address:
        return ""
    try:
        parts = urlsplit(address)
        host = parts.hostname or ""
        port = f":{parts.port}" if parts.port else ""
    except ValueError:
        return "invalid-url"
    if not host:
        return "invalid-url"
    return f"{parts.scheme}://{host}{port}"


@router.get("/whoami")
def whoami(request: Request) -> Whoami:
    record = request.scope["debug_key"]
    return Whoami(key_id=record["id"], expires_at=record["expires_at"], scope=SCOPE)


@router.get("/jobs")
def list_jobs(
    request: Request,
    state: str | None = None,
    limit: Limit = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DebugJobList:
    sql = f"SELECT {_JOB_COLUMNS} FROM jobs"
    args: list[object] = []
    if state is not None:
        sql += " WHERE status = ?"
        args.append(state)
    sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
    args += [limit, offset]
    conn = connect(request.app.state.settings.db_path)
    try:
        rows = conn.execute(sql, args).fetchall()
    finally:
        conn.close()
    return DebugJobList(jobs=[DebugJob(**_job(r)) for r in rows], limit=limit, offset=offset)


@router.get("/jobs/{job_id}")
def get_job(request: Request, job_id: int) -> DebugJobDetail:
    conn = connect(request.app.state.settings.db_path)
    try:
        row = conn.execute(
            f"SELECT {_JOB_COLUMNS}, notices, dest_path FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise ApiError(404, "not_found", "No such job")
    data = _job(row)
    data["notices"] = _notices(row["notices"])
    data["dest_path"] = _scrub(row["dest_path"])
    return DebugJobDetail(**data)


@router.get("/logs")
def list_log_days() -> dict:
    return logs_api.list_logs()


@router.get("/logs/{date}")
def log_day(
    date: str,
    level: str = "info",
    limit: int = 200,
    cursor: str | None = None,
    q: str | None = None,
) -> dict:
    return logs_api.get_log_lines(date, level, limit, cursor, q)


@router.get("/state")
def state(request: Request) -> DebugState:
    app = request.app
    db_path = app.state.settings.db_path
    store: ConnectionStore | None = getattr(app.state, "connection_store", None)
    connections: list[DebugConnection] = []
    if store is not None:
        for name in NAMES:
            connections.append(
                DebugConnection(
                    name=name,
                    address_host=_host_only(store.address(name)),
                    secret=store.secret_state(name),
                )
            )
    conn = connect(db_path)
    try:
        settings: dict[str, str | None] = {}
        for out, key in STATE_SETTINGS.items():
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            settings[out] = None if row is None else str(row["value"])[:32]
        counts = {s: 0 for s in _QUEUE_STATES}
        for row in conn.execute("SELECT status, COUNT(*) AS n FROM jobs GROUP BY status"):
            counts[row["status"]] = row["n"]
    finally:
        conn.close()
    return DebugState(
        version=current_version().version,
        schema_version=SCHEMA_VERSION,
        mode=app.state.settings.mode,
        health={"db": "ok" if db_reachable(db_path) else "error"},
        connections=connections,
        settings=settings,
        queue_counts=counts,
    )


@router.get("/rules")
def rules(request: Request) -> DebugRules:
    conn = connect(request.app.state.settings.db_path)
    try:
        rows = conn.execute("SELECT id, list, scope, enabled FROM rules ORDER BY id").fetchall()
        row = conn.execute("SELECT value FROM settings WHERE key = 'rules.version'").fetchone()
    finally:
        conn.close()
    try:
        version = int(row["value"]) if row else 1
    except ValueError:
        version = 1
    counts: dict[str, int] = {}
    items: list[DebugRule] = []
    for r in rows:
        if r["enabled"]:
            counts[r["list"]] = counts.get(r["list"], 0) + 1
        items.append(
            DebugRule(id=r["id"], list=r["list"], scope=r["scope"], enabled=bool(r["enabled"]))
        )
    return DebugRules(version=version, counts=counts, rules=items)


@router.get("/trash")
def trash(request: Request, limit: Limit = 100) -> list[DebugTrashItem]:
    conn = connect(request.app.state.settings.db_path)
    try:
        rows = conn.execute(
            "SELECT group_id, source, post_id, trashed_at, expires_at FROM trash_items "
            "WHERE state = 'trashed' ORDER BY trashed_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    return [
        DebugTrashItem(
            group=r["group_id"],
            source=r["source"],
            post_id=r["post_id"],
            trashed_at=r["trashed_at"],
            purge_at=r["expires_at"],
        )
        for r in rows
    ]


@router.get("/saved")
def saved(
    request: Request,
    source: str | None = None,
    post_id: str | None = None,
    md5: str | None = None,
    limit: Limit = 50,
) -> list[DebugSavedItem]:
    where: list[str] = []
    args: list[object] = []
    for column, value in (("source", source), ("post_id", post_id), ("md5", md5)):
        if value is not None:
            where.append(f"{column} = ?")
            args.append(value)
    sql = "SELECT source, post_id, md5, target, created_at FROM saved_items"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    conn = connect(request.app.state.settings.db_path)
    try:
        rows = conn.execute(sql, args).fetchall()
    finally:
        conn.close()
    return [DebugSavedItem(**{k: r[k] for k in r.keys()}) for r in rows]
