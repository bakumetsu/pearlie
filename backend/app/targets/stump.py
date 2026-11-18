"""Stump save target: gallery pages into a CBZ in a Stump library folder.

The file work is the Komga target's (`KomgaTarget`); this class swaps the settings, the
`saved_items.target` value and the book server, and finds a saved book with `mediaByPath`.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path

import httpx

from app.bookserver.stump import StumpBookServer
from app.config import Settings
from app.sources.base import Source
from app.sources.throttle import Throttle
from app.stump import Stump
from app.targets.komga import KomgaTarget
from app.targets.stash import PendingScan, SaveError

logger = logging.getLogger("pearlie.stump")


class StumpTarget(KomgaTarget):
    """Stump save target (nhentai galleries)."""

    target = "stump"
    label = "Stump"

    def __init__(
        self,
        settings: Settings,
        client: Stump | None,
        http: httpx.Client,
        sources: dict[str, Source],
        throttles: dict[str, Throttle] | None = None,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        super().__init__(settings, None, http, sources, throttles, clock, sleep)
        self._stump = client
        self._stump_books: StumpBookServer | None = None

    def set_client(self, client: Stump | None) -> None:  # type: ignore[override]
        self._stump = client

    @property
    def _books(self) -> StumpBookServer:  # type: ignore[override]
        client = self._stump
        if client is None:
            raise SaveError("not_configured", "Stump is not configured", 503)
        cached = self._stump_books
        if cached is None or cached.client is not client:
            cached = self._stump_books = StumpBookServer(client)
        return cached

    def _incoming(self) -> str:
        return self._settings.stump_incoming_dir

    def _temp_dir(self) -> Path:
        return self._settings.stump_temp_dir

    def _prefixes(self) -> tuple[str, str]:
        s = self._settings
        return s.stump_path_prefix_pearlie, s.stump_path_prefix_stump

    def find_books(self, library_id: str, books: dict[str, PendingScan]) -> set[str]:
        """Job ids whose book Stump lists now: one exact `mediaByPath` call per book.

        A path that is not known yet is a miss. Raises BookServerError.
        """
        found: set[str] = set()
        for job_id, pending in books.items():
            hit = self._books.find_by_path("books", library_id, pending.komga_path, "")
            if hit is None:
                continue
            found.add(job_id)
            self._record_book(pending, hit.id)
        return found
