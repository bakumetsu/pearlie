"""Tabs API: global search tab list."""

from __future__ import annotations

import json
from typing import get_args

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.api.errors import ApiError
from app.db import connect
from app.models import ViewSource, WebSource

router = APIRouter(prefix="/api")

_SOURCES = {"web"} | set(get_args(ViewSource))
_SITES = set(get_args(WebSource))
_ORDERS = ("newest", "score")
_RATINGS = ("g", "s", "q", "e")


class Tab(BaseModel):
    id: str
    q: str
    src: str
    sites: list[str]
    order: str
    rating: list[str]


class TabList(BaseModel):
    tabs: list[Tab]
    active: str | None
    rev: int


class TabListBody(BaseModel):
    tabs: list[Tab]
    active: str | None
    rev: int


def _default() -> dict:
    return {"tabs": [], "active": None, "rev": 0}


def _parse(value: str) -> dict:
    try:
        data = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return _default()
    if not isinstance(data, dict):
        return _default()
    return data


def _stored(request: Request) -> dict:
    if request.app.state.settings.mode == "fixture":
        mem: dict | None = getattr(request.app.state, "tabs_mem", None)
        if mem is None:
            mem = _default()
            request.app.state.tabs_mem = mem
        return mem
    conn = connect(request.app.state.settings.db_path)
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = 'tabs'").fetchone()
    finally:
        conn.close()
    if row is None:
        return _default()
    return _parse(row["value"])


def _validate(tabs: list[Tab], active: str | None) -> None:
    if len(tabs) > 8:
        raise ApiError(422, "invalid", "at most 8 tabs", field="tabs")
    ids = [t.id for t in tabs]
    if len(ids) != len(set(ids)):
        raise ApiError(422, "invalid", "tab ids must be unique", field="tabs")
    if active is not None and active not in ids:
        raise ApiError(422, "invalid", "active must be None or one of the tab ids", field="active")
    for t in tabs:
        if not (1 <= len(t.id) <= 64):
            raise ApiError(422, "invalid", "tab id must be 1 to 64 characters", field="tabs")
        if len(t.q) > 500:
            raise ApiError(422, "invalid", "q must be at most 500 characters", field="q")
        if t.src not in _SOURCES:
            raise ApiError(422, "invalid", "src must be 'web' or a known source", field="tabs")
        for site in t.sites:
            if site not in _SITES:
                raise ApiError(422, "invalid", f"unknown site {site}", field="sites")
        if t.order not in _ORDERS:
            raise ApiError(422, "invalid", "order must be 'newest' or 'score'", field="order")
        if len(t.rating) != len(set(t.rating)):
            raise ApiError(422, "invalid", "rating values must not be duplicated", field="rating")
        for r in t.rating:
            if r not in _RATINGS:
                raise ApiError(422, "invalid", f"invalid rating value {r}", field="rating")


@router.get("/tabs", response_model=TabList)
def get_tabs(request: Request) -> TabList:
    data = _stored(request)
    return TabList(
        tabs=[Tab(**t) for t in data.get("tabs", [])],
        active=data.get("active"),
        rev=data.get("rev", 0),
    )


@router.put("/tabs", response_model=TabList)
def put_tabs(request: Request, body: TabListBody) -> TabList:
    _validate(body.tabs, body.active)
    if request.app.state.settings.mode == "fixture":
        mem: dict | None = getattr(request.app.state, "tabs_mem", None)
        if mem is None:
            mem = _default()
            request.app.state.tabs_mem = mem
        if body.rev != mem["rev"]:
            raise ApiError(409, "conflict", "Tabs changed on another device", rev=mem["rev"])
        new_rev = mem["rev"] + 1
        mem["tabs"] = [t.model_dump() for t in body.tabs]
        mem["active"] = body.active
        mem["rev"] = new_rev
        return TabList(tabs=body.tabs, active=body.active, rev=new_rev)
    conn = connect(request.app.state.settings.db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT value FROM settings WHERE key = 'tabs'").fetchone()
        stored = _parse(row["value"]) if row is not None else _default()
        if body.rev != stored["rev"]:
            raise ApiError(409, "conflict", "Tabs changed on another device", rev=stored["rev"])
        new_rev = stored["rev"] + 1
        result = {
            "tabs": [t.model_dump() for t in body.tabs],
            "active": body.active,
            "rev": new_rev,
        }
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            ("tabs", json.dumps(result)),
        )
        conn.commit()
    finally:
        conn.close()
    return TabList(tabs=body.tabs, active=body.active, rev=new_rev)
