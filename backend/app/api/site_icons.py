"""Site icons router: the favicon of each configured site, fetched and cached by the backend."""

from __future__ import annotations

import logging
import time
from typing import Literal

import httpx
from fastapi import APIRouter, Request, Response

from app.api.errors import ApiError
from app.db import connect

logger = logging.getLogger("pearlie")

router = APIRouter(prefix="/api")

MAX_ICON_BYTES = 65536
HIT_TTL_S = 30 * 86400
MISS_TTL_S = 86400
TYPES = {
    "image/png",
    "image/x-icon",
    "image/vnd.microsoft.icon",
    "image/gif",
    "image/jpeg",
    "image/webp",
}


def _fetch(
    base: str, client: httpx.Client | None
) -> tuple[int | None, tuple[bytes, str] | None]:
    """GET <base>/favicon.ico with no cookies or keys.

    Returns (HTTP status or None on a network error, the icon or None unless a small image).
    """
    http = client or httpx.Client(timeout=5.0, follow_redirects=False)
    try:
        with http.stream(
            "GET",
            base.rstrip("/") + "/favicon.ico",
            headers={"User-Agent": "Pearlie"},
        ) as resp:
            status = resp.status_code
            if status != 200:
                return status, None
            ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
            if ctype not in TYPES:
                return status, None
            data = bytearray()
            for chunk in resp.iter_bytes():
                data.extend(chunk)
                if len(data) > MAX_ICON_BYTES:
                    return status, None
            return status, ((bytes(data), ctype) if data else None)
    except httpx.HTTPError:
        return None, None
    finally:
        if client is None:
            http.close()


def _load(request: Request, site: str) -> tuple[bytes | None, str, float] | None:
    conn = connect(request.app.state.settings.db_path)
    try:
        row = conn.execute(
            "SELECT data, mime, fetched_at FROM site_icons WHERE site = ?", (site,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return row["data"], row["mime"], row["fetched_at"]


def _store(request: Request, site: str, data: bytes | None, mime: str) -> None:
    conn = connect(request.app.state.settings.db_path)
    try:
        conn.execute(
            "INSERT INTO site_icons (site, data, mime, fetched_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(site) DO UPDATE SET data = excluded.data, mime = excluded.mime, "
            "fetched_at = excluded.fetched_at",
            (site, data, mime, time.time()),
        )
        conn.commit()
    finally:
        conn.close()


def _icon(request: Request, site: str) -> tuple[bytes, str] | None:
    cached = _load(request, site)
    if cached is not None:
        data, mime, at = cached
        age = time.time() - at
        if data is not None and age < HIT_TTL_S:
            return data, mime
        if data is None and age < MISS_TTL_S:
            return None
    base = request.app.state.connection_store.address(site)
    if not base:
        return None
    throttle = request.app.state.throttles.get(site)
    if throttle is not None:
        throttle.wait()
    status, got = _fetch(base, getattr(request.app.state, "site_icon_client", None))
    if throttle is not None and status is not None:
        throttle.report(status)
    if got is None:
        if cached is not None and cached[0] is not None:
            return cached[0], cached[1]
        _store(request, site, None, "")
        return None
    _store(request, site, got[0], got[1])
    return got


@router.get("/site-icons/{site}", responses={200: {"content": {"image/*": {}}}, 404: {}})
def get_site_icon(
    request: Request, site: Literal["danbooru", "gelbooru", "rule34", "nhentai"]
) -> Response:
    # Fixture mode never reaches out; the UI shows the letter mark.
    if request.app.state.settings.mode == "fixture":
        raise ApiError(404, "not_found", "no icon")
    got = _icon(request, site)
    if got is None:
        raise ApiError(404, "not_found", "no icon")
    return Response(
        content=got[0],
        media_type=got[1],
        headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"},
    )
