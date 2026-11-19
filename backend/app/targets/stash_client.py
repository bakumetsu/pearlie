"""Stash GraphQL client for Pearlie library integration."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urljoin, urlparse

import httpx

from app.logs import install_http_hooks

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

FIND_SCENE_BY_PATH = (
    "query($v: String!) { findScenes("
    "scene_filter: {path: {value: $v, modifier: EQUALS}},"
    " filter: {per_page: 1}) { scenes { id } } }"
)

METADATA_SCAN = "mutation($p: [String!]) { metadataScan(input: {paths: $p}) }"

FIND_JOB = "query($id: ID!) { findJob(input: {id: $id}) { id status error } }"

FIND_TAGS = (
    "query($v: String!) { findTags("
    "tag_filter: {name: {value: $v, modifier: EQUALS}},"
    " filter: {per_page: 25}) { tags { id name } } }"
)

TAG_CREATE = "mutation($n: String!) { tagCreate(input: {name: $n}) { id } }"

IMAGE_UPDATE = "mutation($i: ImageUpdateInput!) { imageUpdate(input: $i) { id } }"

SCENE_UPDATE = "mutation($i: SceneUpdateInput!) { sceneUpdate(input: $i) { id } }"

LIBRARY_PATHS = "query { configuration { general { stashes { path } } } }"

IMAGE_FIELDS = (
    "id title rating100 created_at urls tags { name } "
    "visual_files { ... on ImageFile { basename width height size } "
    "... on VideoFile { basename width height size } }"
)
# date and studio { name } are to be confirmed in the Stash playground
SCENE_FIELDS = (
    "id title rating100 created_at urls tags { name } date studio { name } "
    "files { basename width height duration video_codec size }"
)
LIST_IMAGES = (
    "query($f: FindFilterType) { findImages(filter: $f) "
    "{ count megapixels filesize images { " + IMAGE_FIELDS + " } } }"
)
LIST_FOLDER_IMAGES = (
    "query($v: String!, $page: Int!, $n: Int!) { findImages("
    "image_filter: {path: {value: $v, modifier: INCLUDES}},"
    ' filter: {page: $page, per_page: $n, sort: "id", direction: ASC})'
    " { count images { id visual_files { ... on ImageFile { path basename } } } } }"
)
GET_IMAGE = "query($id: ID!) { findImage(id: $id) { " + IMAGE_FIELDS + " } }"
LIST_SCENES = (
    "query($f: FindFilterType) { findScenes(filter: $f) "
    "{ count filesize scenes { " + SCENE_FIELDS + " } } }"
)
GET_SCENE = (
    "query($id: ID!) { findScene(id: $id) { "
    + SCENE_FIELDS
    + " sceneStreams { url mime_type label } } }"
)
_FILE = "path size zip_file { id } fingerprints { type value }"
TRASH_IMAGE = (
    "query($id: ID!) { findImage(id: $id) { id title rating100 organized date urls "
    "tags { name } performers { name } studio { name } galleries { id title } "
    "visual_files { ... on ImageFile { " + _FILE + " } ... on VideoFile { " + _FILE + " } } } }"
)
TRASH_SCENE = (
    "query($id: ID!) { findScene(id: $id) { id title rating100 organized date details urls "
    "tags { name } performers { name } studio { name } files { " + _FILE + " } "
    "scene_markers { title seconds primary_tag { name } tags { name } } "
    "stash_ids { endpoint stash_id } } }"
)
IMAGE_DESTROY = "mutation($i: ImageDestroyInput!) { imageDestroy(input: $i) }"
SCENE_DESTROY = "mutation($i: SceneDestroyInput!) { sceneDestroy(input: $i) }"
FIND_PERFORMER = (
    "query($v: String!) { findPerformers(performer_filter: {name: {value: $v, "
    "modifier: EQUALS}}, filter: {per_page: 5}) { performers { id name } } }"
)
PERFORMER_CREATE = "mutation($n: String!) { performerCreate(input: {name: $n}) { id } }"
FIND_STUDIO = (
    "query($v: String!) { findStudios(studio_filter: {name: {value: $v, "
    "modifier: EQUALS}}, filter: {per_page: 5}) { studios { id name } } }"
)
STUDIO_CREATE = "mutation($n: String!) { studioCreate(input: {name: $n}) { id } }"
FIND_GALLERY = "query($id: ID!) { findGallery(id: $id) { id } }"
MARKER_CREATE = "mutation($i: SceneMarkerCreateInput!) { sceneMarkerCreate(input: $i) { id } }"
GET_SCENE_PREVIEW = "query($id: ID!) { findScene(id: $id) { paths { preview } } }"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


_REDIRECTS = (301, 302, 303, 307, 308)
_MAX_HOPS = 2


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
            self._client: httpx.Client = install_http_hooks(
                httpx.Client(
                    base_url=base_url,
                    headers={"ApiKey": api_key},
                    timeout=15.0,
                ),
                "stash",
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

    def find_scene_by_path(self, path: str) -> str | None:
        """Return the Stash scene id matching *path*, or ``None``."""
        data = self._gql(FIND_SCENE_BY_PATH, {"v": path})
        scenes = data["findScenes"]["scenes"]
        return scenes[0]["id"] if scenes else None

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

    def find_tags_many(self, names: list[str]) -> dict[str, list[dict]]:
        """Look up several tag names in one aliased GraphQL request per 20 names."""
        found: dict[str, list[dict]] = {}
        for i in range(0, len(names), 20):
            chunk = names[i : i + 20]
            decl = ", ".join(f"$v{k}: String!" for k in range(len(chunk)))
            body = " ".join(
                f"t{k}: findTags(tag_filter: {{name: {{value: $v{k}, modifier: EQUALS}}}},"
                " filter: {per_page: 25}) { tags { id name } }"
                for k in range(len(chunk))
            )
            data = self._gql(
                f"query({decl}) {{ {body} }}", {f"v{k}": n for k, n in enumerate(chunk)}
            )
            for k, n in enumerate(chunk):
                found[n] = data[f"t{k}"]["tags"]
        return found

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

    def resolve_tag_ids(self, names: list[str]) -> list[str]:
        """Resolve tag *names* to Stash tag ids, creating any missing tags."""
        ids: list[str] = []
        seen: set[str] = set()
        hits = self.find_tags_many(list(dict.fromkeys(names)))
        for name in names:
            tags = hits[name]
            tag_id = None
            for t in tags:
                if t["name"].casefold() == name.casefold():
                    tag_id = t["id"]
                    break
            if tag_id is None:
                tag_id = self.tag_create(name)
            if tag_id not in seen:
                seen.add(tag_id)
                ids.append(tag_id)
        return ids

    def update_item(self, kind: str, id: str, fields: dict) -> None:
        """Apply *fields* to a single image or scene in Stash."""
        query = IMAGE_UPDATE if kind == "images" else SCENE_UPDATE
        self._gql(query, {"i": {"id": id, **fields}})

    def get_trash_entity(self, kind: str, id: str) -> dict | None:
        """Everything a restore needs from an image or scene, or ``None``."""
        if kind == "image":
            return self._gql(TRASH_IMAGE, {"id": id})["findImage"]
        return self._gql(TRASH_SCENE, {"id": id})["findScene"]

    def destroy_item(self, kind: str, id: str) -> None:
        """Drop the entry only; the file is already out of the library."""
        flags = {"id": id, "delete_file": False, "delete_generated": True}
        if kind == "image":
            self._gql(IMAGE_DESTROY, {"i": flags})
        else:
            self._gql(SCENE_DESTROY, {"i": flags})

    def named_id(self, what: str, name: str) -> str:
        """Id of the performer or studio called *name*; created when missing."""
        find, key, create = (
            (FIND_PERFORMER, "performers", PERFORMER_CREATE)
            if what == "performer"
            else (FIND_STUDIO, "studios", STUDIO_CREATE)
        )
        data = self._gql(find, {"v": name})
        for hit in data["find" + key.capitalize()][key]:
            if hit["name"].casefold() == name.casefold():
                return hit["id"]
        return self._gql(create, {"n": name})[what + "Create"]["id"]

    def gallery_exists(self, id: str) -> bool:
        return self._gql(FIND_GALLERY, {"id": id})["findGallery"] is not None

    def marker_create(self, fields: dict) -> None:
        self._gql(MARKER_CREATE, {"i": fields})

    def library_paths(self) -> list[str]:
        """Return all configured stash paths."""
        data = self._gql(LIBRARY_PATHS)
        stashes = data["configuration"]["general"]["stashes"] or []
        return [s["path"] for s in stashes]

    def list_images(
        self, page: int, per_page: int, q: str, sort: str, direction: str
    ) -> tuple[list[dict], int, dict]:
        """Return a page of images, the total count, and aggregate stats."""
        data = self._gql(
            LIST_IMAGES,
            {
                "f": {
                    "page": page,
                    "per_page": per_page,
                    "q": q,
                    "sort": sort,
                    "direction": direction,
                }
            },
        )
        r = data["findImages"]
        agg = {"megapixels": r.get("megapixels"), "size_bytes": r.get("filesize")}
        return r["images"], r["count"], agg

    def list_folder_images(self, folder: str, page: int, per_page: int) -> tuple[list[dict], int]:
        """Return one page of images whose path contains *folder*, and the total count."""
        data = self._gql(LIST_FOLDER_IMAGES, {"v": folder, "page": page, "n": per_page})
        r = data["findImages"]
        return r["images"], r["count"]

    def get_image(self, id: str) -> dict | None:
        """Return the image dict for *id*, or ``None``."""
        data = self._gql(GET_IMAGE, {"id": id})
        return data["findImage"]

    def list_scenes(
        self, page: int, per_page: int, q: str, sort: str, direction: str
    ) -> tuple[list[dict], int, dict]:
        """Return a page of scenes, the total count, and aggregate stats."""
        data = self._gql(
            LIST_SCENES,
            {
                "f": {
                    "page": page,
                    "per_page": per_page,
                    "q": q,
                    "sort": sort,
                    "direction": direction,
                }
            },
        )
        r = data["findScenes"]
        agg = {"megapixels": None, "size_bytes": r.get("filesize")}
        return r["scenes"], r["count"], agg

    def get_scene(self, id: str) -> dict | None:
        """Return the scene dict (with streams) for *id*, or ``None``."""
        data = self._gql(GET_SCENE, {"id": id})
        return data["findScene"]

    def scene_preview_path(self, id: str) -> str | None:
        """Return the preview path+query from Stash, or ``None``."""
        data = self._gql(GET_SCENE_PREVIEW, {"id": id})
        scene = data.get("findScene")
        if not scene:
            return None
        paths = scene.get("paths")
        if not paths:
            return None
        preview = paths.get("preview")
        if not preview:
            return None
        parsed = urlparse(preview)
        query_params = parse_qsl(parsed.query, keep_blank_values=True)
        filtered = [(k, v) for k, v in query_params if k.lower() != "apikey"]
        query = urlencode(filtered)
        if query:
            return f"{parsed.path}?{query}"
        return parsed.path

    def open_media(
        self,
        path: str,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> httpx.Response:
        """Open a streamed media response from Stash. Caller must close it."""
        limit = httpx.USE_CLIENT_DEFAULT if timeout is None else timeout
        request = self._client.build_request(
            "GET", path, params=params, headers=headers, timeout=limit
        )
        origin = request.url
        hops = 0
        while True:
            try:
                response = self._client.send(request, stream=True, follow_redirects=False)
            except httpx.HTTPError as exc:
                raise StashError("upstream_error", "Stash is not reachable") from exc
            if response.status_code not in _REDIRECTS:
                break
            location = response.headers.get("location")
            response.close()
            if not location or hops >= _MAX_HOPS:
                raise StashError("upstream_error", "Stash redirect not followed")
            target = httpx.URL(urljoin(str(request.url), location))
            if (target.scheme, target.host, target.port) != (
                origin.scheme,
                origin.host,
                origin.port,
            ):
                # Never send the ApiKey to another host.
                raise StashError("upstream_error", "Stash redirect not followed")
            hops += 1
            request = self._client.build_request("GET", target, headers=headers, timeout=limit)

        status = response.status_code
        if status == 404:
            response.close()
            raise StashError("not_found", "Media not found", 404)
        if status in (401, 403):
            response.close()
            raise StashError("upstream_auth", "Stash refused the API key", 502)
        if status >= 400 and status != 416:
            response.close()
            raise StashError("upstream_error", f"Stash returned {status}")
        return response
