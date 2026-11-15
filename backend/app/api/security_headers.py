"""Response headers that keep relayed or served content from running script."""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# /api carries JSON and relayed media (an upstream SVG included): no script, no framing.
API_CSP = "default-src 'none'; sandbox; frame-ancestors 'none'"
# The Svelte build: one module script and linked CSS from this origin. Svelte writes
# style attributes, so style-src keeps 'unsafe-inline'; scripts stay strict.
APP_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; media-src 'self' blob:; font-src 'self' data:; "
    "connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; "
    "frame-ancestors 'none'"
)
# Vite names built files by content hash, so they never change under one URL.
ASSET_CACHE = "public, max-age=31536000, immutable"


class SecurityHeaders:
    """Adds security headers to every response, without buffering the body."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path: str = scope["path"]
        is_api = path.startswith("/api/")

        async def wrapped(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                headers["Referrer-Policy"] = "no-referrer"
                headers["Content-Security-Policy"] = API_CSP if is_api else APP_CSP
                if not is_api and "cache-control" not in headers:
                    # index.html must be revalidated so a new build is picked up.
                    headers["Cache-Control"] = (
                        ASSET_CACHE if path.startswith("/assets/") else "no-cache"
                    )
            await send(message)

        await self.app(scope, receive, wrapped)
