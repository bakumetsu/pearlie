"""Stump save target, download side: gallery page and archive fetches over HTTP."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.sources.base import Post, Source, SourceError
from app.sources.nhentai import CDN_HOST, NHentai
from app.sources.throttle import Throttle
from app.targets.comicinfo import repack_download
from app.targets.placement import Plan
from app.targets.stash import SaveError, _retry_after

logger = logging.getLogger("pearlie.stump")

MAX_PAGES = 1000
MAX_PAGE_BYTES = 8 * 1024 * 1024
MAX_GALLERY_BYTES = 500 * 1024 * 1024


def page_urls(src: Source | None, post: Post) -> list[str]:
    """Checked page URLs of a gallery; *src* must be the nhentai source."""
    if not isinstance(src, NHentai):
        raise SaveError("no_source", f"{post.source} cannot be saved to Stump", 422)
    urls = src.page_urls(post)
    if not 1 <= len(urls) <= MAX_PAGES:
        raise SaveError("no_file", "gallery has no downloadable pages", 422)
    for url in urls:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not CDN_HOST.match(parsed.hostname or ""):
            raise SaveError("host_not_allowed", f"file host not allowed for {post.source}", 422)
    return urls


def fetch_pages(
    http: httpx.Client,
    src: NHentai,
    throttle: Throttle | None,
    urls: list[str],
    work: Path,
    on_progress: Callable[[int, int], None] | None = None,
) -> list[Path]:
    """Route A: download every page into *work*, in order."""
    pages: list[Path] = []
    total = 0
    for n, url in enumerate(urls, 1):
        part = work / f"{n:04d}{Path(urlparse(url).path).suffix.lower()}"
        if throttle:
            throttle.wait()
        written = 0
        try:
            with http.stream(
                "GET", url, headers=src.page_headers(), follow_redirects=False
            ) as resp:
                if throttle:
                    throttle.report(resp.status_code, _retry_after(resp))
                if resp.status_code != 200:
                    raise SaveError("download_failed", f"page {n} returned {resp.status_code}", 502)
                with open(part, "wb") as f:
                    for chunk in resp.iter_bytes():
                        written += len(chunk)
                        total += len(chunk)
                        if written > MAX_PAGE_BYTES or total > MAX_GALLERY_BYTES:
                            raise SaveError("too_large", "gallery is too large", 502)
                        f.write(chunk)
        except httpx.HTTPError:
            raise SaveError("download_failed", f"page {n} failed", 502) from None
        if written == 0:
            raise SaveError("size_mismatch", f"page {n} is empty", 502)
        pages.append(part)
        if on_progress:
            on_progress(n, len(urls))
    return pages


def fetch_api(
    http: httpx.Client,
    src: NHentai,
    throttle: Throttle | None,
    post: Post,
    work: Path,
    cbz: Path,
    plan: Plan,
    tag: str,
    on_progress: Callable[[int, int], None] | None,
) -> bool:
    """Route B: official download link, file repacked as the CBZ. False: use route A.

    Any failure (no link, bad host, non-200, too large, not a gallery zip) is logged
    without the key or link and returns False.
    """
    part = work / "api.zip"
    try:
        url = src.download_url(post.post_id)
        if throttle:
            throttle.wait()
        written = 0
        with http.stream("GET", url, headers=src.page_headers(), follow_redirects=False) as resp:
            if throttle:
                throttle.report(resp.status_code, _retry_after(resp))
            if resp.status_code != 200:
                raise SaveError("download_failed", f"file returned {resp.status_code}", 502)
            with open(part, "wb") as f:
                for chunk in resp.iter_bytes():
                    written += len(chunk)
                    if written > MAX_GALLERY_BYTES:
                        raise SaveError("too_large", "gallery is too large", 502)
                    f.write(chunk)
        count = repack_download(part, cbz, post, plan, MAX_GALLERY_BYTES)
    except (SourceError, SaveError, ValueError, httpx.HTTPError, OSError) as e:
        code = getattr(e, "code", type(e).__name__)
        logger.warning("STUMP %s route=api failed (%s), falling back to gallery-dl", tag, code)
        cbz.unlink(missing_ok=True)
        return False
    finally:
        part.unlink(missing_ok=True)
    if on_progress:
        on_progress(count, count)
    return True
