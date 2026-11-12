"""Danbooru source adapter."""

from collections.abc import Callable
from urllib.parse import urlparse

import httpx

from app.paging import clamp_page_size
from app.sources.auth import SiteAuth, build_auth
from app.sources.base import Post, Rating, SearchPage, SourceError
from app.sources.throttle import DEFAULT_PACE, Throttle

RATING_MAP: dict[str, Rating] = {
    "g": "general", "s": "sensitive", "q": "questionable", "e": "explicit"
}
TAG_TYPES = ("general", "artist", "copyright", "character", "meta")


def _retry_after(resp: httpx.Response) -> float | None:
    """Retry-After in seconds, or None when absent or not a number."""
    raw = resp.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def rating_filter(tag: str) -> tuple[bool, set[str]] | None:
    """Parse rating:x[,y] or -rating:x[,y] into (negated, ratings); None for other tags."""
    negated = tag.startswith("-")
    body = tag[1:] if negated else tag
    if not body.startswith("rating:"):
        return None
    values: set[str] = set()
    for v in body[len("rating:") :].split(","):
        v = v.strip().lower()
        if v in RATING_MAP:
            values.add(RATING_MAP[v])
        elif v in RATING_MAP.values():
            values.add(v)
        else:
            return None
    return negated, values


class Danbooru:
    """Adapter for the Danbooru image board."""

    id = "danbooru"
    target = "stash"
    file_hosts: tuple[str, ...]

    def __init__(
        self,
        client: httpx.Client | None = None,
        throttle: Throttle | None = None,
        base_url: str = "https://danbooru.donmai.us",
        tag_limit: int = 2,  # anonymous search cap
        page_size: int = 60,
        credentials: Callable[[], dict[str, str]] | None = None,
    ) -> None:
        self._client = client or httpx.Client(
            timeout=15.0, headers={"User-Agent": "Pearlie/0.1"}
        )
        self._throttle = throttle or Throttle(DEFAULT_PACE["danbooru"])
        self._base_url = base_url
        self.file_hosts = (urlparse(base_url).hostname or "", "cdn.donmai.us")
        self._tag_limit = tag_limit
        self._page_size = page_size
        self._credentials = credentials

    def _auth(self) -> SiteAuth:
        """Login + API key when both are stored; anonymous otherwise."""
        return build_auth("danbooru", self._credentials() if self._credentials else {})

    def _get(self, path: str, params: dict | None = None) -> dict | list:
        """Fetch a JSON resource from Danbooru."""
        self._throttle.wait()
        try:
            auth = self._auth()
            resp = self._client.get(
                self._base_url + path, params=params, headers=auth.headers, auth=auth.basic
            )
        except httpx.HTTPError:
            raise SourceError("upstream_error", "Danbooru is unreachable") from None
        self._throttle.report(resp.status_code, _retry_after(resp))
        status = resp.status_code
        if status == 404:
            raise SourceError("not_found", "Post not found", 404)
        if status == 429:
            raise SourceError("rate_limited", "Danbooru rate limit", 429)
        if status in (400, 422):
            raise SourceError("bad_request", "Danbooru rejected the search", status)
        if status >= 400:
            raise SourceError("upstream_error", f"Danbooru returned {status}", status)
        try:
            return resp.json()
        except Exception:
            raise SourceError("upstream_error", "Danbooru sent invalid JSON") from None

    def search(self, tags: list[str], page: int = 1, page_size: int | None = None) -> SearchPage:
        """Search posts by a list of tags."""
        size = clamp_page_size("danbooru", page_size or self._page_size)
        cleaned = [t.strip() for t in tags if t.strip()]
        server_tags = cleaned[: self._tag_limit]
        local_tags = cleaned[self._tag_limit :]
        query = " ".join(server_tags)
        data = self._get(
            "/posts.json",
            params={"tags": query, "page": page, "limit": size},
        )
        if not isinstance(data, list):
            raise SourceError("upstream_error", "Danbooru sent invalid JSON")
        raw_count = len(data)
        dropped = [t for t in local_tags if ":" in t and rating_filter(t) is None]
        posts: list[Post] = []
        for d in data:
            if not isinstance(d, dict) or "id" not in d:
                continue
            post = self._to_post(d)
            if self._matches(post, local_tags):
                posts.append(post)
        next_page = page + 1 if raw_count == size else None
        return SearchPage(posts=posts, page=page, next_page=next_page, dropped=dropped)

    def _matches(self, post: Post, local_tags: list[str]) -> bool:
        """Return True if the post passes all local tag filters."""
        post_tags: set[str] = set()
        for tag_list in post.tags.values():
            post_tags.update(tag_list)
        for t in local_tags:
            rf = rating_filter(t)
            if rf is not None:
                negated, ratings = rf
                hit = post.rating in ratings
                if hit == negated:
                    return False
                continue
            if ":" in t:
                continue
            negated = t.startswith("-")
            name = t.lstrip("-")
            has = name in post_tags
            if negated and has:
                return False
            if not negated and not has:
                return False
        return True

    def get_post(self, post_id: str) -> Post:
        """Fetch a single post by its numeric id."""
        pid = post_id.strip()
        if not pid.isdigit():
            raise SourceError("not_found", "Post not found", 404)
        data = self._get(f"/posts/{pid}.json")
        if not isinstance(data, dict) or "id" not in data:
            raise SourceError("upstream_error", "Danbooru sent invalid JSON")
        if data.get("success") is False:
            raise SourceError("not_found", "Post not found", 404)
        return self._to_post(data)

    def _to_post(self, d: dict) -> Post:
        """Convert a raw Danbooru dict into a Post model."""
        tags: dict[str, list[str]] = {}
        for t in TAG_TYPES:
            items = d.get(f"tag_string_{t}", "").split()
            if items:
                tags[t] = items
        return Post(
            post_id=str(d["id"]),
            md5=d.get("md5"),
            file_url=d.get("file_url") or d.get("large_file_url"),
            preview_url=d.get("preview_file_url"),
            width=d.get("image_width") or 0,
            height=d.get("image_height") or 0,
            rating=RATING_MAP.get(d.get("rating") or ""),
            tags=tags,
            source_url=f"{self._base_url}/posts/{d['id']}",
            source="danbooru",
        )
