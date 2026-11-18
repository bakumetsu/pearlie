"""Pick the book server for the running app."""

from __future__ import annotations

from typing import Any

from app.bookserver.base import BookServer, BookServerError
from app.bookserver.komga import KomgaBookServer
from app.bookserver.stump import StumpBookServer
from app.stump import Stump


def _stump_of(app: Any) -> StumpBookServer:
    """Stump adapter built from the settings; cached while the URL and key stay the same."""
    settings = app.state.settings
    url = settings.stump_url
    key = settings.stump_api_key.get_secret_value()
    if not url:
        raise BookServerError("not_configured", "Stump is not configured", 503)
    cached = getattr(app.state, "books", None)
    if isinstance(cached, StumpBookServer) and getattr(app.state, "stump_conn", None) == (url, key):
        return cached
    adapter = StumpBookServer(Stump(url, key), getattr(app.state, "thumb_cache", None))
    app.state.books = adapter
    app.state.stump_conn = (url, key)
    return adapter


def book_server_of(app: Any) -> BookServer:
    """Adapter for `settings.book_server`. Komga: around the current `app.state.komga`, cached
    per client object, so a swapped client (test injection, Options key change) gets a fresh
    adapter. Stump: see `_stump_of`."""
    if getattr(getattr(app.state, "settings", None), "book_server", "komga") == "stump":
        return _stump_of(app)
    client = app.state.komga
    if client is None:
        raise BookServerError("not_configured", "Komga is not configured", 503)
    cached: KomgaBookServer | None = getattr(app.state, "books", None)
    if not isinstance(cached, KomgaBookServer) or cached.client is not client:
        cached = KomgaBookServer(client)
        app.state.books = cached
    return cached
