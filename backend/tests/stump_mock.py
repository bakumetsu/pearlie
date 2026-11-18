"""Just enough Stump (GraphQL + REST images) over httpx.MockTransport; records the calls."""

from __future__ import annotations

import io
import json
import re

import httpx
from PIL import Image


def png(w: int = 400, h: int = 600) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (w, h), (200, 30, 30)).save(out, "PNG")
    return out.getvalue()


def _contains(filter_: object) -> str:
    """The first `contains` value of a filter (the mock treats it as the search text)."""
    if isinstance(filter_, dict):
        if "contains" in filter_:
            return str(filter_["contains"]).lower()
        for v in filter_.values():
            found = _contains(v)
            if found:
                return found
    elif isinstance(filter_, list):
        for v in filter_:
            found = _contains(v)
            if found:
                return found
    return ""


def _eq(filter_: dict | None, field: str) -> str | None:
    parts = (filter_ or {}).get("_and") or [filter_ or {}]
    for p in parts:
        if field in p and "eq" in p[field]:
            return p[field]["eq"]
    return None


class MockStump:
    def __init__(self, libs: list, series: list, books: list, page: bytes | None = None) -> None:
        self.libs, self.series, self.books = libs, series, books
        self.page = page if page is not None else png()
        self.calls: list[tuple[str, str, dict]] = []  # (method, path, body)
        self.headers: list[httpx.Headers] = []
        self.job_status = ["RUNNING", "COMPLETED"]
        self.scanned: list[str] = []
        self.last_job: str | None = "job1"

    def __call__(self, req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content) if req.content else {}
        self.calls.append((req.method, req.url.path, body))
        self.headers.append(req.headers)
        if req.url.path == "/api/graphql":
            return self._gql(body)
        m = re.fullmatch(r"/api/v2/(media|series)/(\w+)/(thumbnail|page/(\d+))", req.url.path)
        if m:
            if m[2] == "b9":
                return httpx.Response(404)
            data = self.page if m[3] != "thumbnail" else b"jpg"
            ctype = "image/png" if m[3] != "thumbnail" else "image/jpeg"
            return httpx.Response(200, content=data, headers={"content-type": ctype})
        return httpx.Response(500)

    def _gql(self, body: dict) -> httpx.Response:
        op, v = body["operationName"], body["variables"]
        if op == "Libraries":
            return self._ok({"libraries": self._conn(self.libs, v["page"], 100)})
        if op in ("SeriesList", "MediaList"):
            rows = self._filtered(self.series if op == "SeriesList" else self.books, v["filter"])
            if _name_asc(v["order"]):
                rows = sorted(rows, key=lambda r: r["name"])
            key = "series" if op == "SeriesList" else "media"
            return self._ok({key: self._conn(rows, v["page"], v["size"])})
        if op in ("SeriesById", "MediaById"):
            rows = self.series if op == "SeriesById" else self.books
            hit = next((r for r in rows if r["id"] == v["id"]), None)
            return self._ok({op[0].lower() + op[1:]: hit})
        if op == "MediaByPath":
            hit = next((r for r in self.books if r["path"] == v["path"]), None)
            return self._ok({"mediaByPath": hit})
        if op == "ScanLibrary":
            self.scanned.append(v["id"])
            return self._ok({"scanLibrary": True})
        if op == "LastScan":
            hit = next((r for r in self.libs if r["id"] == v["id"]), None)
            last = {"jobId": self.last_job} if self.last_job else None
            return self._ok({"libraryById": {"lastScan": last} if hit else None})
        if op == "Job":
            status = self.job_status.pop(0) if len(self.job_status) > 1 else self.job_status[0]
            return self._ok({"jobById": {"id": v["id"], "status": status}})
        return httpx.Response(200, json={"errors": [{"message": "Unknown operation"}]})

    @staticmethod
    def _ok(data: dict) -> httpx.Response:
        return httpx.Response(200, json={"data": data})

    @staticmethod
    def _filtered(rows: list, filter_: dict | None) -> list:
        rows = [r for r in rows if not r.get("deletedAt") and r.get("status") != "MISSING"]
        for field in ("libraryId", "seriesId"):
            want = _eq(filter_, field)
            if want:
                rows = [r for r in rows if r.get(field) == want]
        path = _eq(filter_, "path")
        if path:
            rows = [r for r in rows if r["path"] == path]
        q = _contains(filter_)
        if q:
            rows = [r for r in rows if q in (r["name"] + r["path"]).lower()]
        return rows

    @staticmethod
    def _conn(rows: list, page: int, size: int) -> dict:
        pages = max(1, -(-len(rows) // size))
        return {
            "nodes": rows[(page - 1) * size : page * size],
            "pageInfo": {"totalPages": pages, "totalItems": len(rows)},
        }


def _name_asc(order: list) -> bool:
    return bool(order) and order[0]["field"] == "NAME"


def lib() -> dict:
    return {"id": "L1", "name": "Lib", "path": "/data", "config": {"oneshotsDirectory": "oneshots"}}


def book(i: int, series: str = "s1", gone: bool = False) -> dict:
    return {
        "id": f"b{i}",
        "seriesId": series,
        "libraryId": "L1",
        "name": f"Book {i}",
        "path": f"/data/s/book{i}.cbz",
        "pages": 5,
        "status": "MISSING" if gone else "READY",
        "createdAt": f"2026-01-0{i}T00:00:00Z",
        "deletedAt": None,
        "readProgress": None,
        "metadata": {"title": f"Book {i}", "summary": "", "writers": [], "links": []},
        "tags": [{"name": "x"}],
    }


def series() -> dict:
    return {
        "id": "s1",
        "libraryId": "L1",
        "name": "Series",
        "path": "/data/s",
        "createdAt": "2026-01-01T00:00:00Z",
        "deletedAt": None,
        "isOneshot": False,
        "mediaCount": 3,
        "readCount": 0,
        "metadata": {"title": "Series", "summary": "", "links": []},
        "tags": [{"name": "y"}],
    }
