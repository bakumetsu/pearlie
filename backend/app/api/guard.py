"""Shared request guards for API mutation protection."""

from __future__ import annotations

import ipaddress
import logging
from urllib.parse import urlparse

from fastapi import Request

from app.api.errors import ApiError

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

log = logging.getLogger(__name__)


def _effective_host(request: Request) -> str:
    # See origin_guard: behind a rewriting proxy the browser-facing host is in X-Forwarded-Host.
    forwarded = request.headers.get("x-forwarded-host")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.headers.get("host", "")


def host_allowed(host: str, extra: frozenset[str]) -> bool:
    """IP literals, localhost, *.ts.net and PEARLIE_ALLOWED_HOSTS names; any port."""
    try:
        name = urlparse(f"//{host}").hostname
    except ValueError:
        return False
    if not name:
        return False
    try:
        ipaddress.ip_address(name)
    except ValueError:
        pass
    else:
        return True
    return name == "localhost" or name.endswith(".ts.net") or name in extra


def host_guard(request: Request) -> None:
    """DNS rebinding defence: the Origin check alone passes when the attacker names the host."""
    host = _effective_host(request)
    if host_allowed(host, request.app.state.settings.allowed_host_set):
        return
    log.warning("rejected unlisted host %r (see PEARLIE_ALLOWED_HOSTS)", host[:100])
    raise ApiError(403, "forbidden", "host not allowed")


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
    if netloc != _effective_host(request):
        raise ApiError(403, "forbidden", "cross-site request refused")


def write_guard(request: Request) -> None:
    ct = request.headers.get("content-type", "")
    media_type = ct.split(";", 1)[0].strip().lower()
    if media_type != "application/json":
        raise ApiError(415, "unsupported_media_type", "Content-Type must be application/json")
    origin_guard(request)


def mutation_guard(request: Request) -> None:
    """App-wide dependency: Host check on every /api route, Origin check on mutating ones."""
    if not request.url.path.startswith("/api/"):
        return
    host_guard(request)
    if request.method in SAFE_METHODS:
        return
    origin_guard(request)
