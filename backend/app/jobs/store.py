"""SQLite access for the job queue."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app.db import connect
from app.models import Job, Problem, SavedRef
from app.sources.base import Post

MAX_RESTARTS = 3


def _utc_iso(value: str | None) -> str | None:
    """SQLite CURRENT_TIMESTAMP is naive UTC text; the API sends it as ISO with Z."""
    if not value or value.endswith("Z") or "+" in value[10:]:
        return value
    return value.replace(" ", "T", 1) + "Z"


def _to_job(row: sqlite3.Row) -> Job:
    data: dict[str, object] = {
        "id": str(row["id"]),
        "source": row["source"],
        "post_id": row["post_id"],
        "title": row["title"],
        "thumb_url": row["thumb_url"],
        "target": row["target"],
        "state": row["status"],
        "progress": 1.0 if row["status"] == "done" else 0.0,
        "eta_s": None,
        "error": row["error"],
        "dest_path": row["dest_path"],
        "error_code": row["error_code"],
        "library_ref": None,
        "created_at": _utc_iso(row["created_at"]),
        "finished_at": _utc_iso(row["finished_at"]),
    }
    if row["library_ref_id"] is not None:
        kind = "image" if row["target"] == "stash" else "book"
        data["library_ref"] = SavedRef(kind=kind, id=row["library_ref_id"])
    data["notices"] = [Problem(**n) for n in json.loads(row["notices"])]
    return Job.model_validate(data)


def _chunks(items: list[str], size: int = 500):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _ref(target: str, image_id: str | None) -> SavedRef:
    # A Komga row has no image id; the marker still shows, without a link.
    return SavedRef(kind="book" if target == "komga" else "image", id=image_id or "")


class JobStore:
    def __init__(self, db_path: Path) -> None:
        self._path = db_path

    def saved_image_id(self, source: str, post_id: str) -> str | None:
        conn = connect(self._path)
        try:
            row = conn.execute(
                "SELECT image_id FROM saved_items WHERE source = ? AND post_id = ?",
                (source, post_id),
            ).fetchone()
            if row is None:
                return None
            return row["image_id"] if row["image_id"] is not None else ""
        finally:
            conn.close()

    def saved_refs(
        self, source: str, post_ids: list[str], md5s: dict[str, str] | None = None
    ) -> dict[str, SavedRef]:
        """One batched lookup for a page: post id to the library ref of its saved copy.

        `md5s` (post id to MD5) adds a second pass that also matches the same file
        saved from another source or post.
        """
        if not post_ids:
            return {}
        conn = connect(self._path)
        try:
            found: dict[str, SavedRef] = {}
            for chunk in _chunks(post_ids):
                marks = ",".join("?" * len(chunk))
                for row in conn.execute(
                    "SELECT post_id, target, image_id FROM saved_items "
                    f"WHERE source = ? AND post_id IN ({marks})",
                    (source, *chunk),
                ):
                    found[row["post_id"]] = _ref(row["target"], row["image_id"])
            by_md5 = {
                m.lower(): pid for pid, m in (md5s or {}).items() if m and pid not in found
            }
            for chunk in _chunks(list(by_md5)):
                marks = ",".join("?" * len(chunk))
                for row in conn.execute(
                    f"SELECT md5, target, image_id FROM saved_items WHERE md5 IN ({marks})",
                    tuple(chunk),
                ):
                    found.setdefault(
                        by_md5[row["md5"].lower()], _ref(row["target"], row["image_id"])
                    )
            return found
        finally:
            conn.close()

    def active_job_id(self, source: str, post_id: str) -> str | None:
        conn = connect(self._path)
        try:
            row = conn.execute(
                "SELECT id FROM jobs WHERE source = ? AND post_id = ? "
                "AND status IN ('queued', 'running')",
                (source, post_id),
            ).fetchone()
            if row is None:
                return None
            return str(row["id"])
        finally:
            conn.close()

    def enqueue(
        self, post: Post, target: str, title: str, thumb_url: str, placement: str | None = None
    ) -> str:
        conn = connect(self._path)
        try:
            for _ in range(3):
                try:
                    cur = conn.execute(
                        "INSERT INTO jobs "
                        "(source, post_id, status, target, title, thumb_url, post_json, placement) "
                        "VALUES (?, ?, 'queued', ?, ?, ?, ?, ?)",
                        (
                            post.source,
                            post.post_id,
                            target,
                            title,
                            thumb_url,
                            post.model_dump_json(),
                            json.dumps({"kind": placement}) if placement else None,
                        ),
                    )
                    conn.commit()
                    return str(cur.lastrowid)
                except sqlite3.IntegrityError:
                    conn.rollback()
                    existing = self.active_job_id(post.source, post.post_id)
                    if existing is not None:
                        return existing
            raise RuntimeError("could not enqueue job")
        finally:
            conn.close()

    def get(self, job_id: str) -> Job | None:
        try:
            int(job_id)
        except ValueError:
            return None
        conn = connect(self._path)
        try:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if row is None:
                return None
            return _to_job(row)
        finally:
            conn.close()

    def list(self, states: set[str] | None = None) -> list[Job]:
        conn = connect(self._path)
        try:
            if states is not None:
                placeholders = ",".join("?" for _ in states)
                rows = conn.execute(
                    f"SELECT * FROM jobs WHERE status IN ({placeholders}) ORDER BY id DESC",
                    tuple(states),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM jobs ORDER BY id DESC").fetchall()
            return [_to_job(r) for r in rows]
        finally:
            conn.close()

    def retry(self, job_id: str) -> str:
        conn = connect(self._path)
        try:
            try:
                cur = conn.execute(
                    "UPDATE jobs SET status='queued', error=NULL, error_code=NULL, "
                    "notices='[]', post_json=NULL, library_ref_id=NULL, dest_path=NULL, "
                    "started_at=NULL, finished_at=NULL, attempts=attempts+1, restarts=0, "
                    "updated_at=CURRENT_TIMESTAMP "
                    "WHERE id=? AND status IN ('failed', 'needs_click')",
                    (job_id,),
                )
                conn.commit()
                if cur.rowcount == 1:
                    return "ok"
            except sqlite3.IntegrityError:
                conn.rollback()
                return "conflict"
            row = conn.execute("SELECT id FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if row is None:
                return "missing"
            return "bad_state"
        finally:
            conn.close()

    def delete(self, job_id: str) -> str:
        conn = connect(self._path)
        try:
            cur = conn.execute(
                "DELETE FROM jobs WHERE id=? AND status<>'running'",
                (job_id,),
            )
            conn.commit()
            if cur.rowcount == 1:
                return "ok"
            row = conn.execute("SELECT id FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if row is None:
                return "missing"
            return "bad_state"
        finally:
            conn.close()

    def requeue_running(self, max_restarts: int = MAX_RESTARTS) -> int:
        """Requeue jobs left running by a crash; a job that already restarted
        max_restarts times ends failed (restart_limit) so it cannot loop."""
        conn = connect(self._path)
        try:
            conn.execute(
                "UPDATE jobs SET status='failed', error=?, error_code='restart_limit', "
                "finished_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP "
                "WHERE status='running' AND restarts >= ?",
                (
                    f"interrupted by {max_restarts} restarts in a row; retry it by hand",
                    max_restarts,
                ),
            )
            cur = conn.execute(
                "UPDATE jobs SET status='queued', started_at=NULL, restarts=restarts+1, "
                "updated_at=CURRENT_TIMESTAMP WHERE status='running'"
            )
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()

    def count_running(self) -> int:
        conn = connect(self._path)
        try:
            row = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='running'").fetchone()
            return int(row[0])
        finally:
            conn.close()

    def queued(self) -> list[tuple[str, str]]:
        conn = connect(self._path)
        try:
            rows = conn.execute(
                "SELECT id, source FROM jobs WHERE status='queued' ORDER BY id"
            ).fetchall()
            return [(str(r["id"]), r["source"]) for r in rows]
        finally:
            conn.close()

    def mark_running(self, job_id: str) -> bool:
        conn = connect(self._path)
        try:
            cur = conn.execute(
                "UPDATE jobs SET status='running', started_at=CURRENT_TIMESTAMP, "
                "updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='queued'",
                (job_id,),
            )
            conn.commit()
            return cur.rowcount == 1
        finally:
            conn.close()

    def load_post(self, job_id: str) -> tuple[str, str | None]:
        conn = connect(self._path)
        try:
            row = conn.execute(
                "SELECT target, post_json FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
            if row is None:
                return ("", None)
            return (row["target"], row["post_json"])
        finally:
            conn.close()

    def load_placement(self, job_id: str) -> str | None:
        """The save-dialog override ("series" or "oneshot") stored with the job, if any."""
        conn = connect(self._path)
        try:
            row = conn.execute("SELECT placement FROM jobs WHERE id = ?", (job_id,)).fetchone()
        finally:
            conn.close()
        if row is None or not row["placement"]:
            return None
        try:
            kind = json.loads(row["placement"]).get("kind")
        except (ValueError, AttributeError):
            return None
        return kind if kind in ("series", "oneshot") else None

    def set_post(self, job_id: str, post: Post) -> None:
        conn = connect(self._path)
        try:
            conn.execute(
                "UPDATE jobs SET post_json=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (post.model_dump_json(), job_id),
            )
            conn.commit()
        finally:
            conn.close()

    def finish(
        self,
        job_id: str,
        state: str,
        error: str | None = None,
        error_code: str | None = None,
        notices: list[Problem] | None = None,
        library_ref_id: str | None = None,
        dest_path: str | None = None,
    ) -> None:
        if notices is not None:
            notices_json = json.dumps([n.model_dump() for n in notices])
        else:
            notices_json = "[]"
        conn = connect(self._path)
        try:
            conn.execute(
                "UPDATE jobs SET status=?, error=?, error_code=?, notices=?, "
                "library_ref_id=?, dest_path=?, finished_at=CURRENT_TIMESTAMP, "
                "updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (state, error, error_code, notices_json, library_ref_id, dest_path, job_id),
            )
            conn.commit()
        finally:
            conn.close()
