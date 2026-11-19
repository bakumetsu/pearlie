"""Pearlie trash core: move a library file into the trash folder, undo, purge.

The store knows files, the ``trash_items`` table and tokens. It never talks to Stash or
Stump: the caller passes the library calls (destroy, restore) as functions, so a Stump
target can use the same store. Files are only renamed, never copied (product rule 1).
"""

from __future__ import annotations

import errno
import json
import logging
import os
import shutil
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.bookserver.base import BOOK_TARGETS
from app.db import connect

_BOOK_TARGET_SQL = f"target IN ({','.join('?' * len(BOOK_TARGETS))})"

logger = logging.getLogger("pearlie")

RETENTION_KEY = "options.global.trash_retention_days"
DIR_KEY = "options.global.trash_dir"
SIDECAR = ".pearlie.json"
ACTIVE_STATES = ("moving", "trashed", "restoring")


class TrashError(Exception):
    """A trash failure that maps to an API error."""

    def __init__(self, status: int, code: str, message: str) -> None:
        self.status = status
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass
class TrashSpec:
    """What to move: one library file or folder and what restore needs."""

    target: str
    kind: str
    entity_id: str
    title: str
    orig_path: Path
    meta: dict[str, Any] = field(default_factory=dict)
    md5: str | None = None
    source: str | None = None
    post_id: str | None = None
    group_id: str | None = None


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _size(path: Path) -> int:
    try:
        if path.is_dir():
            return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
        return path.stat().st_size
    except OSError:
        return 0


def _suffixed(path: Path) -> Path:
    """First free name next to *path*: ``a (restored).jpg``, ``a (restored 2).jpg``."""
    n = 1
    while True:
        tag = "(restored)" if n == 1 else f"(restored {n})"
        if path.is_dir() or (not path.exists() and path.suffix == ""):
            cand = path.with_name(f"{path.name} {tag}")
        else:
            cand = path.with_name(f"{path.stem} {tag}{path.suffix}")
        if not cand.exists():
            return cand
        n += 1


class TrashStore:
    def __init__(self, db_path: Path, trash_dir: Path) -> None:
        self._db = db_path
        self.default_dir = trash_dir
        self._lock = threading.Lock()

    @property
    def dir(self) -> Path:
        """The stored folder (Options) or, when none is stored, the ``.env`` default."""
        stored = self.stored_dir()
        return Path(stored) if stored else self.default_dir

    def stored_dir(self) -> str | None:
        conn = connect(self._db)
        try:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (DIR_KEY,)).fetchone()
        finally:
            conn.close()
        return str(row[0]) if row and str(row[0]).strip() else None

    def item_count(self) -> int:
        conn = connect(self._db)
        try:
            marks = ",".join("?" * len(ACTIVE_STATES))
            row = conn.execute(
                f"SELECT COUNT(*) FROM trash_items WHERE state IN ({marks})", ACTIVE_STATES
            ).fetchone()
            return int(row[0])
        finally:
            conn.close()

    def set_dir(self, path: str | None, validate: Callable[[], None] | None = None) -> None:
        """Store the folder (``None`` = back to the default) unless the trash has items.

        The count, *validate* and the write run under the store lock, so a restore cannot
        slip in between. A move that starts at the same time keeps its absolute row path.
        """
        with self._lock:
            if self.item_count() > 0:
                raise TrashError(409, "trash_not_empty", "Trash has items; restore or delete them")
            if validate is not None:
                validate()
            conn = connect(self._db)
            try:
                if path:
                    conn.execute(
                        "INSERT INTO settings (key, value) VALUES (?, ?) "
                        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                        (DIR_KEY, path),
                    )
                else:
                    conn.execute("DELETE FROM settings WHERE key = ?", (DIR_KEY,))
                conn.commit()
            finally:
                conn.close()
            self.__dict__.pop("_probe_cache", None)

    # -- settings -------------------------------------------------------------

    def retention_days(self) -> int:
        conn = connect(self._db)
        try:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?", (RETENTION_KEY,)
            ).fetchone()
        finally:
            conn.close()
        try:
            return min(365, max(1, int(row[0]))) if row else 7
        except (TypeError, ValueError):
            return 7

    def check_dir(self) -> None:
        """503 ``trash_unavailable`` unless the trash folder exists and is writable."""
        if not self.dir.is_dir():
            try:
                self.dir.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
        if not self.dir.is_dir() or not os.access(self.dir, os.W_OK):
            raise TrashError(503, "trash_unavailable", "Trash folder is missing or not writable")

    def _inside(self, path: Path) -> bool:
        try:
            Path(os.path.realpath(path)).relative_to(os.path.realpath(self.dir))
            return True
        except ValueError:
            return False

    # -- rows -----------------------------------------------------------------

    def _row(self, token: str) -> dict | None:
        conn = connect(self._db)
        try:
            r = conn.execute("SELECT * FROM trash_items WHERE token = ?", (token,)).fetchone()
            return dict(r) if r else None
        finally:
            conn.close()

    def _run(self, sql: str, args: tuple = ()) -> None:
        conn = connect(self._db)
        try:
            conn.execute(sql, args)
            conn.commit()
        finally:
            conn.close()

    def get(self, token: str) -> dict | None:
        return self._row(token)

    def list_rows(self) -> list[dict]:
        """Trashed, not expired, newest first."""
        now = _iso(datetime.now(UTC))
        conn = connect(self._db)
        try:
            rows = conn.execute(
                "SELECT * FROM trash_items WHERE state = 'trashed' AND expires_at > ? "
                "ORDER BY trashed_at DESC",
                (now,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def active_for_entity(self, target: str, entity_id: str) -> dict | None:
        conn = connect(self._db)
        try:
            r = conn.execute(
                "SELECT * FROM trash_items WHERE target = ? AND entity_id = ? AND state IN "
                "('moving','trashed','restoring') LIMIT 1",
                (target, entity_id),
            ).fetchone()
            return dict(r) if r else None
        finally:
            conn.close()

    def stump_owned_ids(self) -> set[str]:
        """book ids Pearlie trashed (`moving` or `trashed`), with what Stump drops with them.

        A `restoring` row is left out on purpose: its item must not be purged under it.
        A trashed series also owns its book ids, and a book that emptied its series owns
        that series id.
        """
        conn = connect(self._db)
        try:
            rows = conn.execute(
                f"SELECT entity_id, meta FROM trash_items WHERE {_BOOK_TARGET_SQL} "
                "AND state IN ('moving','trashed')",
                BOOK_TARGETS,
            ).fetchall()
        finally:
            conn.close()
        ids: set[str] = set()
        for r in rows:
            ids.add(r["entity_id"])
            try:
                meta = json.loads(r["meta"] or "{}")
            except ValueError:
                continue
            ids.update(str(i) for i in meta.get("book_ids") or [])
            if meta.get("series_gone_id"):
                ids.add(str(meta["series_gone_id"]))
        return ids

    def stump_covering(self, book_id: str) -> dict | None:
        """A live Stump trash row that holds the book: the book itself or its series."""
        conn = connect(self._db)
        try:
            rows = conn.execute(
                f"SELECT * FROM trash_items WHERE {_BOOK_TARGET_SQL} AND state IN "
                "('moving','trashed','restoring')",
                BOOK_TARGETS,
            ).fetchall()
        finally:
            conn.close()
        for r in rows:
            if r["entity_id"] == book_id:
                return dict(r)
            try:
                meta = json.loads(r["meta"] or "{}")
            except ValueError:
                continue
            if book_id in [str(i) for i in meta.get("book_ids") or []]:
                return dict(r)
        return None

    def find_in_trash(
        self, source: str | None = None, post_id: str | None = None, md5: str | None = None
    ) -> dict | None:
        """A live trash row for a post or an MD5 (dedupe)."""
        conn = connect(self._db)
        try:
            r = None
            if source and post_id:
                r = conn.execute(
                    "SELECT * FROM trash_items WHERE source = ? AND post_id = ? AND state IN "
                    "('moving','trashed','restoring') LIMIT 1",
                    (source, post_id),
                ).fetchone()
            if r is None and md5:
                r = conn.execute(
                    "SELECT * FROM trash_items WHERE md5 = ? AND state IN "
                    "('moving','trashed','restoring') LIMIT 1",
                    (md5.lower(),),
                ).fetchone()
            return dict(r) if r else None
        finally:
            conn.close()

    # -- delete ---------------------------------------------------------------

    def delete(self, spec: TrashSpec, destroy: Callable[[], None]) -> dict:
        """Move the file, call *destroy* (the library forgets the entry), all or nothing."""
        self.check_dir()
        src = spec.orig_path
        if not os.path.lexists(src):
            raise TrashError(404, "not_found", "Item not found")
        if self._inside(src):
            raise TrashError(422, "path_outside_library", "Item is outside the library")
        token = uuid.uuid4().hex
        now = datetime.now(UTC)
        expires = now + timedelta(days=self.retention_days())
        folder = self.dir / token
        dest = folder / src.name
        conn = connect(self._db)
        try:
            conn.execute(
                "INSERT INTO trash_items (token, group_id, target, kind, entity_id, title, "
                "orig_path, trash_path, md5, source, post_id, meta, state, trashed_at, "
                "expires_at, size_bytes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'moving',?,?,?)",
                (
                    token,
                    spec.group_id,
                    spec.target,
                    spec.kind,
                    spec.entity_id,
                    spec.title,
                    str(src),
                    str(dest),
                    spec.md5.lower() if spec.md5 else None,
                    spec.source,
                    spec.post_id,
                    json.dumps(spec.meta),
                    _iso(now),
                    _iso(expires),
                    _size(src),
                ),
            )
            conn.commit()
        finally:
            conn.close()
        try:
            folder.mkdir()
            (folder / SIDECAR).write_text(
                json.dumps(
                    {
                        "token": token,
                        "target": spec.target,
                        "kind": spec.kind,
                        "entity_id": spec.entity_id,
                        "title": spec.title,
                        "orig_path": str(src),
                        "meta": spec.meta,
                    }
                ),
                encoding="utf-8",
            )
            os.rename(src, dest)
        except OSError as e:
            self._drop(token, folder)
            if e.errno == errno.EXDEV:
                raise TrashError(
                    503, "trash_unavailable", "Trash folder is on another volume"
                ) from None
            logger.warning("trash move failed token=%s errno=%s", token, e.errno)
            raise TrashError(503, "trash_unavailable", "Could not move the item") from None
        try:
            destroy()
        except Exception as e:
            logger.warning(
                "trash destroy failed token=%s kind=%s error=%s", token, spec.kind, type(e).__name__
            )
            self._rollback(token, src, dest, folder)
            raise
        self._run("UPDATE trash_items SET state = 'trashed' WHERE token = ?", (token,))
        logger.info("trash token=%s kind=%s id=%s state=trashed", token, spec.kind, spec.entity_id)
        return self._row(token) or {}

    def _drop(self, token: str, folder: Path) -> None:
        self._run("DELETE FROM trash_items WHERE token = ?", (token,))
        if folder.is_dir() and self._inside(folder):
            shutil.rmtree(folder, ignore_errors=True)

    def _rollback(self, token: str, src: Path, dest: Path, folder: Path) -> None:
        try:
            os.rename(dest, src)
        except OSError:
            # Row stays `moving`; the start-up repair retries.
            logger.warning("trash rollback failed token=%s", token)
            return
        self._drop(token, folder)

    # -- restore --------------------------------------------------------------

    def restore(self, token: str, apply: Callable[[dict, Path], tuple[str, Any]]) -> Any:
        """Move back, then *apply(row, new_path)* -> (new_entity_id, result)."""
        with self._lock:
            row = self._row(token)
            if row is None or row["state"] != "trashed":
                raise TrashError(404, "not_found", "Item not found")
            if _parse(row["expires_at"]) <= datetime.now(UTC):
                self.purge_row(token)
                raise TrashError(404, "not_found", "Item not found")
            self._run("UPDATE trash_items SET state = 'restoring' WHERE token = ?", (token,))
        src = Path(row["trash_path"])
        target = Path(row["orig_path"])
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if os.path.lexists(target):
                target = _suffixed(target)
            os.rename(src, target)
        except OSError as e:
            self._run("UPDATE trash_items SET state = 'trashed' WHERE token = ?", (token,))
            code = "trash_unavailable"
            msg = (
                "Trash folder is on another volume"
                if e.errno == errno.EXDEV
                else "Could not restore"
            )
            raise TrashError(503, code, msg) from None
        try:
            new_id, result = apply(row, target)
        except Exception as e:
            logger.warning(
                "restore incomplete token=%s path=%s error=%s", token, target, type(e).__name__
            )
            self._drop(token, self.dir / token)
            raise TrashError(
                502,
                "restore_incomplete",
                f"{target.name} is back in the library but not registered",
            ) from None
        self._saved_items_after_restore(row, new_id)
        self._drop(token, self.dir / token)
        logger.info("trash token=%s state=restored", token)
        return result

    def _saved_items_after_restore(self, row: dict, new_id: str) -> None:
        conn = connect(self._db)
        try:
            cur = conn.execute(
                "UPDATE saved_items SET image_id = ? WHERE target = ? AND image_id = ?",
                (new_id, row["target"], row["entity_id"]),
            )
            if cur.rowcount == 0 and row["source"] and row["post_id"]:
                conn.execute(
                    "INSERT OR IGNORE INTO saved_items "
                    "(source, post_id, md5, target, image_id, kind) VALUES (?,?,?,?,?,?)",
                    (
                        row["source"],
                        row["post_id"],
                        row["md5"] or "",
                        row["target"],
                        new_id,
                        row["kind"],
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    # -- purge ----------------------------------------------------------------

    def purge_row(self, token: str) -> bool:
        """Delete the files, the row and the saved_items row. False if the files stay."""
        row = self._row(token)
        if row is None:
            return False
        folder = self.dir / token
        if folder.exists() or folder.is_symlink():
            if folder.is_symlink() or not self._inside(folder):
                logger.warning("trash purge refused token=%s", token)
                return False
            try:
                shutil.rmtree(folder)
            except OSError as e:
                logger.warning("trash purge failed token=%s errno=%s", token, e.errno)
                return False
        conn = connect(self._db)
        try:
            conn.execute("DELETE FROM trash_items WHERE token = ?", (token,))
            conn.execute(
                "DELETE FROM saved_items WHERE target = ? AND image_id = ?",
                (row["target"], row["entity_id"]),
            )
            if row["source"] and row["post_id"]:
                conn.execute(
                    "DELETE FROM saved_items WHERE source = ? AND post_id = ?",
                    (row["source"], row["post_id"]),
                )
            if row["target"] in BOOK_TARGETS:
                try:
                    book_ids = json.loads(row["meta"] or "{}").get("book_ids") or []
                except ValueError:
                    book_ids = []
                for book_id in [row["entity_id"], *book_ids]:
                    conn.execute(
                        f"DELETE FROM saved_items WHERE {_BOOK_TARGET_SQL} AND library_id = ?",
                        (*BOOK_TARGETS, str(book_id)),
                    )
            conn.commit()
        finally:
            conn.close()
        return True

    def delete_for_good(self, token: str) -> None:
        row = self._row(token)
        if row is None or row["state"] != "trashed":
            raise TrashError(404, "not_found", "Item not found")
        if not self.purge_row(token):
            raise TrashError(503, "trash_unavailable", "Could not delete the item")

    def purge_expired(self) -> int:
        now = _iso(datetime.now(UTC))
        conn = connect(self._db)
        try:
            tokens = [
                r[0]
                for r in conn.execute(
                    "SELECT token FROM trash_items WHERE state = 'trashed' AND expires_at <= ?",
                    (now,),
                )
            ]
        finally:
            conn.close()
        return sum(1 for t in tokens if self.purge_row(t))

    def empty(self) -> int:
        conn = connect(self._db)
        try:
            tokens = [
                r[0] for r in conn.execute("SELECT token FROM trash_items WHERE state = 'trashed'")
            ]
        finally:
            conn.close()
        return sum(1 for t in tokens if self.purge_row(t))

    def purge_preview(self, days: int) -> int:
        conn = connect(self._db)
        try:
            rows = conn.execute(
                "SELECT trashed_at FROM trash_items WHERE state = 'trashed'"
            ).fetchall()
        finally:
            conn.close()
        now = datetime.now(UTC)
        return sum(1 for (t,) in rows if _parse(t) + timedelta(days=days) <= now)

    def set_retention(self, days: int, purge: bool = False) -> int:
        """A longer retention only moves expiry later; *purge* recomputes and purges."""
        conn = connect(self._db)
        try:
            rows = conn.execute(
                "SELECT token, trashed_at, expires_at FROM trash_items WHERE state = 'trashed'"
            ).fetchall()
            for r in rows:
                new = _parse(r["trashed_at"]) + timedelta(days=days)
                if not purge:
                    new = max(new, _parse(r["expires_at"]))
                conn.execute(
                    "UPDATE trash_items SET expires_at = ? WHERE token = ?", (_iso(new), r["token"])
                )
            conn.commit()
        finally:
            conn.close()
        return self.purge_expired() if purge else 0

    # -- start-up repair ------------------------------------------------------

    def repair(self, destroyers: dict[str, Callable[[dict], None]]) -> None:
        """Settle rows left `moving` or `restoring` by a crash."""
        conn = connect(self._db)
        try:
            rows = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM trash_items WHERE state IN ('moving','restoring')"
                )
            ]
        finally:
            conn.close()
        base = self.dir
        for row in rows:
            token = row["token"]
            trash_path, orig = Path(row["trash_path"]), Path(row["orig_path"])
            folder = base / token
            try:
                if row["state"] == "restoring":
                    if os.path.lexists(trash_path):
                        self._run("UPDATE trash_items SET state='trashed' WHERE token=?", (token,))
                    else:
                        logger.warning(
                            "trash repair: restore of token=%s left the file in the library", token
                        )
                        self._drop(token, folder)
                    continue
                if not os.path.lexists(trash_path):
                    self._drop(token, folder)
                    continue
                destroy = destroyers.get(row["target"])
                try:
                    if destroy is None:
                        raise RuntimeError("no destroyer")
                    destroy(row)
                except Exception:
                    self._rollback(token, orig, trash_path, folder)
                    continue
                self._run("UPDATE trash_items SET state='trashed' WHERE token=?", (token,))
            except OSError:
                logger.warning("trash repair failed token=%s", token)
