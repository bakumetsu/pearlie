"""SQLite access for the job queue."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app.db import connect
from app.models import Job, Problem, SavedRef
from app.sources.base import Post


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
        "library_ref": None,
        "created_at": row["created_at"],
        "finished_at": row["finished_at"],
    }
    if row["library_ref_id"] is not None:
        kind = "image" if row["target"] == "stash" else "book"
        data["library_ref"] = SavedRef(kind=kind, id=row["library_ref_id"])
    data["notices"] = [Problem(**n) for n in json.loads(row["notices"])]
    return Job.model_validate(data)


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

    def enqueue(self, post: Post, target: str, title: str, thumb_url: str) -> str:
        conn = connect(self._path)
        try:
            for _ in range(3):
                try:
                    cur = conn.execute(
                        "INSERT INTO jobs "
                        "(source, post_id, status, target, title, thumb_url, post_json) "
                        "VALUES (?, ?, 'queued', ?, ?, ?, ?)",
                        (
                            post.source,
                            post.post_id,
                            target,
                            title,
                            thumb_url,
                            post.model_dump_json(),
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
                    "notices='[]', post_json=NULL, library_ref_id=NULL, "
                    "started_at=NULL, finished_at=NULL, attempts=attempts+1, "
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

    def requeue_running(self) -> int:
        conn = connect(self._path)
        try:
            cur = conn.execute(
                "UPDATE jobs SET status='queued', started_at=NULL, "
                "updated_at=CURRENT_TIMESTAMP WHERE status='running'"
            )
            conn.commit()
            return cur.rowcount
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
    ) -> None:
        if notices is not None:
            notices_json = json.dumps([n.model_dump() for n in notices])
        else:
            notices_json = "[]"
        conn = connect(self._path)
        try:
            conn.execute(
                "UPDATE jobs SET status=?, error=?, error_code=?, notices=?, "
                "library_ref_id=?, finished_at=CURRENT_TIMESTAMP, "
                "updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (state, error, error_code, notices_json, library_ref_id, job_id),
            )
            conn.commit()
        finally:
            conn.close()
