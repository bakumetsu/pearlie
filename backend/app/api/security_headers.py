"""Response headers that keep relayed or served content from running script."""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# /api carries JSON and relayed media (an upstream SVG included): no script, no framing.
API_CSP = "default-src 'none'; sandbox; frame-ancestors 'none'"


class SecurityHeaders:
    """Adds nosniff and a sandbox CSP to every /api response, without buffering the body."""

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
                if is_api:
                    headers["Content-Security-Policy"] = API_CSP
            await send(message)

        await self.app(scope, receive, wrapped)
