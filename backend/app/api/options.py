"""Options router: per-profile and global display settings."""

from __future__ import annotations

import math
from typing import Literal

from fastapi import APIRouter, FastAPI, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator

from app.api.errors import ApiError
from app.db import connect
from app.fixtures.store import store
from app.sources.throttle import DEFAULT_PACE, Throttle

router = APIRouter(prefix="/api")

ALLOWED_RATES = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0)


class SitePace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: float
    default: float
    locked: bool
    backing_off: bool


class Options(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sfw: StrictBool = False
    sfw_set: StrictBool = False
    player_rate: float = 1.0
    player_rate_set: StrictBool = False
    profile: Literal["desktop", "touch"] = "desktop"

    backdrop_strength: StrictInt = Field(default=60, ge=0, le=100)
    backdrop_wall: StrictBool = True
    backdrop_item: StrictBool = True
    backdrop_lightbox: StrictBool = True
    allow_blurred_tags: StrictBool = False
    trash_retention_days: StrictInt = Field(default=7, ge=1, le=365)
    infinite_scroll: StrictBool = False
    source_pace: dict[str, SitePace] = {}
    hidden_sites: list[str] = []
    site_order: list[str] = []

    @field_validator("player_rate")
    @classmethod
    def _check_rate(cls, v: float) -> float:
        if v not in ALLOWED_RATES:
            raise ValueError(f"player_rate must be one of {ALLOWED_RATES}")
        return v


class OptionsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sfw: StrictBool | None = None
    player_rate: float | None = None
    backdrop_strength: StrictInt | None = Field(default=None, ge=0, le=100)
    backdrop_wall: StrictBool | None = None
    backdrop_item: StrictBool | None = None
    backdrop_lightbox: StrictBool | None = None
    allow_blurred_tags: StrictBool | None = None
    trash_retention_days: StrictInt | None = Field(default=None, ge=1, le=365)
    infinite_scroll: StrictBool | None = None
    source_pace: dict[str, float] | None = None
    hidden_sites: list[str] | None = None
    site_order: list[str] | None = None

    @field_validator("player_rate")
    @classmethod
    def _check_rate(cls, v: float | None) -> float | None:
        if v is not None and v not in ALLOWED_RATES:
            raise ValueError(f"player_rate must be one of {ALLOWED_RATES}")
        return v


def _detect_profile(request: Request) -> Literal["desktop", "touch"]:
    header = request.headers.get("X-Pearlie-Device", "")
    if header.lower() == "touch":
        return "touch"
    if header.lower() == "desktop":
        return "desktop"
    ua = request.headers.get("User-Agent", "")
    if any(kw in ua for kw in ("iPhone", "iPad", "Android", "Mobile")):
        return "touch"
    return "desktop"


def _num(raw: str | None, default: float) -> float:
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _read_mem(request: Request, key: str) -> str | None:
    mem: dict[str, str] | None = getattr(request.app.state, "options_mem", None)
    if mem is None:
        return None
    return mem.get(key)


def _write_mem(request: Request, key: str, value: str) -> None:
    mem: dict[str, str] | None = getattr(request.app.state, "options_mem", None)
    if mem is None:
        mem = {}
        request.app.state.options_mem = mem
    mem[key] = value


def _read_db(request: Request, key: str) -> str | None:
    conn = connect(request.app.state.settings.db_path)
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    finally:
        conn.close()
    return row["value"] if row is not None else None


def _write_db(request: Request, key: str, value: str) -> None:
    conn = connect(request.app.state.settings.db_path)
    try:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()
    finally:
        conn.close()


def _effective_pace(app: FastAPI, site: str) -> tuple[float, bool]:
    """Return (value, locked) for the given site's pace."""
    settings = app.state.settings
    locked = "download_interval_s" in settings.model_fields_set
    if locked:
        return max(float(settings.download_interval_s), DEFAULT_PACE[site]), True
    fixture = settings.mode == "fixture"
    key = f"options.global.pace.{site}"
    if fixture:
        mem: dict[str, str] | None = getattr(app.state, "options_mem", None)
        raw = mem.get(key) if mem else None
    else:
        conn = connect(settings.db_path)
        try:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        finally:
            conn.close()
        raw = row["value"] if row is not None else None
    if raw is not None:
        try:
            v = float(raw)
            if math.isfinite(v) and v >= DEFAULT_PACE[site]:
                return v, False
        except (ValueError, TypeError):
            pass
    return DEFAULT_PACE[site], False


def apply_pace(app: FastAPI) -> None:
    """Read stored/locked pace values and apply set_interval on every throttle."""
    throttles: dict[str, Throttle] = getattr(app.state, "throttles", {})
    for site in list(throttles):
        value, _ = _effective_pace(app, site)
        throttles[site].set_interval(value)


@router.get("/options", response_model=Options)
def get_options(request: Request) -> Options:
    profile = _detect_profile(request)
    fixture = request.app.state.settings.mode == "fixture"

    def read(key: str) -> str | None:
        if fixture:
            return _read_mem(request, key)
        return _read_db(request, key)

    # Profile values
    sfw_raw = read(f"options.{profile}.sfw")
    sfw_val: bool = sfw_raw == "1" if sfw_raw is not None else False
    sfw_set: bool = sfw_raw is not None

    pr_raw = read(f"options.{profile}.player_rate")
    rate: float = _num(pr_raw, 1.0)
    if rate not in ALLOWED_RATES:
        rate = 1.0
    rate_set: bool = pr_raw is not None

    # Global values
    bs_raw = read("options.global.backdrop_strength")
    backdrop_strength: int = min(100, max(0, int(_num(bs_raw, 60))))

    bw_raw = read("options.global.backdrop_wall")
    backdrop_wall: bool = bw_raw == "1" if bw_raw is not None else True

    bi_raw = read("options.global.backdrop_item")
    backdrop_item: bool = bi_raw == "1" if bi_raw is not None else True

    bl_raw = read("options.global.backdrop_lightbox")
    backdrop_lightbox: bool = bl_raw == "1" if bl_raw is not None else True

    abt_raw = read("options.global.allow_blurred_tags")
    allow_blurred_tags: bool = abt_raw == "1" if abt_raw is not None else False

    trd_raw = read("options.global.trash_retention_days")
    trash_retention_days: int = min(365, max(1, int(_num(trd_raw, 7))))

    is_raw = read("options.global.infinite_scroll")
    infinite_scroll: bool = is_raw == "1"

    # Source pace
    source_pace: dict[str, SitePace] = {}
    throttles: dict[str, Throttle] = getattr(request.app.state, "throttles", {})
    for site in DEFAULT_PACE:
        val, locked = _effective_pace(request.app, site)
        throttle = throttles.get(site)
        backing = throttle.backing_off if throttle is not None else False
        source_pace[site] = SitePace(
            value=val,
            default=DEFAULT_PACE[site],
            locked=locked,
            backing_off=backing,
        )

    hs_raw = read("options.global.hidden_sites")
    hidden_sites = [s for s in DEFAULT_PACE if s in (hs_raw or "").split(",")]

    so_raw = (read("options.global.site_order") or "").split(",")
    site_order = list(dict.fromkeys(s for s in so_raw if s in DEFAULT_PACE))
    site_order += [s for s in DEFAULT_PACE if s not in site_order]

    return Options(
        sfw=sfw_val,
        sfw_set=sfw_set,
        player_rate=rate,
        player_rate_set=rate_set,
        profile=profile,
        backdrop_strength=backdrop_strength,
        backdrop_wall=backdrop_wall,
        backdrop_item=backdrop_item,
        backdrop_lightbox=backdrop_lightbox,
        allow_blurred_tags=allow_blurred_tags,
        trash_retention_days=trash_retention_days,
        infinite_scroll=infinite_scroll,
        source_pace=source_pace,
        hidden_sites=hidden_sites,
        site_order=site_order,
    )


@router.put("/options", response_model=Options)
def put_options(request: Request, body: OptionsUpdate) -> Options:
    profile = _detect_profile(request)
    fixture = request.app.state.settings.mode == "fixture"

    def write(key: str, value: str) -> None:
        if fixture:
            _write_mem(request, key, value)
        else:
            _write_db(request, key, value)

    if body.sfw is not None:
        write(f"options.{profile}.sfw", "1" if body.sfw else "0")

    if body.player_rate is not None:
        write(f"options.{profile}.player_rate", str(body.player_rate))

    if body.backdrop_strength is not None:
        write("options.global.backdrop_strength", str(body.backdrop_strength))
    if body.backdrop_wall is not None:
        write("options.global.backdrop_wall", "1" if body.backdrop_wall else "0")
    if body.backdrop_item is not None:
        write("options.global.backdrop_item", "1" if body.backdrop_item else "0")
    if body.backdrop_lightbox is not None:
        write("options.global.backdrop_lightbox", "1" if body.backdrop_lightbox else "0")
    if body.allow_blurred_tags is not None:
        write("options.global.allow_blurred_tags", "1" if body.allow_blurred_tags else "0")
    if body.infinite_scroll is not None:
        write("options.global.infinite_scroll", "1" if body.infinite_scroll else "0")
    if body.trash_retention_days is not None:
        write("options.global.trash_retention_days", str(body.trash_retention_days))
        if fixture:
            store.set_retention(body.trash_retention_days)

    if body.hidden_sites is not None:
        for site in body.hidden_sites:
            if site not in DEFAULT_PACE:
                raise ApiError(422, "invalid", f"unknown site: {site}", field="hidden_sites")
        if set(DEFAULT_PACE) <= set(body.hidden_sites):
            raise ApiError(422, "invalid", "keep at least one site visible", field="hidden_sites")
        write("options.global.hidden_sites", ",".join(sorted(set(body.hidden_sites))))

    if body.site_order is not None:
        for site in body.site_order:
            if site not in DEFAULT_PACE:
                raise ApiError(422, "invalid", f"unknown site: {site}", field="site_order")
        write("options.global.site_order", ",".join(dict.fromkeys(body.site_order)))

    if body.source_pace is not None:
        settings = request.app.state.settings
        locked = "download_interval_s" in settings.model_fields_set
        if locked:
            raise ApiError(422, "invalid", "source_pace is set in .env", field="source_pace")
        for site, value in body.source_pace.items():
            if site not in DEFAULT_PACE:
                raise ApiError(422, "invalid", f"unknown site: {site}", field="source_pace")
            if not math.isfinite(value) or value > 3600:
                raise ApiError(422, "invalid", f"invalid value for {site}", field="source_pace")
            if value < DEFAULT_PACE[site]:
                raise ApiError(422, "invalid", f"invalid value for {site}", field="source_pace")
        # All valid – write and apply
        throttles: dict[str, Throttle] = getattr(request.app.state, "throttles", {})
        for site, value in body.source_pace.items():
            write(f"options.global.pace.{site}", str(value))
            if site in throttles:
                throttles[site].set_interval(value)

    return get_options(request)
