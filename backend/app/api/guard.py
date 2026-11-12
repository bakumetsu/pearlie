"""Shared request guards for API mutation protection."""

from __future__ import annotations

from urllib.parse import urlparse

from fastapi import Request

from app.api.errors import ApiError

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def origin_guard(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin is None:
        origin = request.headers.get("referer")
    if origin is None:
        raise ApiError(403, "forbidden", "cross-site request refused")
    netloc = urlparse(origin).netloc
    # Behind a proxy that rewrites Host (nginx default, Vite changeOrigin) the
    # browser-facing host arrives in X-Forwarded-Host; a cross-site page cannot
    # set that header without a CORS preflight, which is never allowed.
    forwarded = request.headers.get("x-forwarded-host")
    if forwarded:
        host = forwarded.split(",", 1)[0].strip()
    else:
        host = request.headers.get("host", "")
    if netloc != host:
        raise ApiError(403, "forbidden", "cross-site request refused")


def write_guard(request: Request) -> None:
    ct = request.headers.get("content-type", "")
    media_type = ct.split(";", 1)[0].strip().lower()
    if media_type != "application/json":
        raise ApiError(415, "unsupported_media_type", "Content-Type must be application/json")
    origin_guard(request)


def mutation_guard(request: Request) -> None:
    """App-wide dependency: covers every mutating /api route, including later routers."""
    if request.method in SAFE_METHODS or not request.url.path.startswith("/api/"):
        return
    origin_guard(request)
