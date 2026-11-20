"""Shared request guards for API mutation protection."""

from __future__ import annotations

import ipaddress
import logging
from html import escape
from urllib.parse import urlparse

from fastapi import Request
from starlette.datastructures import Headers
from starlette.responses import HTMLResponse, JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

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


def _hint_name(host: str) -> str:
    """Bare host name for the error hint; only plain name characters are echoed back."""
    try:
        name = urlparse(f"//{host}").hostname or ""
    except ValueError:
        name = ""
    name = name[:100]
    if not name or not all(c.isalnum() or c in ".-_" for c in name):
        return "this host"
    return name


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
    """App-wide dependency: Origin check on mutating /api routes (Host is checked by HostGuard)."""
    if not request.url.path.startswith("/api/"):
        return
    if request.method in SAFE_METHODS:
        return
    origin_guard(request)


_WARNED_CAP = 256


def _error_page(host: str) -> str:
    name = escape(host[:100])
    return (
        "<!doctype html><html lang=en><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        "<title>Host not allowed</title>"
        "<body style='font-family:system-ui,sans-serif;max-width:36rem;"
        "margin:3rem auto;padding:0 1rem'>"
        "<h1>Host not allowed</h1>"
        f"<p>Pearlie refused this request because the host <code>{name}</code> is not allowed.</p>"
        "<p>Add the name to <code>PEARLIE_ALLOWED_HOSTS</code> in the <code>.env</code> file "
        "(comma list, for example <code>PEARLIE_ALLOWED_HOSTS=pearlie.home</code>) "
        "and restart Pearlie.</p></body></html>"
    )


class HostGuard:
    """DNS rebinding defence on every HTTP request: API, web UI, static files and SPA routes.

    The Origin check alone passes when the attacker names the host. /api gets the JSON 403;
    any other path gets a short HTML page. One WARNING per rejected host, not per request.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._warned: set[str] = set()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        forwarded = headers.get("x-forwarded-host")
        host = forwarded.split(",", 1)[0].strip() if forwarded else headers.get("host", "")
        extra: frozenset[str] = scope["app"].state.settings.allowed_host_set
        if host_allowed(host, extra):
            await self.app(scope, receive, send)
            return
        if host not in self._warned and len(self._warned) < _WARNED_CAP:
            self._warned.add(host)
            log.warning("rejected unlisted host %r (see PEARLIE_ALLOWED_HOSTS)", host[:100])
        if scope["path"].startswith("/api/"):
            hint = f"host not allowed: add {_hint_name(host)} to PEARLIE_ALLOWED_HOSTS"
            response = JSONResponse({"code": "host_not_allowed", "message": hint}, status_code=403)
        else:
            response = HTMLResponse(_error_page(host), status_code=403)
        await response(scope, receive, send)
