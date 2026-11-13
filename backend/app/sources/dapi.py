"""Rule34 and Gelbooru source adapters (both speak the Gelbooru-style dapi)."""

import logging
from collections.abc import Callable
from urllib.parse import urlparse

import httpx

from app.paging import clamp_page_size
from app.sources.auth import SiteAuth, build_auth
from app.sources.base import Post, Rating, SearchPage, SourceError
from app.sources.danbooru import _retry_after
from app.sources.filters import dapi_filter_tags
from app.sources.throttle import DEFAULT_PACE, Throttle

# The API key travels in the query string, and httpx logs request URLs at INFO.
logging.getLogger("httpx").setLevel(logging.WARNING)

RATING_MAP: dict[str, Rating] = {
    "safe": "general",
    "general": "general",
    "sensitive": "sensitive",
    "questionable": "questionable",
    "explicit": "explicit",
}


def rating_filter(tag: str) -> tuple[bool, set[str]] | None:
    """Parse rating:x[,y] or -rating:x[,y] (safe counts as general); None for other tags."""
    negated = tag.startswith("-")
    body = tag[1:] if negated else tag
    if not body.startswith("rating:"):
        return None
    values: set[str] = set()
    for v in body[len("rating:") :].split(","):
        v = v.strip().lower()
        if v not in RATING_MAP:
            return None
        values.add(RATING_MAP[v])
    return negated, values


class DapiSource:
    """Adapter for a dapi site; subclasses set the site id, name and file hosts."""

    id = "rule34"
    name = "Rule34"
    target = "stash"
    default_base_url = "https://api.rule34.xxx"
    extra_file_hosts: tuple[str, ...] = ()
    md5_key = "hash"
    file_hosts: tuple[str, ...]

    def __init__(
        self,
        client: httpx.Client | None = None,
        throttle: Throttle | None = None,
        base_url: str | None = None,
        page_size: int = 60,
        credentials: Callable[[], dict[str, str]] | None = None,
    ) -> None:
        self._client = client or httpx.Client(
            timeout=15.0, headers={"User-Agent": "Pearlie/0.1"}
        )
        self._throttle = throttle or Throttle(DEFAULT_PACE[self.id])
        self._base_url = (base_url or self.default_base_url).rstrip("/")
        self.file_hosts = (urlparse(self._base_url).hostname or "", *self.extra_file_hosts)
        self._page_size = page_size
        self._credentials = credentials

    def _auth(self) -> SiteAuth:
        """User id + API key when both are stored; anonymous otherwise."""
        return build_auth(self.id, self._credentials() if self._credentials else {})

    def _get(self, params: dict[str, str | int]) -> list[dict]:
        """Query dapi and return the raw post dicts (empty list when none)."""
        self._throttle.wait()
        try:
            auth = self._auth()
            query: dict[str, str | int] = {
                "page": "dapi", "s": "post", "q": "index", "json": 1, **params, **auth.params,
            }
            resp = self._client.get(
                self._base_url + "/index.php", params=query, headers=auth.headers
            )
        except httpx.HTTPError:
            raise SourceError("upstream_error", f"{self.name} is unreachable") from None
        self._throttle.report(resp.status_code, _retry_after(resp))
        status = resp.status_code
        if status == 429:
            raise SourceError("rate_limited", f"{self.name} rate limit", 429)
        if status in (401, 403):
            raise SourceError("upstream_error", f"{self.name} rejected the credentials", status)
        if status >= 400:
            raise SourceError("upstream_error", f"{self.name} returned {status}", status)
        if not resp.content.strip():
            return []  # Rule34 answers an empty body when nothing matches
        try:
            data = resp.json()
        except Exception:
            raise SourceError("upstream_error", f"{self.name} sent invalid JSON") from None
        if isinstance(data, dict):  # Gelbooru wraps the list; a missing key means no posts
            data = data.get("post") or []
        if not isinstance(data, list):
            raise SourceError("upstream_error", f"{self.name} sent invalid JSON")
        return [d for d in data if isinstance(d, dict) and "id" in d]

    def search(
        self,
        tags: list[str],
        page: int = 1,
        page_size: int | None = None,
        order: str | None = None,
        rating: list[str] | None = None,
    ) -> SearchPage:
        """Search posts by tags; typed rating:x tags are filtered here, the rest go to the site.

        The order and rating filters are sent to the site as tags and checked here too.
        """
        size = clamp_page_size(self.id, page_size or self._page_size)
        cleaned = [t.strip() for t in tags if t.strip()]
        ratings = [t for t in cleaned if rating_filter(t) is not None]
        server_tags = [t for t in cleaned if t not in ratings]
        filter_tags, notices = dapi_filter_tags(self.id, order, rating or [])
        server_tags += filter_tags
        ratings += [t for t in filter_tags if rating_filter(t) is not None]
        data = self._get(
            {"tags": " ".join(server_tags), "pid": max(page, 1) - 1, "limit": size}
        )
        posts = [p for p in map(self._to_post, data) if self._rating_ok(p, ratings)]
        next_page = page + 1 if len(data) == size else None
        return SearchPage(posts=posts, page=page, next_page=next_page, notices=notices)

    @staticmethod
    def _rating_ok(post: Post, rating_tags: list[str]) -> bool:
        """True if the post passes every rating:x / -rating:x tag."""
        for t in rating_tags:
            rf = rating_filter(t)
            if rf is None:
                continue
            negated, ratings = rf
            if (post.rating in ratings) == negated:
                return False
        return True

    def get_post(self, post_id: str) -> Post:
        """Fetch a single post by its numeric id."""
        pid = post_id.strip()
        if not pid.isdigit():
            raise SourceError("not_found", "Post not found", 404)
        data = self._get({"id": pid})
        if not data:
            raise SourceError("not_found", "Post not found", 404)
        return self._to_post(data[0])

    def _to_post(self, d: dict) -> Post:
        """Convert a raw dapi dict into a Post model."""
        names = str(d.get("tags") or "").split()
        return Post(
            post_id=str(d["id"]),
            md5=d.get(self.md5_key) or d.get("md5") or d.get("hash"),
            file_url=d.get("file_url") or d.get("sample_url"),
            preview_url=d.get("preview_url") or d.get("sample_url"),
            sample_url=d.get("sample_url"),
            width=int(d.get("width") or 0),
            height=int(d.get("height") or 0),
            rating=RATING_MAP.get(str(d.get("rating") or "").lower()),
            tags={"general": names} if names else {},
            source_url=f"{self._base_url.replace('api.', '', 1)}/index.php"
            f"?page=post&s=view&id={d['id']}",
            source=self.id,
        )


class Rule34(DapiSource):
    """Adapter for rule34.xxx."""

    id = "rule34"
    name = "Rule34"
    default_base_url = "https://api.rule34.xxx"
    extra_file_hosts = (
        "rule34.xxx", "img.rule34.xxx", "wimg.rule34.xxx", "api-cdn.rule34.xxx",
        "api-cdn-mp4.rule34.xxx",
    )
    md5_key = "hash"


class Gelbooru(DapiSource):
    """Adapter for gelbooru.com (same dapi, md5 under its own key)."""

    id = "gelbooru"
    name = "Gelbooru"
    default_base_url = "https://gelbooru.com"
    extra_file_hosts = (
        "img1.gelbooru.com", "img2.gelbooru.com", "img3.gelbooru.com", "img4.gelbooru.com",
        "simg3.gelbooru.com", "simg4.gelbooru.com",
    )
    md5_key = "md5"
