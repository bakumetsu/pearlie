"""Komga side of the trash: move the file or folder, let Komga forget it, restore."""

from __future__ import annotations

import json
import logging
import os
import posixpath
import threading
import time
from collections.abc import Callable
from pathlib import Path

from app.config import Settings
from app.db import connect
from app.komga import Komga, KomgaError, book_item, series_item
from app.library.trash import TrashError, TrashSpec, TrashStore
from app.models import LibraryItem
from app.targets import destinations

logger = logging.getLogger("pearlie")

KIND_OF = {"books": "book", "series": "series"}
PLURAL_OF = {"book": "books", "series": "series"}
SETTLE_TIMEOUT_S = 120.0
SETTLE_POLL_S = 2.0
RESTORE_TIMEOUT_S = 60.0


class KomgaTrash:
    def __init__(
        self,
        settings: Settings,
        store: TrashStore,
        client: Komga,
        wait_s: Callable[[], float] = lambda: 10.0,
        settle_timeout_s: float = SETTLE_TIMEOUT_S,
        poll_s: float = SETTLE_POLL_S,
        restore_timeout_s: float = RESTORE_TIMEOUT_S,
    ) -> None:
        self._s = settings
        self._store = store
        self._c = client
        self._wait_s = wait_s
        self._settle_timeout_s = settle_timeout_s
        self._poll_s = poll_s
        self._restore_timeout_s = restore_timeout_s
        self._lock = threading.Lock()
        self._pending: dict[str, set[tuple[str, str]]] = {}
        self._timers: dict[str, threading.Timer] = {}

    # -- paths ----------------------------------------------------------------

    def _to_local(self, komga_path: str) -> Path:
        s = self._s
        p = destinations.to_pearlie_path(
            komga_path.replace("\\", "/"), s.komga_path_prefix_pearlie, s.komga_path_prefix_komga
        )
        return Path(p)

    def _to_komga(self, local: Path) -> str:
        s = self._s
        return destinations.to_stash_path(
            local.as_posix(), s.komga_path_prefix_pearlie, s.komga_path_prefix_komga
        )

    def _roots(self) -> list[str]:
        return [
            os.path.realpath(self._to_local(str(lib.get("root", ""))))
            for lib in self._c.list_libraries()
        ]

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
        except KomgaError as e:
            raise TrashError(e.status, e.code, e.message) from None
        if dto.get("deleted"):
            raise TrashError(404, "not_found", "Item not found")
        if self._store.active_for_entity("komga", id):
            raise TrashError(409, "already_trashed", "Item is already in the trash")
        try:
            local = self._to_local(str(dto.get("url", "")))
            self._check_under_library(local)
            meta = self._meta(kind, dto)
        except KomgaError as e:
            raise TrashError(e.status, e.code, e.message) from None
        library_id = str(dto["libraryId"])
        meta["library_id"] = library_id
        source, post_id = self._saved_row(id) if kind == "book" else (None, None)
        md = dto.get("metadata") or {}
        spec = TrashSpec(
            target="komga",
            kind=kind,
            entity_id=id,
            title=md.get("title") or dto.get("name") or local.name,
            orig_path=local,
            meta=meta,
            source=source,
            post_id=post_id,
            group_id=group_id,
        )

        def forget() -> None:
            # Komga is checked reachable; the scan itself runs debounced.
            self._c.list_libraries()
            self._queue(library_id, kind, id)

        try:
            return self._store.delete(spec, forget)
        except KomgaError:
            raise TrashError(502, "upstream_error", "Komga did not accept the delete") from None

    def _meta(self, kind: str, dto: dict) -> dict:
        md = dto.get("metadata") or {}
        meta: dict = {
            "title": md.get("title"),
            "summary": md.get("summary"),
            "tags": sorted(md.get("tags") or []),
            "komga_path": dto.get("url"),
        }
        if kind == "book":
            rp = dto.get("readProgress")
            if rp:
                meta["progress"] = {"page": rp.get("page"), "completed": bool(rp.get("completed"))}
            meta["series_id"] = dto.get("seriesId")
            meta["series_title"] = dto.get("seriesTitle")
            series = self._c.get_series(str(dto["seriesId"]))
            if int(series.get("booksCount", 0)) <= 1:
                meta["series_gone_id"] = dto["seriesId"]
        else:
            books, _ = self._c.all_series_books(str(dto["id"]))
            meta["book_ids"] = [b["id"] for b in books]
        return meta

    def _saved_row(self, book_id: str) -> tuple[str | None, str | None]:
        conn = connect(self._s.db_path)
        try:
            r = conn.execute(
                "SELECT source, post_id FROM saved_items WHERE target = 'komga' AND library_id = ?",
                (book_id,),
            ).fetchone()
        finally:
            conn.close()
        return (r["source"], r["post_id"]) if r else (None, None)

    def destroy_row(self, row: dict) -> None:
        """Start-up repair: queue the scan so Komga drops the entry."""
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
        try:
            self._c.scan_library(library_id)
        except KomgaError as e:
            logger.warning("trash komga scan failed code=%s: items stay hidden", e.code)
            return
        self._settle(items)
        self.empty_if_ours(library_id)

    def _settled(self, kind: str, id: str) -> bool:
        try:
            dto = self._c.get_book(id) if kind == "book" else self._c.get_series(id)
        except KomgaError as e:
            return e.status == 404
        return bool(dto.get("deleted"))

    def _settle(self, items: set[tuple[str, str]]) -> None:
        deadline = time.monotonic() + self._settle_timeout_s
        todo = set(items)
        while todo:
            todo = {(k, i) for k, i in todo if not self._settled(k, i)}
            if not todo or time.monotonic() >= deadline:
                return
            time.sleep(self._poll_s)

    def foreign_deleted(self, library_id: str) -> int:
        """How many soft-deleted Komga items of the library Pearlie did not trash."""
        owned = self._store.komga_owned_ids()
        foreign = 0
        for plural in ("books", "series"):
            foreign += sum(
                1 for d in self._c.list_deleted(plural, library_id) if str(d.get("id")) not in owned
            )
        return foreign

    def empty_if_ours(self, library_id: str) -> bool:
        """Call empty-trash only when every soft-deleted item is one Pearlie trashed."""
        try:
            foreign = self.foreign_deleted(library_id)  # checked right before the call
            if foreign:
                logger.warning(
                    "trash komga empty-trash skipped: %d foreign soft-deleted items", foreign
                )
                return False
            self._c.empty_trash(library_id)
        except KomgaError as e:
            logger.warning("trash komga empty-trash failed code=%s: items stay hidden", e.code)
            return False
        return True

    # -- restore --------------------------------------------------------------

    def restore(self, token: str) -> LibraryItem:
        row = self._store.get(token)
        if row is not None:
            lib = _loads(row.get("meta")).get("library_id")
            if lib:
                self.cancel(str(lib), row["entity_id"])
        return self._store.restore(token, self._apply)

    def _apply(self, row: dict, new_path: Path) -> tuple[str, LibraryItem]:
        meta = _loads(row["meta"])
        kind = row["kind"]
        plural = PLURAL_OF[kind]
        library_id = str(meta["library_id"])
        komga_path = self._to_komga(new_path)
        self._c.scan_library(library_id)
        dto = self._wait_found(plural, row["entity_id"], library_id, komga_path, new_path.name)
        new_id = str(dto["id"])
        patch = self._metadata_patch(meta, dto)
        if patch:
            self._c.set_metadata(plural, new_id, patch)
        progress = meta.get("progress")
        if kind == "book" and progress and progress.get("page"):
            self._c.set_progress(new_id, int(progress["page"]), bool(progress.get("completed")))
        dto = self._c.get_book(new_id) if kind == "book" else self._c.get_series(new_id)
        self._relink_saved(row["entity_id"], new_id)
        return new_id, (book_item(dto) if kind == "book" else series_item(dto))

    @staticmethod
    def _metadata_patch(meta: dict, dto: dict) -> dict:
        """Tags, title and summary saved at delete time; only fields the scan lost."""
        scanned = dto.get("metadata") or {}
        patch: dict = {}
        if meta.get("tags"):
            patch.update(tags=list(meta["tags"]), tagsLock=True)
        for field in ("title", "summary"):
            saved = meta.get(field)
            if saved and saved != scanned.get(field):
                patch.update({field: saved, f"{field}Lock": True})
        return patch

    def _wait_found(
        self, plural: str, old_id: str, library_id: str, komga_path: str, name: str
    ) -> dict:
        """The restored item: the same id revived by the scan, or a new id at the path."""
        deadline = time.monotonic() + self._restore_timeout_s
        want = posixpath.normpath(komga_path)
        while True:
            try:
                dto = self._c.get_book(old_id) if plural == "books" else self._c.get_series(old_id)
                if (
                    not dto.get("deleted")
                    and posixpath.normpath(str(dto.get("url", "")).replace("\\", "/")) == want
                ):
                    return dto
            except KomgaError as e:
                if e.status != 404:
                    raise
            found = self._c.find_by_url(plural, library_id, komga_path, posixpath.splitext(name)[0])
            if found is not None:
                return found
            if time.monotonic() >= deadline:
                raise RuntimeError("not indexed")
            time.sleep(self._poll_s)

    def _relink_saved(self, old_id: str, new_id: str) -> None:
        conn = connect(self._s.db_path)
        try:
            conn.execute(
                "UPDATE saved_items SET library_id = ? WHERE target = 'komga' AND library_id = ?",
                (new_id, old_id),
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
