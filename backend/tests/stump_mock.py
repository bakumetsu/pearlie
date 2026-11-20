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


# What Stump v0.1.13 accepts (checked against its web client): the oneof order entries and the
# filter fields Pearlie sends. A media filter has no `libraryId`: it goes through `series`.
_FILTER_FIELDS = {
    # SeriesFilterInput has no `status` (live: unknown field "status")
    "SeriesList": {"libraryId", "path", "name", "metadata", "_and", "_or"},
    "MediaList": {"seriesId", "series", "path", "status", "name", "metadata", "_and", "_or"},
}
_ORDER_KEY = {"SeriesList": "series", "MediaList": "media"}


def _shape_error(op: str, v: dict, query: str) -> str | None:
    """The message Stump gives for an input it refuses; `None` when the shape is valid."""
    for i, entry in enumerate(v["order"] or []):
        ok = isinstance(entry, dict) and list(entry) == [_ORDER_KEY[op]]
        if not ok or set(entry[_ORDER_KEY[op]]) != {"field", "direction"}:
            return f'Invalid value for argument "orderBy.{i}", Oneof input objects requires'

    # Stump's own queries declare `$filter: <Type>!`: a nullable variable or null is refused.
    ftype = "SeriesFilterInput" if op == "SeriesList" else "MediaFilterInput"
    if f"$filter: {ftype}!" not in query or v["filter"] is None:
        return f'Invalid value for argument "filter", expected type "{ftype}"'

    def bad(f: object) -> bool:
        if not isinstance(f, dict) or not set(f) <= _FILTER_FIELDS[op]:
            return True
        return any(bad(x) for k in ("_and", "_or") for x in f.get(k, []))

    if bad(v["filter"]):
        return 'Invalid value for argument "filter", expected type "FilterInput"'
    return None


def _series_library(filter_: dict | None) -> str | None:
    """The library of a media filter's `series: {libraryId: {eq}}`."""
    for p in (filter_ or {}).get("_and") or [filter_ or {}]:
        if "series" in p:
            return p["series"]["libraryId"]["eq"]
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
        self.cleaned: list[str] = []
        self.locks: list[tuple[str, str, list[str]]] = []  # (operation, id, fields)
        self.fail_ops: dict[str, str] = {}  # operation name -> error message answered every time
        self.progress_errors: list[str] = []  # messages answered before a progress save works

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
            if (err := _shape_error(op, v, body["query"])) is not None:
                return httpx.Response(200, json={"errors": [{"message": err}]})
            rows = self._filtered(
                self.series if op == "SeriesList" else self.books, v["filter"], op == "SeriesList"
            )
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
            hist = [{"jobId": self.last_job, "timestamp": "2026-01-01T00:00:00Z"}]
            hist = hist if self.last_job else []
            return self._ok({"libraryById": {"scanHistory": hist} if hit else None})
        if op == "Job":
            status = self.job_status.pop(0) if len(self.job_status) > 1 else self.job_status[0]
            return self._ok({"jobById": {"id": v["id"], "status": status}})
        return self._write(op, v, body["query"]) or httpx.Response(
            200, json={"errors": [{"message": "Unknown operation"}]}
        )

    def _find(self, rows: list, id_: str) -> dict:
        return next(r for r in rows if r["id"] == id_)

    def _write(self, op: str, v: dict, query: str) -> httpx.Response | None:
        """The write operations; `None` for an unknown one."""
        done = self._ok({op[0].lower() + op[1:]: {"__typename": "X"}})
        if op == "CleanLibrary":
            self.cleaned.append(v["id"])
            self.books[:] = [b for b in self.books if b["status"] != "MISSING"]
            self.series[:] = [s for s in self.series if s.get("status") != "MISSING"]
            return self._ok({"cleanLibrary": {"__typename": "X"}})
        if op in ("SetMediaTags", "SetSeriesTags"):
            rows = self.books if op == "SetMediaTags" else self.series
            self._find(rows, v["id"])["tags"] = [{"name": t} for t in v["tags"]]
            return self._ok({"set": {"__typename": "X"}})
        if op in ("UpdateMediaMetadata", "UpdateSeriesMetadata"):
            rows = self.books if op == "UpdateMediaMetadata" else self.series
            self._find(rows, v["id"])["metadata"].update(v["input"])
            return self._ok({"update": {"__typename": "X"}})
        if op in ("SetMediaLockedFields", "SetSeriesLockedFields"):
            # the shape of Stump's own web client (0.1.13): mediaId/seriesId + lockedFields
            field = (
                "setMediaLockedFields" if op == "SetMediaLockedFields" else "setSeriesLockedFields"
            )
            arg = "mediaId" if op == "SetMediaLockedFields" else "seriesId"
            want = f"{field}({arg}: ${arg}, lockedFields: $lockedFields) {{ id }}"
            if want not in query or set(v) != {arg, "lockedFields"}:
                return httpx.Response(
                    200, json={"errors": [{"message": 'Unknown argument "fields"'}]}
                )
            self.locks.append((field, v[arg], list(v["lockedFields"])))
            return self._ok({field: {"id": v[arg]}})
        if op == "UpdateMediaProgress":
            if self.progress_errors:
                msg = self.progress_errors.pop(0)
                return httpx.Response(200, json={"errors": [{"message": msg}]})
            page = v["input"]["paged"]["page"]
            self._find(self.books, v["id"])["readProgress"] = {"page": page}
            return done
        if op == "FinishMediaProgress":
            if "{ __typename }" in query:  # Stump returns a scalar: a selection is an error
                msg = 'Field "finishMediaProgress" must not have a selection'
                return httpx.Response(200, json={"errors": [{"message": msg}]})
            self._find(self.books, v["id"])["readHistory"] = [
                {"completedAt": "2026-01-02T00:00:00Z"}
            ]
            return self._ok({"finishMediaProgress": True})
        if op in ("ClearMediaProgress", "DeleteMediaReadingHistory"):
            if op in self.fail_ops:
                return httpx.Response(200, json={"errors": [{"message": self.fail_ops[op]}]})
            field = op[0].lower() + op[1:]
            if f"{field}(id: $id) {{" in query:  # Stump returns a scalar: a selection is an error
                msg = f'Field "{field}" must not have a selection'
                return httpx.Response(200, json={"errors": [{"message": msg}]})
            book = self._find(self.books, v["id"])
            if op == "ClearMediaProgress":
                book["readProgress"] = None
            else:
                book["readHistory"] = []
            return self._ok({field: True})
        return None

    @staticmethod
    def _ok(data: dict) -> httpx.Response:
        return httpx.Response(200, json={"data": data})

    @staticmethod
    def _filtered(rows: list, filter_: dict | None, is_series: bool = False) -> list:
        if is_series:  # no status filter on series: MISSING ones are listed too (the UI shows them)
            pass
        elif _eq(filter_, "status") == "MISSING":
            rows = [r for r in rows if r.get("status") == "MISSING"]
        else:
            rows = [r for r in rows if r.get("status") != "MISSING"]
        for field, want in (
            ("libraryId", _eq(filter_, "libraryId") or _series_library(filter_)),
            ("seriesId", _eq(filter_, "seriesId")),
        ):
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
    return bool(order) and next(iter(order[0].values()))["field"] == "NAME"


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
        "readProgress": None,
        "readHistory": [],
        "metadata": {"title": f"Book {i}", "summary": "", "writers": [], "links": []},
        "tags": [{"name": "x"}],
    }


def series() -> dict:
    return {
        "id": "s1",
        "libraryId": "L1",
        "name": "Series",
        "path": "/data/s",
        "status": "READY",
        "createdAt": "2026-01-01T00:00:00Z",
        "oneshotBook": None,
        "mediaCount": 3,
        "readCount": 0,
        "metadata": {"title": "Series", "summary": "", "links": []},
        "tags": [{"name": "y"}],
    }
