"""Stump client: GraphQL (`/api/graphql`) plus the REST image routes, Bearer API key.

Pinned to Stump v0.1.13 (`docs/DESIGN.md`). Stump answers GraphQL errors with HTTP 200 and an
`errors` array; `Stump.gql` maps them to Pearlie error codes.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

import httpx

from app.bookserver.base import BookServerError
from app.logs import install_http_hooks, scrub

log = logging.getLogger(__name__)

PAGE_SIZE = 100
SERIES_BOOKS_PAGES = 100  # 100 x 100 = the 10,000 book cap of the series view
JOB_POLL_S = 1.0
JOB_TIMEOUT_S = 120.0

_JOB_DONE = "COMPLETED"
_JOB_FAILED = ("FAILED", "CANCELLED")

# Field lists in one place: the schema is "stable but subject to change" upstream.
_PAGE_INFO = "pageInfo { ... on OffsetPaginationInfo { totalPages totalItems } }"
_BOOK_FIELDS = (
    "id name path pages status createdAt seriesId libraryId "
    "metadata { title summary writers links } tags { name } "
    "readProgress { page } readHistory { completedAt }"
)
_SERIES_FIELDS = (
    "id name path status createdAt libraryId mediaCount readCount oneshotBook { id } "
    "metadata { title summary links } tags { name }"
)

Q_LIBRARIES = (
    "query Libraries($page: Int!) { libraries(pagination: {offset: {page: $page, "
    f"pageSize: {PAGE_SIZE}, zeroBased: false}}}}) {{ nodes {{ id name path "
    f"config {{ oneshotsDirectory }} }} {_PAGE_INFO} }} }}"
)
Q_SERIES_LIST = (
    "query SeriesList($filter: SeriesFilterInput!, $order: [SeriesOrderBy!], $page: Int!, "
    "$size: Int!) { series(filter: $filter, orderBy: $order, pagination: {offset: "
    f"{{page: $page, pageSize: $size, zeroBased: false}}}}) {{ nodes {{ {_SERIES_FIELDS} }} "
    f"{_PAGE_INFO} }} }}"
)
Q_MEDIA_LIST = (
    "query MediaList($filter: MediaFilterInput!, $order: [MediaOrderBy!], $page: Int!, "
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

M_SCAN_LIBRARY = "mutation ScanLibrary($id: ID!) { scanLibrary(id: $id) }"
Q_LAST_SCAN = (
    "query LastScan($id: ID!) { libraryById(id: $id) { scanHistory { jobId timestamp } } }"
)

# Write operations. Return type not verified live (T-330): the selection set of each mutation is
# set here, one line each. "" = scalar return (no selection); `{ __typename }` is valid for any
# object type and Pearlie reads nothing back. STUMP_MAP names no return type except scanLibrary
# (Boolean).
_SEL = " { __typename }"
RETURN_SELECTION = {
    "cleanLibrary": _SEL,  # guess: object (deleted counts)
    "setMediaTags": _SEL,  # guess: [Tag]
    "setSeriesTags": _SEL,  # guess: [Tag]
    "updateMediaMetadata": _SEL,  # guess: MediaMetadata
    "updateSeriesMetadata": _SEL,  # guess: SeriesMetadata
    "updateMediaProgress": _SEL,  # guess: ReadProgress object
    "finishMediaProgress": "",  # scalar in the Stump 0.1.13 web bundle: no selection
    "setMediaLockedFields": " { id }",  # Media; seen in the Stump 0.1.13 web bundle
    "setSeriesLockedFields": " { id }",  # Series; seen in the Stump 0.1.13 web bundle
}

M_CLEAN_LIBRARY = (
    f"mutation CleanLibrary($id: ID!) {{ cleanLibrary(id: $id){RETURN_SELECTION['cleanLibrary']} }}"
)
M_SET_MEDIA_TAGS = (
    "mutation SetMediaTags($id: ID!, $tags: [String!]!) "
    f"{{ setMediaTags(id: $id, tags: $tags){RETURN_SELECTION['setMediaTags']} }}"
)
M_SET_SERIES_TAGS = (
    "mutation SetSeriesTags($id: ID!, $tags: [String!]!) "
    f"{{ setSeriesTags(id: $id, tags: $tags){RETURN_SELECTION['setSeriesTags']} }}"
)
M_UPDATE_MEDIA_META = (
    "mutation UpdateMediaMetadata($id: ID!, $input: MediaMetadataInput!) "
    f"{{ updateMediaMetadata(id: $id, input: $input){RETURN_SELECTION['updateMediaMetadata']} }}"
)
M_UPDATE_SERIES_META = (
    "mutation UpdateSeriesMetadata($id: ID!, $input: SeriesMetadataInput!) "
    f"{{ updateSeriesMetadata(id: $id, input: $input){RETURN_SELECTION['updateSeriesMetadata']} }}"
)
M_UPDATE_PROGRESS = (
    "mutation UpdateMediaProgress($id: ID!, $input: MediaProgressInput!) "
    f"{{ updateMediaProgress(id: $id, input: $input){RETURN_SELECTION['updateMediaProgress']} }}"
)
M_FINISH_PROGRESS = (
    "mutation FinishMediaProgress($id: ID!) "
    f"{{ finishMediaProgress(id: $id){RETURN_SELECTION['finishMediaProgress']} }}"
)

# Locked-field names: sent as the variable `lockedFields: [MetadataField!]!` (enum values by name)
LOCKABLE = ("TITLE", "SUMMARY", "LINKS", "WRITERS", "TAGS")

_NOT_FOUND_WORDS = ("not found", "notfound", "no such")
_LOG_MAX = 500  # chars of the error summary in the log line


class StumpError(BookServerError):
    """Error raised by the Stump client."""


class _DbLocked(StumpError):
    """Stump answered with a SQLite "database is locked" GraphQL error."""


_PROGRESS_BACKOFF = (0.2, 0.5)  # waits before retry 1 and 2


def _unreachable() -> StumpError:
    return StumpError("upstream_error", "Stump is not reachable", 502)


def _error_text(errors: list) -> str:
    return " ".join(str(e.get("message", "")) if isinstance(e, dict) else str(e) for e in errors)


def _map_gql_errors(errors: list) -> StumpError:
    """One Pearlie error for a GraphQL `errors` array. Never echoes the server text."""
    text = _error_text(errors)
    if any(w in text.lower() for w in _NOT_FOUND_WORDS):
        return StumpError("not_found", "Not found", 404)
    return StumpError("upstream_error", "Stump returned an error", 502)


def _log_gql_errors(operation: str, errors: list) -> None:
    """One WARNING per failed operation: messages and paths, scrubbed and truncated."""
    parts: list[str] = []
    for e in errors:
        if isinstance(e, dict):
            path = ".".join(str(p) for p in e.get("path") or [])
            parts.append(f"{e.get('message', '')} [{path}]" if path else str(e.get("message", "")))
        else:
            parts.append(str(e))
    log.warning("Stump %s failed: %s", operation, scrub(" | ".join(parts))[:_LOG_MAX])


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

    def gql(
        self,
        operation: str,
        query: str,
        variables: dict | None = None,
        quiet_locked: bool = False,
    ) -> dict:
        """Run one GraphQL operation; return its `data` object.

        A "database is locked" error raises `_DbLocked`; with *quiet_locked* the caller logs it.
        """
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
            errors = reply["errors"]
            if "database is locked" in _error_text(errors).lower():
                if not quiet_locked:
                    _log_gql_errors(operation, errors)
                raise _DbLocked("upstream_error", "Stump returned an error", 502)
            _log_gql_errors(operation, errors)
            raise _map_gql_errors(errors)
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

    def list_series(self, page: int, size: int, filter_: dict, order: list) -> dict:
        v = {"filter": filter_, "order": order, "page": page, "size": size}
        return self.gql("SeriesList", Q_SERIES_LIST, v)["series"]

    def list_media(self, page: int, size: int, filter_: dict, order: list) -> dict:
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

    def scan_library(self, library_id: str, timeout: float = JOB_TIMEOUT_S) -> None:
        """Queue one library scan and wait for its job. `scanLibrary` returns only a Boolean,
        so the job id comes from `libraryById.scanHistory` (the newest entry)."""
        self.gql("ScanLibrary", M_SCAN_LIBRARY, {"id": library_id})
        lib = self.gql("LastScan", Q_LAST_SCAN, {"id": library_id}).get("libraryById")
        if not lib:
            raise StumpError("not_found", "Not found", 404)
        last = max(
            lib.get("scanHistory") or [], key=lambda r: str(r.get("timestamp") or ""), default={}
        )
        job_id = last.get("jobId")
        if job_id:
            self.wait_job(str(job_id), timeout)

    # writes (T-329)

    def clean_library(self, library_id: str) -> None:
        """Drop the library's MISSING entities from Stump's database. Files are not touched."""
        self.gql("CleanLibrary", M_CLEAN_LIBRARY, {"id": library_id})

    def set_tags(self, kind: str, id: str, tags: list[str]) -> None:
        if kind == "series":
            self.gql("SetSeriesTags", M_SET_SERIES_TAGS, {"id": id, "tags": tags})
        else:
            self.gql("SetMediaTags", M_SET_MEDIA_TAGS, {"id": id, "tags": tags})

    def update_metadata(self, kind: str, id: str, fields: dict) -> None:
        if kind == "series":
            self.gql("UpdateSeriesMetadata", M_UPDATE_SERIES_META, {"id": id, "input": fields})
        else:
            self.gql("UpdateMediaMetadata", M_UPDATE_MEDIA_META, {"id": id, "input": fields})

    def lock_fields(self, kind: str, id: str, fields: list[str]) -> None:
        """Lock metadata fields so a rescan does not overwrite them."""
        names = [f for f in fields if f in LOCKABLE]
        if not names:
            return
        arg, op, name = ("mediaId", "setMediaLockedFields", "SetMediaLockedFields")
        if kind == "series":
            arg, op, name = ("seriesId", "setSeriesLockedFields", "SetSeriesLockedFields")
        query = (
            f"mutation {name}(${arg}: ID!, $lockedFields: [MetadataField!]!) "
            f"{{ {op}({arg}: ${arg}, lockedFields: $lockedFields){RETURN_SELECTION[op]} }}"
        )
        self.gql(name, query, {arg: id, "lockedFields": names})

    def update_progress(self, media_id: str, page: int) -> None:
        variables = {"id": media_id, "input": {"paged": {"page": page}}}
        # Only this save retries: Stump's SQLite is sometimes busy (T-347).
        tries = len(_PROGRESS_BACKOFF) + 1
        for attempt in range(tries):
            try:
                self.gql("UpdateMediaProgress", M_UPDATE_PROGRESS, variables, quiet_locked=True)
                return
            except _DbLocked:
                if attempt == tries - 1:
                    log.warning(
                        "Stump UpdateMediaProgress failed: database is locked (%d tries)", tries
                    )
                    raise
                self._sleep(_PROGRESS_BACKOFF[attempt])

    def finish_progress(self, media_id: str) -> None:
        self.gql("FinishMediaProgress", M_FINISH_PROGRESS, {"id": media_id})

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
