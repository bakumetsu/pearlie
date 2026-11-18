"""Stump client: GraphQL (`/api/graphql`) plus the REST image routes, Bearer API key.

Pinned to Stump v0.1.13 (`docs/DESIGN.md`). Stump answers GraphQL errors with HTTP 200 and an
`errors` array; `Stump.gql` maps them to Pearlie error codes.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import httpx

from app.bookserver.base import BookServerError
from app.logs import install_http_hooks

PAGE_SIZE = 100
SERIES_BOOKS_PAGES = 100  # 100 x 100 = the 10,000 book cap of the series view
JOB_POLL_S = 1.0
JOB_TIMEOUT_S = 120.0

_JOB_DONE = "COMPLETED"
_JOB_FAILED = ("FAILED", "CANCELLED")

# Field lists in one place: the schema is "stable but subject to change" upstream.
_PAGE_INFO = "pageInfo { ... on OffsetPaginationInfo { totalPages totalItems } }"
_BOOK_FIELDS = (
    "id name path pages status createdAt deletedAt seriesId libraryId "
    "metadata { title summary writers links } tags { name } "
    "readProgress { page isCompleted }"
)
_SERIES_FIELDS = (
    "id name path createdAt deletedAt libraryId isOneshot mediaCount readCount "
    "metadata { title summary links } tags { name }"
)

Q_LIBRARIES = (
    "query Libraries($page: Int!) { libraries(pagination: {offset: {page: $page, "
    f"pageSize: {PAGE_SIZE}, zeroBased: false}}}}) {{ nodes {{ id name path "
    f"config {{ oneshotsDirectory }} }} {_PAGE_INFO} }} }}"
)
Q_SERIES_LIST = (
    "query SeriesList($filter: SeriesFilterInput, $order: [SeriesOrderBy!], $page: Int!, "
    "$size: Int!) { series(filter: $filter, orderBy: $order, pagination: {offset: "
    f"{{page: $page, pageSize: $size, zeroBased: false}}}}) {{ nodes {{ {_SERIES_FIELDS} }} "
    f"{_PAGE_INFO} }} }}"
)
Q_MEDIA_LIST = (
    "query MediaList($filter: MediaFilterInput, $order: [MediaOrderBy!], $page: Int!, "
    "$size: Int!) { media(filter: $filter, orderBy: $order, pagination: {offset: "
    f"{{page: $page, pageSize: $size, zeroBased: false}}}}) {{ nodes {{ {_BOOK_FIELDS} }} "
    f"{_PAGE_INFO} }} }}"
)
Q_SERIES_BY_ID = f"query SeriesById($id: ID!) {{ seriesById(id: $id) {{ {_SERIES_FIELDS} }} }}"
Q_MEDIA_BY_ID = f"query MediaById($id: ID!) {{ mediaById(id: $id) {{ {_BOOK_FIELDS} }} }}"
Q_MEDIA_BY_PATH = (
    f"query MediaByPath($path: String!) {{ mediaByPath(path: $path) {{ {_BOOK_FIELDS} }} }}"
)
Q_JOB = "query Job($id: ID!) { jobById(id: $id) { id status } }"

_NOT_FOUND_WORDS = ("not found", "notfound", "no such")


class StumpError(BookServerError):
    """Error raised by the Stump client."""


def _unreachable() -> StumpError:
    return StumpError("upstream_error", "Stump is not reachable", 502)


def _map_gql_errors(errors: list) -> StumpError:
    """One Pearlie error for a GraphQL `errors` array. Never echoes the server text."""
    text = " ".join(str(e.get("message", "")) if isinstance(e, dict) else str(e) for e in errors)
    if any(w in text.lower() for w in _NOT_FOUND_WORDS):
        return StumpError("not_found", "Not found", 404)
    return StumpError("upstream_error", "Stump returned an error", 502)


class Stump:
    """Stump API client (GraphQL + REST images)."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """An injected *client* (tests, `httpx.MockTransport`) is used as-is."""
        if client is None:
            self._client: httpx.Client = install_http_hooks(
                httpx.Client(
                    base_url=base_url,
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=15.0,
                ),
                "stump",
            )
        else:
            self._client = client
        self._sleep = sleep

    @staticmethod
    def _check(resp: httpx.Response) -> None:
        if resp.status_code == 404:
            raise StumpError("not_found", "Not found", 404)
        if resp.status_code >= 400:
            raise StumpError("upstream_error", f"Stump returned {resp.status_code}", 502)

    def gql(self, operation: str, query: str, variables: dict | None = None) -> dict:
        """Run one GraphQL operation; return its `data` object."""
        body = {"operationName": operation, "query": query, "variables": variables or {}}
        try:
            resp = self._client.post("/api/graphql", json=body)
        except httpx.HTTPError:
            raise _unreachable() from None
        self._check(resp)
        try:
            reply = resp.json()
        except ValueError:
            raise StumpError("upstream_error", "Stump sent an invalid answer", 502) from None
        if not isinstance(reply, dict):
            raise StumpError("upstream_error", "Stump sent an invalid answer", 502)
        if reply.get("errors"):
            raise _map_gql_errors(reply["errors"])
        data = reply.get("data")
        if not isinstance(data, dict):
            raise StumpError("upstream_error", "Stump sent an invalid answer", 502)
        return data

    # libraries

    def list_libraries(self) -> list[dict]:
        out: list[dict] = []
        for page in range(1, 51):
            conn = self.gql("Libraries", Q_LIBRARIES, {"page": page})["libraries"]
            out.extend(conn.get("nodes") or [])
            if page >= int((conn.get("pageInfo") or {}).get("totalPages") or 1):
                break
        return out

    # lists (offset pagination, 1-based)

    def list_series(self, page: int, size: int, filter_: dict | None, order: list) -> dict:
        v = {"filter": filter_, "order": order, "page": page, "size": size}
        return self.gql("SeriesList", Q_SERIES_LIST, v)["series"]

    def list_media(self, page: int, size: int, filter_: dict | None, order: list) -> dict:
        v = {"filter": filter_, "order": order, "page": page, "size": size}
        return self.gql("MediaList", Q_MEDIA_LIST, v)["media"]

    def get_series(self, id: str) -> dict:
        d = self.gql("SeriesById", Q_SERIES_BY_ID, {"id": id}).get("seriesById")
        if not d:
            raise StumpError("not_found", "Not found", 404)
        return d

    def get_media(self, id: str) -> dict:
        d = self.gql("MediaById", Q_MEDIA_BY_ID, {"id": id}).get("mediaById")
        if not d:
            raise StumpError("not_found", "Not found", 404)
        return d

    def media_by_path(self, path: str) -> dict | None:
        return self.gql("MediaByPath", Q_MEDIA_BY_PATH, {"path": path}).get("mediaByPath")

    # jobs

    def wait_job(self, job_id: str, timeout: float = JOB_TIMEOUT_S) -> None:
        """Poll `jobById` until COMPLETED. Raises on FAILED/CANCELLED or timeout."""
        deadline = time.monotonic() + timeout
        while True:
            job = self.gql("Job", Q_JOB, {"id": job_id}).get("jobById")
            status = (job or {}).get("status")
            if status == _JOB_DONE:
                return
            if status in _JOB_FAILED:
                raise StumpError("upstream_error", "Stump job failed", 502)
            if time.monotonic() >= deadline:
                raise StumpError("upstream_error", "Stump job timed out", 504)
            self._sleep(JOB_POLL_S)

    # REST images

    def open_image(self, path: str) -> httpx.Response:
        """Open a streaming GET for an image. The caller must close the response."""
        request = self._client.build_request("GET", path)
        try:
            resp = self._client.send(request, stream=True)
        except httpx.HTTPError:
            raise _unreachable() from None
        try:
            self._check(resp)
        except StumpError:
            resp.close()
            raise
        return resp
