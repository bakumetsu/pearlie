"""Stash GraphQL client for Pearlie library integration."""

from __future__ import annotations

import httpx

# ---------------------------------------------------------------------------
# Module-level GraphQL query / mutation constants
# ---------------------------------------------------------------------------

FIND_IMAGE_BY_CHECKSUM = (
    "query($v: String!) { findImages("
    "image_filter: {checksum: {value: $v, modifier: EQUALS}},"
    " filter: {per_page: 1}) { images { id } } }"
)

FIND_IMAGE_BY_PATH = (
    "query($v: String!) { findImages("
    "image_filter: {path: {value: $v, modifier: EQUALS}},"
    " filter: {per_page: 1}) { images { id } } }"
)

METADATA_SCAN = "mutation($p: [String!]) { metadataScan(input: {paths: $p}) }"

FIND_JOB = "query($id: ID!) { findJob(input: {id: $id}) { id status error } }"

FIND_TAGS = (
    "query($v: String!) { findTags("
    "tag_filter: {name: {value: $v, modifier: EQUALS}},"
    " filter: {per_page: 25}) { tags { id name } } }"
)

TAG_CREATE = "mutation($n: String!) { tagCreate(input: {name: $n}) { id } }"

IMAGE_UPDATE = (
    "mutation($i: ImageUpdateInput!) { imageUpdate(input: $i) { id } }"
)

LIBRARY_PATHS = (
    "query { configuration { general { stashes { path } } } }"
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class StashError(Exception):
    """Error raised by the Stash client."""

    def __init__(self, code: str, message: str, status: int = 502) -> None:
        self.code = code
        self.message = message
        self.status = status
        super().__init__(message)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class StashClient:
    """Stash GraphQL API client."""

    def __init__(self, base_url: str, api_key: str, client: httpx.Client | None = None) -> None:
        """Initialise the client.

        When *client* is ``None`` a new ``httpx.Client`` is created with the
        ApiKey header and a 15-second timeout.  An injected client (e.g. one
        using ``httpx.MockTransport`` in tests) is used as-is.
        """
        if client is None:
            self._client: httpx.Client = httpx.Client(
                base_url=base_url,
                headers={"ApiKey": api_key},
                timeout=15.0,
            )
        else:
            self._client = client

    # ------------------------------------------------------------------
    # Internal helper
    # ------------------------------------------------------------------

    def _gql(self, query: str, variables: dict | None = None) -> dict:
        """POST a GraphQL request and return the ``data`` dict.

        Raises ``StashError`` for network failures, auth problems,
        upstream HTTP errors, or GraphQL-level errors.
        """
        try:
            resp = self._client.post("/graphql", json={"query": query, "variables": variables})
        except httpx.HTTPError:
            raise StashError("upstream_error", "Stash is not reachable") from None

        if resp.status_code in (401, 403):
            raise StashError("upstream_auth", "Stash refused the API key", 502)
        if resp.status_code >= 400:
            raise StashError("upstream_error", f"Stash returned {resp.status_code}")

        try:
            body = resp.json()
        except ValueError:
            raise StashError("upstream_error", "Stash returned an invalid response") from None
        errors = body.get("errors")
        if errors:
            raise StashError("upstream_error", "Stash rejected the request")

        return body["data"]

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def find_image_by_checksum(self, md5: str) -> str | None:
        """Return the Stash image id matching *md5*, or ``None``."""
        data = self._gql(FIND_IMAGE_BY_CHECKSUM, {"v": md5})
        images = data["findImages"]["images"]
        return images[0]["id"] if images else None

    def find_image_by_path(self, path: str) -> str | None:
        """Return the Stash image id matching *path*, or ``None``."""
        data = self._gql(FIND_IMAGE_BY_PATH, {"v": path})
        images = data["findImages"]["images"]
        return images[0]["id"] if images else None

    def metadata_scan(self, path: str) -> str:
        """Trigger a metadata scan on *path*; return the job id."""
        data = self._gql(METADATA_SCAN, {"p": [path]})
        return data["metadataScan"]

    def find_job(self, job_id: str) -> dict:
        """Return the job dict, or ``{"status": "UNKNOWN", "error": None}`` if not found."""
        data = self._gql(FIND_JOB, {"id": job_id})
        job = data["findJob"]
        if job is None:
            return {"status": "UNKNOWN", "error": None}
        return job

    def find_tags(self, name: str) -> list[dict]:
        """Return all tag dicts matching *name* (up to 25)."""
        data = self._gql(FIND_TAGS, {"v": name})
        return data["findTags"]["tags"]

    def tag_create(self, name: str) -> str:
        """Create a tag with *name*; return the new tag id."""
        data = self._gql(TAG_CREATE, {"n": name})
        return data["tagCreate"]["id"]

    def image_update(self, image_id: str, tag_ids: list[str], urls: list[str]) -> None:
        """Update an image's tags and urls in Stash."""
        self._gql(
            IMAGE_UPDATE,
            {"i": {"id": image_id, "tag_ids": tag_ids, "urls": urls}},
        )

    def library_paths(self) -> list[str]:
        """Return all configured stash paths."""
        data = self._gql(LIBRARY_PATHS)
        stashes = data["configuration"]["general"]["stashes"] or []
        return [s["path"] for s in stashes]
