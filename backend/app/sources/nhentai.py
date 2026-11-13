"""nhentai source adapter (search and gallery metadata; saving to Komga is a later step)."""

import re
from collections.abc import Callable

import httpx

from app.logs import install_http_hooks
from app.paging import clamp_page_size
from app.sources.auth import SiteAuth, build_auth
from app.sources.base import Post, SearchPage, SourceError
from app.sources.danbooru import _retry_after
from app.sources.throttle import DEFAULT_PACE, Throttle

API_HOST = "nhentai.net"
# Numbered CDN mirrors (i, i3, t5, ...); the one place that says which hosts hold images.
CDN_HOST = re.compile(r"^[it]\d?\.nhentai\.net$")
TYPES = ("artist", "group", "parody", "character", "language", "category")
QUERY_TYPES = (*TYPES, "tag")
IMG_HOST = "https://i.nhentai.net"
THUMB_HOST = "https://t.nhentai.net"


def _term(token: str) -> str:
    """One search token in nhentai syntax: type:"name with spaces", negation kept."""
    neg = "-" if token.startswith("-") else ""
    body = token[1:] if neg else token
    kind, sep, name = body.partition(":")
    if sep and kind in QUERY_TYPES:
        prefix = f"{kind}:"
    else:
        prefix, name = "", body
    name = name.replace("_", " ").strip()
    return f'{neg}{prefix}"{name}"' if name else ""


def _int(value: object) -> int:
    """A size field as an int; anything that is not a whole number counts as 0."""
    try:
        return int(value)  # type: ignore[call-overload]
    except (ValueError, TypeError):
        return 0


def _obj(value: object) -> dict:
    """The value when it is a JSON object, else an empty dict."""
    return value if isinstance(value, dict) else {}


def _list(value: object) -> list:
    return value if isinstance(value, list) else []


def build_query(tags: list[str]) -> str:
    """Space-joined nhentai query from the search box tokens (empty when none)."""
    return " ".join(t for t in (_term(x) for x in tags if x.strip()) if t)


class NHentai:
    """Adapter for nhentai.net; galleries are saved into Komga."""

    id = "nhentai"
    name = "nhentai"
    target = "komga"
    default_base_url = "https://nhentai.net"
    file_hosts: tuple[str, ...]

    def __init__(
        self,
        client: httpx.Client | None = None,
        throttle: Throttle | None = None,
        base_url: str | None = None,
        page_size: int = 25,
        credentials: Callable[[], dict[str, str]] | None = None,
    ) -> None:
        self._client = client or install_http_hooks(httpx.Client(timeout=15.0), self.id)
        self._throttle = throttle or Throttle(DEFAULT_PACE[self.id], site=self.id)
        self._base_url = (base_url or self.default_base_url).rstrip("/")
        self.file_hosts = (API_HOST, "i.nhentai.net", "t.nhentai.net")
        self._page_size = page_size
        self._credentials = credentials

    def _auth(self) -> SiteAuth:
        return build_auth(self.id, self._credentials() if self._credentials else {})

    def page_urls(self, post: Post) -> list[str]:
        """Image URL of every page, in order (CDN host, never the API host)."""
        media_id = str(post.extra.get("media_id") or "")
        raw = post.extra.get("page_exts")
        exts = raw if isinstance(raw, list) else []
        if not media_id.isalnum():
            return []
        return [f"{IMG_HOST}/galleries/{media_id}/{n}.{e}" for n, e in enumerate(exts, 1)]

    def page_headers(self) -> dict[str, str]:
        """Headers for page downloads: User-Agent only, the Cookie stays on the API host."""
        return {k: v for k, v in self._auth().headers.items() if k.lower() != "cookie"}

    def _get(self, path: str, params: dict[str, str | int] | None = None) -> dict:
        """GET one API path (Cookie goes to the API host only) and return the JSON object."""
        self._throttle.wait()
        try:
            resp = self._client.get(
                self._base_url + path, params=params, headers=self._auth().headers
            )
        except httpx.HTTPError:
            raise SourceError("upstream_error", "nhentai is unreachable") from None
        self._throttle.report(resp.status_code, _retry_after(resp))
        status = resp.status_code
        if status == 404:
            raise SourceError("not_found", "Gallery not found", 404)
        if status == 429:
            raise SourceError("rate_limited", "nhentai rate limit", 429)
        if status in (403, 503):
            raise SourceError(
                "upstream_error",
                "nhentai blocked the request (check the cookie and User-Agent)",
                status,
            )
        if status >= 400:
            raise SourceError("upstream_error", f"nhentai returned {status}", status)
        try:
            data = resp.json()
        except Exception:
            raise SourceError("upstream_error", "nhentai sent invalid JSON") from None
        if not isinstance(data, dict):
            raise SourceError("upstream_error", "nhentai sent invalid JSON")
        return data

    def search(
        self,
        tags: list[str],
        page: int = 1,
        page_size: int | None = None,
        order: str | None = None,
        rating: list[str] | None = None,
    ) -> SearchPage:
        """Search galleries; the site's page size is fixed, page_size only clamps."""
        clamp_page_size(self.id, page_size or self._page_size)
        page = max(page, 1)
        query = build_query(tags)
        if query:
            data = self._get("/api/v2/search", {"query": query, "page": page})
        else:
            data = self._get("/api/v2/galleries", {"page": page})
        rows = data.get("result")
        if not isinstance(rows, list):
            raise SourceError("upstream_error", "nhentai sent invalid JSON")
        posts = []
        for d in rows:
            if not isinstance(d, dict) or "id" not in d:
                continue
            try:
                posts.append(self._to_post(d))
            except (ValueError, TypeError):
                continue  # one odd gallery must not fail the page
        pages = data.get("num_pages")
        pages = pages if isinstance(pages, int) else None
        per_page = data.get("per_page")
        total = pages * per_page if pages is not None and isinstance(per_page, int) else None
        next_page = page + 1 if pages is not None and page < pages else None
        return SearchPage(posts=posts, page=page, next_page=next_page, total=total, pages=pages)

    def get_post(self, post_id: str) -> Post:
        """Fetch one gallery by its numeric id."""
        pid = post_id.strip()
        if not pid.isdigit():
            raise SourceError("not_found", "Gallery not found", 404)
        return self._to_post(self._get(f"/api/v2/galleries/{pid}"))

    # --- API parsing: the only place that knows the nhentai JSON shape ---

    @staticmethod
    def _parse_pages(d: dict) -> tuple[list[str], dict]:
        """(page extensions in order, cover dict) from a v2 gallery.

        A full gallery has `pages` and `cover`; a list/search row has neither and only a
        `thumbnail` path, so it gives no pages and the thumbnail as the cover.
        """
        exts = []
        for p in _list(d.get("pages")):
            path = str(_obj(p).get("path") or "")
            ext = path.rpartition(".")[2] if "." in path else ""
            exts.append(ext if ext.isalnum() else "jpg")
        cover = _obj(d.get("cover"))
        if not cover.get("path"):
            cover = {
                "path": d.get("thumbnail"),
                "width": d.get("thumbnail_width"),
                "height": d.get("thumbnail_height"),
            }
        return exts, cover

    def _to_post(self, d: dict) -> Post:
        exts, cover = self._parse_pages(d)
        media_id = str(d.get("media_id") or "")
        title = _obj(d.get("title"))
        grouped: dict[str, list[str]] = {}
        for t in _list(d.get("tags")):
            if not isinstance(t, dict) or not t.get("name"):
                continue
            kind = str(t.get("type"))
            grouped.setdefault(kind if kind in TYPES else "general", []).append(str(t["name"]))
        path = str(cover.get("path") or "")
        cover_url = (
            f"{THUMB_HOST}/{path.lstrip('/')}"
            if path.startswith("galleries/") and ".." not in path
            else None
        )
        count = d.get("num_pages")
        return Post(
            source=self.id,
            post_id=str(d["id"]),
            preview_url=cover_url,
            sample_url=cover_url,
            width=_int(cover.get("width")),
            height=_int(cover.get("height")),
            tags=grouped,
            source_url=f"{self._base_url}/g/{d['id']}/",
            title=(
                title.get("pretty")
                or title.get("english")
                or title.get("japanese")
                or d.get("english_title")
                or d.get("japanese_title")
                or None
            ),
            page_count=count if isinstance(count, int) else (len(exts) or None),
            extra={"media_id": media_id, "page_exts": exts},
        )
