"""nhentai source adapter (search and gallery metadata; saving to Stump is a later step)."""

import hashlib
import logging
import re
import threading
import time
from collections import deque
from collections.abc import Callable
from urllib.parse import urlparse

import httpx

from app.logs import install_http_hooks
from app.paging import clamp_page_size
from app.sources.auth import SiteAuth, build_auth
from app.sources.base import Post, SearchPage, SourceError
from app.sources.danbooru import _retry_after
from app.sources.filters import NHENTAI_SORTS
from app.sources.query_terms import TITLE_MAX
from app.sources.throttle import DEFAULT_PACE, MAX_WAIT, Throttle

API_HOST = "nhentai.net"
# Numbered CDN mirrors (i, i3, t5, ...); the one place that says which hosts hold images.
CDN_HOST = re.compile(r"^[it]\d?\.nhentai\.net$")
TYPES = ("artist", "group", "parody", "character", "language", "category")
QUERY_TYPES = (*TYPES, "tag")
IMG_HOST = "https://i.nhentai.net"
THUMB_HOST = "https://t.nhentai.net"
# Tag id -> (type, name) lives this long; rows carry ids only, galleries carry both.
TAG_TTL = 24 * 3600.0
MAX_QUEUE_WAIT = 8.0  # longest a call waits for its slot before it fails with rate_limited
SLOW_CALL_MS = 3000
CHECK_EVERY = 600.0  # seconds between GET /user key checks while the key is ok or unchecked
RATE_WINDOW = 60.0  # wait when X-RateLimit-Remaining is 0 and the site names no window
# Documented per-IP limits with a margin: (guest, key) seconds between calls of a bucket.
BUCKET_PACE: dict[str, tuple[float, float]] = {
    "search": (6.5, 3.2),
    "list": (6.5, 3.2),
    "detail": (3.2, 1.5),
    "related": (3.2, 1.5),
}
DOWNLOAD_LIMIT = 7  # documented: 7 download links per 5 min per user
DOWNLOAD_WINDOW = 300.0
_API_PREFIX = "/api/v2"
_DETAIL = re.compile(r"^/galleries/\d+$")
_RELATED = re.compile(r"^/galleries/\d+/related$")
_DOWNLOAD = re.compile(r"^/galleries/\d+/download$")
_log = logging.getLogger(__name__)


def bucket_of(path: str) -> str:
    """Pace bucket of an API path: search, list, detail, related, user or other."""
    p = path[len(_API_PREFIX) :] if path.startswith(_API_PREFIX) else path
    p = p.rstrip("/") or "/"
    if p == "/search" or p.startswith("/search/"):
        return "search"
    if p == "/galleries":
        return "list"
    if _DETAIL.match(p):
        return "detail"
    if _RELATED.match(p):
        return "related"
    if p == "/user":
        return "user"
    if _DOWNLOAD.match(p):
        return "download"
    return "other"


def _term(token: str) -> str:
    """One search token in nhentai syntax: type:"name with spaces", negation kept."""
    neg = "-" if token.startswith("-") else ""
    body = token[1:] if neg else token
    kind, sep, name = body.partition(":")
    if sep and kind in QUERY_TYPES:
        prefix = f"{kind}:"
    elif sep and kind == "title":
        # nhentai has no title: prefix; a quoted bare term searches the title.
        prefix, name = "", name[:TITLE_MAX]
    else:
        prefix, name = "", body
    name = name.replace("_", " ").replace('"', " ").strip()
    return f'{neg}{prefix}"{name}"' if name else ""


def _is_noise_tag(name: str) -> bool:
    """The site's 'definition revised' marker is not a content tag; drop it."""
    return "definition revised" in name.lower()


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


REJECT_TERM_CAP = 10


def reject_terms(reject: list[str], limit: int = REJECT_TERM_CAP) -> list[str]:
    """Search tokens (`-tag:name`) that let the site drop plain reject entries server-side.

    Wildcard entries and scopes nhentai does not know are skipped; the grid check still
    hides what the site returns.
    """
    out: list[str] = []
    for entry in reject:
        scope, sep, name = entry.partition(":")
        if not sep:
            scope, name = "tag", entry
        elif scope in ("general", ""):
            scope = "tag"
        name = name.strip()
        if scope not in QUERY_TYPES or not name or any(c in name for c in '*?"'):
            continue
        out.append(f"-{scope}:{name}")
        if len(out) >= limit:
            break
    return out


def build_query(tags: list[str]) -> str:
    """Space-joined nhentai query from the search box tokens (empty when none)."""
    terms = [t for t in (_term(x) for x in tags if x.strip()) if t]
    if terms and all(t.startswith("-") for t in terms):
        terms.append("pages:>0")  # nhentai needs one positive term; this matches every gallery
    return " ".join(terms)


class NHentai:
    """Adapter for nhentai.net; galleries are saved into Stump."""

    id = "nhentai"
    name = "nhentai"
    target = "stump"
    default_base_url = "https://nhentai.net"
    file_hosts: tuple[str, ...]

    def __init__(
        self,
        client: httpx.Client | None = None,
        throttle: Throttle | None = None,
        base_url: str | None = None,
        page_size: int = 25,
        credentials: Callable[[], dict[str, str]] | None = None,
        paced: bool = True,
    ) -> None:
        self._client = client or install_http_hooks(
            httpx.Client(timeout=httpx.Timeout(15.0, connect=5.0)), self.id
        )
        self._throttle = throttle or Throttle(DEFAULT_PACE[self.id], site=self.id)
        self._base_url = (base_url or self.default_base_url).rstrip("/")
        self.file_hosts = (API_HOST, "i.nhentai.net", "t.nhentai.net")
        self._page_size = page_size
        self._credentials = credentials
        self._paced = paced  # False: no documented-limit floor (tests with a fake clock)
        self._key_lock = threading.Lock()
        self._key_id = ""  # fingerprint of the key the state belongs to; never the key
        self._key_state = "unset"
        self._key_reason = ""
        self._last_check = 0.0
        self._last_403_check = 0.0
        self._download_times: deque[float] = deque()
        self._spawn: Callable[[Callable[[], object]], None] = self._spawn_thread
        self._tag_names: dict[int, tuple[str, str, float]] = {}
        self._warned_unknown = False

    def _learn_tag(self, tag_id: object, kind: str, name: str) -> None:
        """Remember one tag id's type and name (no site call; fed by full galleries)."""
        if isinstance(tag_id, int) and not isinstance(tag_id, bool):
            self._tag_names[tag_id] = (kind, name, time.monotonic())

    def _row_tags(self, ids: list, grouped: dict[str, list[str]]) -> None:
        """Add the known names of a row's tag ids to `grouped`; unknown ids stay out."""
        now = time.monotonic()
        unknown = False
        for tid in ids:
            hit = self._tag_names.get(tid) if isinstance(tid, int) else None
            if hit is None or now - hit[2] > TAG_TTL:
                unknown = True
                continue
            grouped.setdefault(hit[0], []).append(hit[1])
        if unknown and not self._warned_unknown:
            self._warned_unknown = True
            _log.info("nhentai: grid rows carry tag ids not seen yet; rules see known tags only")

    def _auth(self) -> SiteAuth:
        return build_auth(self.id, self._credentials() if self._credentials else {})

    @staticmethod
    def _spawn_thread(fn: Callable[[], object]) -> None:
        threading.Thread(target=fn, name="nhentai-key-check", daemon=True).start()

    def _sync_key(self) -> str:
        """Compare the stored key with the one the state belongs to; reset on change."""
        key = (self._credentials() if self._credentials else {}).get("api_key", "")
        ident = hashlib.sha256(key.encode()).hexdigest() if key else ""
        with self._key_lock:
            if ident != self._key_id:
                self._key_id = ident
                self._key_state = "unchecked" if key else "unset"
                self._key_reason = ""
                self._last_check = 0.0
                self._last_403_check = 0.0
            return self._key_state

    @property
    def key_state(self) -> tuple[str, str]:
        """(unset|unchecked|ok|failed, reason) for the stored key; reason is invalid|blocked."""
        state = self._sync_key()
        with self._key_lock:
            return state, self._key_reason

    def _headers(self) -> dict[str, str]:
        """Request headers; the key is dropped while it counts as failed."""
        headers = dict(self._auth().headers)
        if self._sync_key() in ("unset", "failed"):
            headers.pop("Authorization", None)
        return headers

    def _set_key(self, state: str, reason: str = "") -> None:
        with self._key_lock:
            changed = (self._key_state, self._key_reason) != (state, reason)
            self._key_state, self._key_reason = state, reason
        if changed:
            _log.warning("nhentai: key state %s%s", state, f" ({reason})" if reason else "")

    def check_key(self) -> tuple[str, str]:
        """Ask GET /api/v2/user whether the key works; the body (it holds an email) is dropped.

        401 marks the key failed(invalid), 403 failed(blocked); other answers and network
        errors leave the state alone. Returns the new (state, reason).
        """
        if self._sync_key() == "unset":
            return "unset", ""
        headers = self._auth().headers
        with self._key_lock:
            self._last_check = time.monotonic()
        try:
            resp = self._client.get(self._base_url + f"{_API_PREFIX}/user", headers=headers)
        except httpx.HTTPError as e:
            _log.warning("nhentai: key check failed (%s)", type(e).__name__)
            return self.key_state
        code = resp.status_code
        if code == 200:
            self._set_key("ok")
        elif code == 401:
            self._set_key("failed", "invalid")
        elif code == 403:
            self._set_key("failed", "blocked")
        else:
            _log.warning("nhentai: key check answered %d", code)
        return self.key_state

    def _maybe_check(self) -> None:
        """Start the periodic key check aside when it is due (first call, then every 10 min)."""
        state = self._sync_key()
        if state == "unset" or (state == "failed" and self._key_reason != "blocked"):
            return  # an invalid key is re-checked only on save or Test
        now = time.monotonic()
        with self._key_lock:
            if self._last_check and now - self._last_check < CHECK_EVERY:
                return
            self._last_check = now  # claim it so one call starts one check
            if state == "failed":
                self._key_state = "unchecked"  # a short site block must not keep the key off
        self._spawn(self.check_key)

    def _recheck_after_403(self) -> bool:
        """After a 403 that carried the key: True when the key is still good (a site block)."""
        now = time.monotonic()
        with self._key_lock:
            if self._last_403_check and now - self._last_403_check < CHECK_EVERY:
                return self._key_state == "ok"
            self._last_403_check = now
        return self.check_key()[0] == "ok"

    def page_urls(self, post: Post) -> list[str]:
        """Image URL of every page, in order (CDN host, never the API host)."""
        media_id = str(post.extra.get("media_id") or "")
        raw = post.extra.get("page_exts")
        exts = raw if isinstance(raw, list) else []
        if not media_id.isalnum():
            return []
        return [f"{IMG_HOST}/galleries/{media_id}/{n}.{e}" for n, e in enumerate(exts, 1)]

    def page_headers(self) -> dict[str, str]:
        """Headers for page downloads: User-Agent only, Cookie and key stay on the API host."""
        return {
            k: v
            for k, v in self._auth().headers.items()
            if k.lower() not in ("cookie", "authorization")
        }

    def _get(
        self,
        path: str,
        params: dict[str, str | int] | None = None,
        max_wait: float | None = None,
    ) -> dict:
        """GET one API path (Cookie and key go to the API host only) and return the JSON object.

        `max_wait` set (browsing): fail with rate_limited when the slot is further away.
        None (save jobs): wait for the slot, as the pace rules say.
        A key the site rejects (401, or 403 while /user also fails) is dropped and the call
        runs once more as guest.
        """
        self._maybe_check()
        sent_key = "Authorization" in self._headers()
        try:
            return self._call(path, params, max_wait)
        except SourceError as e:
            if not sent_key or e.status not in (401, 403):
                raise
            if e.status == 403 and self._recheck_after_403():
                raise  # the key is good: a site block, shown by the browse error path
            if self.key_state[0] != "failed":
                self._set_key("failed", "invalid" if e.status == 401 else "blocked")
            return self._call(path, params, max_wait)

    def _floor(self, bucket: str, with_key: bool) -> float:
        if not self._paced or bucket not in BUCKET_PACE:
            return 0.0
        return BUCKET_PACE[bucket][1 if with_key else 0]

    def _call(
        self,
        path: str,
        params: dict[str, str | int] | None,
        max_wait: float | None,
    ) -> dict:
        headers = self._headers()
        bucket = bucket_of(path)
        floor = self._floor(bucket, "Authorization" in headers)
        if bucket == "user":
            delay: float | None = 0.0  # 45/min limit, never near it: no bucket, no wait
        elif max_wait is None:
            delay = self._throttle.reserve(floor, bucket)
        else:
            delay = self._throttle.reserve_within(max_wait, floor, bucket)
        if delay is None:
            # A pause (429 Retry-After) is running: fail fast so the UI shows Retry,
            # and take no slot so queued calls do not push the wait further out.
            _log.warning(
                "nhentai: %s refused, back-off pause is longer than %.0fs", path, MAX_QUEUE_WAIT
            )
            raise SourceError("rate_limited", "nhentai asked to slow down; retry in a minute", 429)
        if delay > 0:
            self._throttle.nap(delay)
        started = time.monotonic()
        try:
            resp = self._client.get(self._base_url + path, params=params, headers=headers)
        except httpx.HTTPError as e:
            _log.warning(
                "nhentai: %s failed (%s) after %d ms",
                path,
                type(e).__name__,
                (time.monotonic() - started) * 1000,
            )
            raise SourceError("upstream_error", "nhentai is unreachable") from None
        elapsed_ms = (time.monotonic() - started) * 1000
        if elapsed_ms > SLOW_CALL_MS or resp.status_code >= 400:
            _log.warning("nhentai: %s status=%d in %d ms", path, resp.status_code, elapsed_ms)
        self._throttle.report(resp.status_code, _retry_after(resp), floor)
        status = resp.status_code
        if status < 400 and bucket != "user":
            self._honour_rate_headers(resp, bucket)
        if status == 404:
            raise SourceError("not_found", "Gallery not found", 404)
        if status == 429:
            raise SourceError("rate_limited", "nhentai rate limit", 429)
        if status == 401:
            raise SourceError("upstream_error", "nhentai rejected the request", 401)
        if status in (403, 503):
            raise SourceError(
                "upstream_error",
                "nhentai blocked the request (Cloudflare check): "
                "set the cookie and User-Agent in Options",
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

    def download_url(self, post_id: str) -> str:
        """Ask the official endpoint for the gallery's file link (route B of a save job).

        Needs the key (state ok). Never waits: when the 7-per-5-min budget is used up or a
        back-off pause runs, it raises so the job takes route A. The signed link is returned
        to the caller only and never logged.
        """
        if not post_id.isdigit():
            raise SourceError("bad_request", "invalid gallery id", 422)
        headers = self._headers()
        if "Authorization" not in headers:
            raise SourceError("upstream_error", "no usable key", 401)
        now = time.monotonic()
        with self._key_lock:
            while self._download_times and now - self._download_times[0] > DOWNLOAD_WINDOW:
                self._download_times.popleft()
            if len(self._download_times) >= DOWNLOAD_LIMIT:
                raise SourceError("rate_limited", "download budget used up", 429)
            if self._throttle.reserve_within(0.0, 0.0, "download") is None:
                raise SourceError("rate_limited", "nhentai asked to slow down", 429)
            self._download_times.append(now)
        path = f"{_API_PREFIX}/galleries/{post_id}/download"
        try:
            resp = self._client.post(self._base_url + path, headers=headers)
        except httpx.HTTPError as e:
            _log.warning("nhentai: %s failed (%s)", path, type(e).__name__)
            raise SourceError("upstream_error", "nhentai is unreachable") from None
        self._throttle.report(resp.status_code, _retry_after(resp))
        if resp.status_code == 401:
            self._set_key("failed", "invalid")
        if resp.status_code != 200:
            _log.warning("nhentai: %s status=%d", path, resp.status_code)
            raise SourceError(
                "upstream_error", f"nhentai returned {resp.status_code}", resp.status_code
            )
        try:
            url = resp.json().get("url")
        except Exception:
            url = None
        parsed = urlparse(url) if isinstance(url, str) else None
        if parsed is None or parsed.scheme != "https" or not CDN_HOST.match(parsed.hostname or ""):
            raise SourceError("upstream_error", "nhentai sent no usable download link")
        return str(url)

    def _honour_rate_headers(self, resp: httpx.Response, bucket: str) -> None:
        """X-RateLimit-Remaining 0: hold the bucket until the next window."""
        if resp.headers.get("X-RateLimit-Remaining", "").strip() != "0":
            return
        wait = min(_retry_after(resp) or RATE_WINDOW, MAX_WAIT)
        self._throttle.hold_until(wait, bucket)
        _log.info("nhentai: rate limit window used up, bucket %s waits %.0fs", bucket, wait)

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
        sort = NHENTAI_SORTS.get(order or "")
        if sort:
            # The listing endpoint has no sort; match-all search takes one.
            data = self._get(
                "/api/v2/search",
                {"query": query or "pages:>0", "page": page, "sort": sort},
                MAX_QUEUE_WAIT,
            )
        elif query:
            data = self._get("/api/v2/search", {"query": query, "page": page}, MAX_QUEUE_WAIT)
        else:
            data = self._get("/api/v2/galleries", {"page": page}, MAX_QUEUE_WAIT)
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
            if _is_noise_tag(str(t["name"])):
                continue
            kind = str(t.get("type"))
            kind = kind if kind in TYPES else "general"
            grouped.setdefault(kind, []).append(str(t["name"]))
            self._learn_tag(t.get("id"), kind, str(t["name"]))
        self._row_tags(_list(d.get("tag_ids")), grouped)
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
            extra={
                "media_id": media_id,
                "page_exts": exts,
                "title_english": title.get("english") or None,
                "title_japanese": title.get("japanese") or None,
            },
        )
