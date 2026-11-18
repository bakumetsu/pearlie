"""Pick the book server for the running app."""

from __future__ import annotations

from typing import Any

from app.bookserver.base import BookServer, BookServerError
from app.bookserver.komga import KomgaBookServer


def book_server_of(app: Any) -> BookServer:
    """Adapter around the current `app.state.komga`; cached per client object, so a swapped
    client (test injection, Options key change) gets a fresh adapter."""
    client = app.state.komga
    if client is None:
        raise BookServerError("not_configured", "Komga is not configured", 503)
    cached: KomgaBookServer | None = getattr(app.state, "books", None)
    if cached is None or cached.client is not client:
        cached = KomgaBookServer(client)
        app.state.books = cached
    return cached
