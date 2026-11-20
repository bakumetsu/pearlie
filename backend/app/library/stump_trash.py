"""Stump side of the trash: the file move stays Pearlie's; Stump shows the item `MISSING`.

A debounced scan makes Stump mark the moved item `MISSING`, `cleanLibrary` runs only when every
MISSING item is one Pearlie trashed, and a restore scans, finds the item (same id or a new id at
the path), remaps the id and writes tags, metadata and read progress back.
"""

from __future__ import annotations

import json
import logging
import os
import posixpath
import threading
import time
from collections.abc import Callable
from pathlib import Path

from app.bookserver.base import BookDTO, BookServer, BookServerError, Kind, MetadataPatch, SeriesDTO
from app.bookserver.map import book_item, series_item
from app.bookserver.stump import StumpBookServer
from app.config import Settings
from app.db import connect
from app.library.trash import TrashError, TrashSpec, TrashStore
from app.models import LibraryItem
from app.stump import Stump
from app.targets import destinations

logger = logging.getLogger("pearlie")

KIND_OF = {"books": "book", "series": "series"}
PLURAL_OF: dict[str, Kind] = {"book": "books", "series": "series"}
SETTLE_TIMEOUT_S = 120.0
SETTLE_POLL_S = 2.0
RESTORE_TIMEOUT_S = 60.0


class StumpTrash:
    label = "Stump"  # the book server named in messages

    def __init__(
        self,
        settings: Settings,
        store: TrashStore,
        client: Stump | BookServer,
        wait_s: Callable[[], float] = lambda: 10.0,
        settle_timeout_s: float = SETTLE_TIMEOUT_S,
        poll_s: float = SETTLE_POLL_S,
        restore_timeout_s: float = RESTORE_TIMEOUT_S,
    ) -> None:
        self._s = settings
        self._store = store
        self._c: BookServer = client if hasattr(client, "kind") else StumpBookServer(client)  # type: ignore[arg-type]
        self._wait_s = wait_s
        self._settle_timeout_s = settle_timeout_s
        self._poll_s = poll_s
        self._restore_timeout_s = restore_timeout_s
        self._lock = threading.Lock()
        self._pending: dict[str, set[tuple[str, str]]] = {}
        self._timers: dict[str, threading.Timer] = {}

    # -- paths ----------------------------------------------------------------

    def _to_local(self, server_path: str) -> Path:
        s = self._s
        p = destinations.to_pearlie_path(
            server_path.replace("\\", "/"), s.stump_path_prefix_pearlie, s.stump_path_prefix_stump
        )
        return Path(p)

    def _to_server(self, local: Path) -> str:
        s = self._s
        return destinations.to_stash_path(
            local.as_posix(), s.stump_path_prefix_pearlie, s.stump_path_prefix_stump
        )

    def _roots(self) -> list[str]:
        return [os.path.realpath(self._to_local(lib.root)) for lib in self._c.list_libraries()]

    def _check_under_library(self, local: Path) -> None:
        real = os.path.realpath(local)
        trash = os.path.realpath(self._store.dir)
        roots = self._roots()
        for root in roots:
            if trash == root or trash.startswith(root + os.sep):
                raise TrashError(503, "trash_unavailable", "Trash folder is inside a library")
        if real in roots or not any(real.startswith(r + os.sep) for r in roots):
            raise TrashError(422, "path_outside_library", "Item is outside the library")

    # -- delete ---------------------------------------------------------------

    def delete(self, plural: str, id: str, group_id: str | None = None) -> dict:
        kind = KIND_OF[plural]
        self._store.check_dir()
        try:
            dto = self._c.get_book(id) if kind == "book" else self._c.get_series(id)
        except BookServerError as e:
            raise TrashError(e.status, e.code, e.message) from None
        if dto.deleted:
            raise TrashError(404, "not_found", "Item not found")
        if self._store.active_for_entity(self._c.kind, id):
            raise TrashError(409, "already_trashed", "Item is already in the trash")
        try:
            local = self._to_local(dto.path)
            self._check_under_library(local)
            meta = self._meta(kind, dto)
        except BookServerError as e:
            raise TrashError(e.status, e.code, e.message) from None
        library_id = dto.library_id
        meta["library_id"] = library_id
        source, post_id = self._saved_row(id) if kind == "book" else (None, None)
        spec = TrashSpec(
            target=self._c.kind,
            kind=kind,
            entity_id=id,
            title=dto.title or dto.name or local.name,
            orig_path=local,
            meta=meta,
            source=source,
            post_id=post_id,
            group_id=group_id,
        )

        def forget() -> None:
            # the server is checked reachable; the scan itself runs debounced.
            self._c.list_libraries()
            self._drop_walks()
            if meta.get("series_gone_id"):
                self._remove_empty_series_dir(local.parent, self._series_local(dto))
            self._queue(library_id, kind, id)

        try:
            return self._store.delete(spec, forget)
        except BookServerError:
            raise TrashError(
                502, "upstream_error", f"{self.label} did not accept the delete"
            ) from None

    def _drop_walks(self) -> None:
        """The series and deleted-items walks of the book server are stale after a move."""
        drop = getattr(self._c, "invalidate_walks", None)
        if drop is not None:
            drop()

    def _series_local(self, dto: BookDTO | SeriesDTO) -> Path | None:
        """The local folder of the book's series, or None when it cannot be told."""
        if not isinstance(dto, BookDTO):
            return None
        try:
            return self._to_local(self._c.get_series(dto.series_id).path)
        except BookServerError:
            return None

    def _remove_empty_series_dir(self, folder: Path, series_dir: Path | None) -> None:
        """The last book left: drop the series folder so the scan drops the series.

        Only the series folder itself, only when truly empty (rmdir, no recursion), never a
        library root or a folder above it.
        """
        if series_dir is None or os.path.realpath(folder) != os.path.realpath(series_dir):
            return
        try:
            real = os.path.realpath(folder)
            roots = self._roots()
            if real in roots or not any(real.startswith(r + os.sep) for r in roots):
                return
            os.rmdir(folder)
        except (OSError, BookServerError) as e:
            logger.info("trash stump series folder kept: %s", type(e).__name__)

    def _meta(self, kind: str, dto: BookDTO | SeriesDTO) -> dict:
        meta: dict = {
            "title": dto.title,
            "summary": dto.summary,
            "tags": sorted(dto.tags),
            "server_path": dto.path,
        }
        if isinstance(dto, BookDTO):
            if dto.read_page is not None:
                meta["progress"] = {"page": dto.read_page, "completed": dto.read_done}
            meta["series_id"] = dto.series_id
            if self._c.get_series(dto.series_id).book_count <= 1:
                meta["series_gone_id"] = dto.series_id
        else:
            books, _ = self._c.series_books(dto.id)
            meta["book_ids"] = [b.id for b in books]
        return meta

    def _saved_row(self, book_id: str) -> tuple[str | None, str | None]:
        conn = connect(self._s.db_path)
        try:
            r = conn.execute(
                "SELECT source, post_id FROM saved_items WHERE target = ? AND library_id = ?",
                (self._c.kind, book_id),
            ).fetchone()
        finally:
            conn.close()
        return (r["source"], r["post_id"]) if r else (None, None)

    def destroy_row(self, row: dict) -> None:
        """Start-up repair: queue the scan so Stump drops the entry."""
        meta = _loads(row.get("meta"))
        if meta.get("library_id"):
            self._queue(str(meta["library_id"]), row["kind"], row["entity_id"])

    # -- debounced scan, then empty-trash -------------------------------------

    def _queue(self, library_id: str, kind: str, id: str) -> None:
        with self._lock:
            self._pending.setdefault(library_id, set()).add((kind, id))
            old = self._timers.pop(library_id, None)
            if old is not None:
                old.cancel()
            timer = threading.Timer(max(0.0, self._wait_s()), self._run, args=(library_id,))
            timer.daemon = True
            self._timers[library_id] = timer
            timer.start()

    def cancel(self, library_id: str, id: str) -> None:
        """Forget a pending item (it is being restored)."""
        with self._lock:
            items = self._pending.get(library_id, set())
            items.difference_update({(k, i) for k, i in items if i == id})

    def _run(self, library_id: str) -> None:
        with self._lock:
            self._timers.pop(library_id, None)
            items = self._pending.pop(library_id, set())
        if not items:
            return
        logger.info("trash stump scan requested: %d items", len(items))
        try:
            self._c.scan_library(library_id)
        except BookServerError as e:
            logger.warning("trash stump scan failed code=%s: items stay hidden", e.code)
            return
        self._settle(items)
        self._drop_walks()  # a walk taken before the scan still lists the items
        self.empty_if_ours(library_id)

    def _settled(self, kind: str, id: str) -> bool:
        try:
            dto = self._c.get_book(id) if kind == "book" else self._c.get_series(id)
        except BookServerError as e:
            return e.status == 404
        return dto.deleted

    def _settle(self, items: set[tuple[str, str]]) -> None:
        deadline = time.monotonic() + self._settle_timeout_s
        todo = set(items)
        while todo:
            todo = {(k, i) for k, i in todo if not self._settled(k, i)}
            if not todo or time.monotonic() >= deadline:
                return
            time.sleep(self._poll_s)

    def foreign_deleted(self, library_id: str) -> int:
        """How many soft-deleted Stump items of the library Pearlie did not trash."""
        owned = self._store.stump_owned_ids()
        foreign = 0
        for plural in ("books", "series"):
            foreign += sum(1 for d in self._c.list_deleted(plural, library_id) if d.id not in owned)
        return foreign

    def empty_if_ours(self, library_id: str) -> bool:
        """Call empty-trash when at most `stump_clean_max_foreign` soft-deleted items are foreign."""
        try:
            foreign = self.foreign_deleted(library_id)  # checked right before the call
            limit = self._s.stump_clean_max_foreign
            if foreign > limit:
                logger.warning(
                    "trash stump empty-trash skipped: %d foreign soft-deleted items (limit %d)",
                    foreign,
                    limit,
                )
                return False
            if foreign:
                logger.info("trash stump empty-trash: %d foreign soft-deleted items", foreign)
            self._c.purge_deleted(library_id)
        except BookServerError as e:
            logger.warning("trash stump empty-trash failed code=%s: items stay hidden", e.code)
            return False
        return True

    # -- restore --------------------------------------------------------------

    def restore(self, token: str) -> LibraryItem:
        row = self._store.get(token)
        if row is not None:
            lib = _loads(row.get("meta")).get("library_id")
            if lib:
                self.cancel(str(lib), row["entity_id"])
        try:
            return self._store.restore(token, self._apply)
        finally:
            self._drop_walks()

    def _apply(self, row: dict, new_path: Path) -> tuple[str, LibraryItem]:
        meta = _loads(row["meta"])
        kind = row["kind"]
        plural = PLURAL_OF[kind]
        server_path = self._to_server(new_path)
        library_id = self._library_for(str(meta.get("library_id") or ""), server_path)
        self._c.scan_library(library_id)
        dto = self._wait_found(plural, row["entity_id"], library_id, server_path, new_path.name)
        new_id = dto.id
        patch = self._metadata_patch(meta, dto)
        if patch is not None:
            self._c.set_metadata(plural, new_id, patch)
        progress = meta.get("progress")
        if kind == "book" and progress and progress.get("page"):
            self._c.set_progress(new_id, int(progress["page"]), bool(progress.get("completed")))
        if kind == "book":
            book = self._c.get_book(new_id)
            item = book_item(book)
        else:
            item = series_item(self._c.get_series(new_id))
        self._relink_saved(row["entity_id"], new_id)
        return new_id, item

    def _library_for(self, library_id: str, server_path: str) -> str:
        """The saved library id, or for a row from the Komga era the library that holds the path."""
        libs = self._c.list_libraries()
        if any(lib.id == library_id for lib in libs):
            return library_id
        want = posixpath.normpath(server_path.replace("\\", "/"))
        for lib in libs:
            root = posixpath.normpath(lib.root.replace("\\", "/"))
            if want == root or want.startswith(root.rstrip("/") + "/"):
                return lib.id
        raise RuntimeError("library not found")

    @staticmethod
    def _metadata_patch(meta: dict, dto: BookDTO | SeriesDTO) -> MetadataPatch | None:
        """Tags, title and summary saved at delete time; only fields the scan lost."""
        tags = list(meta["tags"]) if meta.get("tags") else None
        title, summary = meta.get("title"), meta.get("summary")
        title = title if title and title != dto.title else None
        summary = summary if summary and summary != dto.summary else None
        if tags is None and title is None and summary is None:
            return None
        return MetadataPatch(tags=tags, title=title, summary=summary)

    def _wait_found(
        self, plural: Kind, old_id: str, library_id: str, server_path: str, name: str
    ) -> BookDTO | SeriesDTO:
        """The restored item: the same id revived by the scan, or a new id at the path."""
        deadline = time.monotonic() + self._restore_timeout_s
        want = posixpath.normpath(server_path)
        while True:
            try:
                dto = self._c.get_book(old_id) if plural == "books" else self._c.get_series(old_id)
                if not dto.deleted and posixpath.normpath(dto.path.replace("\\", "/")) == want:
                    return dto
            except BookServerError as e:
                if e.status != 404:
                    raise
            found = self._c.find_by_path(
                plural, library_id, server_path, posixpath.splitext(name)[0]
            )
            if found is not None:
                return found
            if time.monotonic() >= deadline:
                raise RuntimeError("not indexed")
            time.sleep(self._poll_s)

    def _relink_saved(self, old_id: str, new_id: str) -> None:
        conn = connect(self._s.db_path)
        try:
            conn.execute(
                "UPDATE saved_items SET library_id = ? WHERE target = ? AND library_id = ?",
                (new_id, self._c.kind, old_id),
            )
            conn.commit()
        finally:
            conn.close()


def _loads(raw: str | None) -> dict:
    try:
        data = json.loads(raw or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}
