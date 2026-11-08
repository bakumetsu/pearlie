"""Job board fixture with simulated timing."""
from __future__ import annotations

import time
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from app.models import Job, SavedRef


class Conflict(Exception):
    def __init__(self, library_ref: dict | None):
        self.library_ref = library_ref
        super().__init__()


class Rejected(Exception):
    pass


class BadState(Exception):
    pass


class JobBoard:
    def __init__(self, web: dict[str, list[dict]]):
        self.web = web
        self.jobs: list[dict] = []
        self._counter = 0
        self.reset()

    def reset(self) -> None:
        self.jobs = []
        self._counter = 0

    def _next_id(self) -> str:
        self._counter += 1
        return f"job-{self._counter}"

    def _compute_start(self, source: str) -> float:
        now = time.monotonic()
        latest = max(
            (j["_start"] for j in self.jobs
             if j["source"] == source and not j["_fixed"]),
            default=None,
        )
        base = latest + 8 if latest is not None else now
        return max(now, base) + 3

    def _advance(self) -> None:
        now = time.monotonic()
        for j in self.jobs:
            if j["_fixed"]:
                continue
            elapsed = now - j["_start"]
            if elapsed < 0:
                j["state"], j["eta_s"], j["progress"] = "queued", -elapsed, 0.0
            elif elapsed < 8:
                j["state"], j["eta_s"], j["progress"] = "running", 8 - elapsed, elapsed / 8
            else:
                j["state"], j["progress"], j["eta_s"] = "done", 1.0, 0.0
                if j["finished_at"] is None:
                    j["finished_at"] = datetime.now(UTC).isoformat()
                    ref = {"kind": "image" if j["target"] == "stash" else "book",
                           "id": "900" + str(j["_n"])}
                    j["library_ref"] = ref
                    for post in self.web.get(j["source"], []):
                        if post["post_id"] == j["post_id"]:
                            post["saved"] = ref
                            break

    def _to_model(self, d: dict) -> Job:
        clean = {k: v for k, v in d.items() if not k.startswith("_")}
        if clean.get("library_ref") is not None:
            clean["library_ref"] = SavedRef(**clean["library_ref"])
        return Job(**clean)

    def seed(self) -> None:
        eligible = [p for posts in self.web.values() for p in posts
                    if "_rejected" not in p and p["saved"] is None]
        now_mono = time.monotonic()
        now_dt = datetime.now(UTC)
        specs: Sequence[tuple[str, str | None, bool]] = (
            [("running", None, False)] * 2
            + [("queued", None, False)] * 3
            + [("failed", "Source returned 503", True)] * 2
            + [("needs_click", None, True)] * 1
            + [("done", None, True)] * 12
        )
        for i, (state, error, fixed) in enumerate(specs):
            p = eligible[i]
            nid = self._next_id()
            num = self._counter
            if state == "running":
                start = now_mono - 3
            elif state == "queued":
                start = now_mono + 3 + (i - 2) * 3
            else:
                start = now_mono
            ref = ({"kind": "image" if p["target"] == "stash" else "book",
                    "id": "900" + str(num)} if state == "done" else None)
            self.jobs.append({
                "id": nid, "source": p["source"], "post_id": p["post_id"],
                "title": p.get("title") or f"{p['source']} {p['post_id']}",
                "thumb_url": p["thumb_url"], "target": p["target"],
                "state": state,
                "progress": 1.0 if state == "done" else 0.0,
                "eta_s": 0.0, "error": error, "library_ref": ref,
                "created_at": (now_dt - timedelta(minutes=i)).isoformat(),
                "finished_at": (now_dt - timedelta(minutes=i)).isoformat()
                if state == "done" else None,
                "_t0": now_mono, "_start": start, "_fixed": fixed, "_n": num,
            })

    def list(self, states: set[str] | None = None) -> list[Job]:
        self._advance()
        out = [self._to_model(j) for j in reversed(self.jobs)
               if states is None or j["state"] in states]
        return out

    def get(self, job_id: str) -> Job | None:
        self._advance()
        for j in self.jobs:
            if j["id"] == job_id:
                return self._to_model(j)
        return None

    def save(self, source: str, post_id: str) -> str:
        self._advance()
        post = next(
            (p for p in self.web.get(source, []) if p["post_id"] == post_id),
            None,
        )
        if post is None:
            raise KeyError(f"unknown post {source}/{post_id}")
        if "_rejected" in post:
            raise Rejected()
        if post["saved"] is not None:
            raise Conflict(post["saved"])
        for j in self.jobs:
            if (j["source"] == source and j["post_id"] == post_id
                    and not j["_fixed"] and j["state"] in ("queued", "running")):
                raise Conflict(None)
        d = self._new_from_post(post)
        return d["id"]

    def _new_from_post(self, p: dict) -> dict:
        nid = self._next_id()
        num = self._counter
        d = {
            "id": nid, "source": p["source"], "post_id": p["post_id"],
            "title": p.get("title") or f"{p['source']} {p['post_id']}",
            "thumb_url": p["thumb_url"], "target": p["target"],
            "state": "queued", "progress": 0.0, "eta_s": 0.0,
            "error": None, "library_ref": None,
            "created_at": datetime.now(UTC).isoformat(),
            "finished_at": None,
            "_t0": time.monotonic(), "_start": self._compute_start(p["source"]),
            "_fixed": False, "_n": num,
        }
        self.jobs.append(d)
        return d

    def retry(self, job_id: str) -> Job | None:
        self._advance()
        j = next((x for x in self.jobs if x["id"] == job_id), None)
        if j is None:
            return None
        if j["state"] not in ("failed", "needs_click"):
            raise BadState()
        p = next(
            (x for x in self.web.get(j["source"], []) if x["post_id"] == j["post_id"]),
            None,
        )
        idx = self.jobs.index(j)
        d = self._new_from_post(p if p is not None else {
            "source": j["source"], "post_id": j["post_id"],
            "title": j["title"], "thumb_url": j["thumb_url"], "target": j["target"],
        })
        self.jobs[idx] = d
        return self._to_model(d)

    def delete(self, job_id: str) -> bool | None:
        self._advance()
        j = next((x for x in self.jobs if x["id"] == job_id), None)
        if j is None:
            return None
        if j["state"] == "running":
            raise BadState()
        self.jobs.remove(j)
        return True
