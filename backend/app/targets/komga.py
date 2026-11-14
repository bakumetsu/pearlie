"""Komga save target: gallery pages into a CBZ in a Komga library folder."""

from __future__ import annotations

import errno
import hashlib
import logging
import os
import posixpath
import re
import shutil
import time
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.config import Settings
from app.db import connect
from app.komga import Komga, KomgaError
from app.models import Problem
from app.sources.base import Post, Source
from app.sources.nhentai import CDN_HOST, NHentai
from app.sources.throttle import Throttle
from app.targets import destinations
from app.targets.comicinfo import build_cbz
from app.targets.placement import (
    IndexCache,
    NameIndex,
    OneshotsDir,
    Plan,
    make_plan,
    oneshots_dir_name,
    series_folder_name,
)
from app.targets.placement_name import parse_name
from app.targets.stash import SaveError, SaveResult, _md5_of, _retry_after

logger = logging.getLogger("pearlie.komga")

TEMP_PREFIX = "pearlie-"
MAX_PAGES = 1000
MAX_PAGE_BYTES = 8 * 1024 * 1024
MAX_GALLERY_BYTES = 500 * 1024 * 1024
STALE_S = 3600
VERIFY_TRIES = 5
VERIFY_DELAY_S = 2.0
VERIFY_PAGE_SIZE = 50


def _file_name(post: Post) -> str:
    title = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", post.title or "gallery").strip(" .") or "gallery"
    return f"{title[:100]} [{post.post_id}].cbz"


class KomgaTarget:
    """Komga save target (nhentai galleries)."""

    def __init__(
        self,
        settings: Settings,
        client: Komga | None,
        http: httpx.Client,
        sources: dict[str, Source],
        throttles: dict[str, Throttle] | None = None,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._settings = settings
        self._c = client
        self._http = http
        self._sources = sources
        self._throttles = throttles or {}
        self._clock = clock
        self._sleep = sleep
        self._index_cache = IndexCache()

    def set_client(self, client: Komga) -> None:
        self._c = client

    @property
    def _client(self) -> Komga:
        if self._c is None:
            raise SaveError("not_configured", "Komga is not configured", 503)
        return self._c

    @_client.setter
    def _client(self, client: Komga) -> None:
        self._c = client

    def _folder(self, source_id: str) -> str:
        s = self._settings
        folder = destinations.resolve_site(s.db_path, source_id, s.komga_incoming_dir)
        if not folder:
            raise SaveError(
                "no_destination", "no Komga folder set; choose one in Options > Save folders", 422
            )
        try:
            return destinations.validate_komga_folder(
                folder, self._roots(), s.komga_path_prefix_pearlie, s.komga_path_prefix_komga
            )
        except destinations.DestinationError as e:
            raise SaveError(e.code, e.message, e.status) from e

    def _roots(self) -> list[str]:
        try:
            return [str(lib.get("root", "")) for lib in self._client.list_libraries()]
        except KomgaError as e:
            raise SaveError(e.code, e.message, e.status) from None

    @staticmethod
    def _check_writable(folder: str) -> Path:
        path = Path(folder)
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        if not path.is_dir() or not os.access(path, os.W_OK):
            raise SaveError(
                "destination_not_writable",
                f"Pearlie cannot write to {folder}; give it write access to the Komga library",
                422,
            )
        return path

    def _urls(self, post: Post) -> list[str]:
        src = self._sources.get(post.source)
        if not isinstance(src, NHentai):
            raise SaveError("no_source", f"{post.source} cannot be saved to Komga", 422)
        urls = src.page_urls(post)
        if not 1 <= len(urls) <= MAX_PAGES:
            raise SaveError("no_file", "gallery has no downloadable pages", 422)
        for url in urls:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https") or not CDN_HOST.match(parsed.hostname or ""):
                raise SaveError("host_not_allowed", f"file host not allowed for {post.source}", 422)
        return urls

    def _fetch(self, urls: list[str], work: Path, post: Post) -> list[Path]:
        src = self._sources[post.source]
        assert isinstance(src, NHentai)
        throttle = self._throttles.get(post.source)
        pages: list[Path] = []
        total = 0
        for n, url in enumerate(urls, 1):
            part = work / f"{n:04d}{Path(urlparse(url).path).suffix.lower()}"
            if throttle:
                throttle.wait()
            written = 0
            try:
                with self._http.stream(
                    "GET", url, headers=src.page_headers(), follow_redirects=False
                ) as resp:
                    if throttle:
                        throttle.report(resp.status_code, _retry_after(resp))
                    if resp.status_code != 200:
                        raise SaveError(
                            "download_failed", f"page {n} returned {resp.status_code}", 502
                        )
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
        return pages

    def _place_mode(self) -> str:
        conn = connect(self._settings.db_path)
        try:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = 'komga.place_mode'"
            ).fetchone()
        finally:
            conn.close()
        return "auto" if row is not None and row["value"] == "auto" else "suggest"

    def _oneshots(self, folder: str, tag: str) -> OneshotsDir:
        s = self._settings
        try:
            libs = self._client.list_libraries()
        except KomgaError:
            return OneshotsDir(None, "oneshots_not_set")
        found = oneshots_dir_name(
            libs, folder, s.komga_path_prefix_pearlie, s.komga_path_prefix_komga
        )
        logger.info(
            "KOMGA %s oneshots dir=%s via=%s",
            tag,
            found.name or "",
            "komga" if found.name else "none",
        )
        return found

    def _plan(
        self,
        post: Post,
        dest_dir: Path,
        oneshots: OneshotsDir,
        override: str | None,
        notices: list[Problem],
        tag: str,
        absorb: bool = False,
    ) -> Plan:
        """*absorb* (the sheet's suggestion) or an *override* (the sheet's confirmed kind)
        allows the name-prefix join, and only in mode ``suggest``; batch and rule saves
        send neither, so they match an exact root only."""
        parsed = parse_name(post.title or "", post.tags.get("artist", []))
        index = self._index_cache.get(dest_dir, oneshots.name)
        if index.too_large:
            notices.append(
                Problem(
                    code="placement_index_too_large",
                    message="folder has too many entries to match; saved as a new book",
                )
            )
            index = NameIndex()
        mode = self._place_mode()
        prefix_ok = mode == "suggest" and (absorb or override is not None)
        plan = make_plan(
            index, parsed, "suggest" if prefix_ok else "auto", oneshots.name is not None
        )
        if override == "oneshot" and plan.kind == "series":
            plan = Plan("oneshot", None, "", None, "oneshot")
        elif override == "series" and plan.kind == "oneshot":
            folder = series_folder_name(parsed.author, parsed.root)
            plan = Plan("series", parsed.root, parsed.number, folder, "new")
        logger.info(
            "KOMGA %s placement kind=%s root_hash=%s number=%s via=%s mode=%s",
            tag,
            plan.kind,
            hashlib.md5((plan.series or "").encode()).hexdigest()[:8],
            plan.number or "-",
            plan.via,
            "override" if override else mode,
        )
        return plan

    def suggest(self, post: Post) -> Plan:
        """The plan a save would use now. Writes nothing: no folder, no file, no job."""
        folder = self._folder(post.source)
        oneshots = self._oneshots(folder, f"source={post.source} post={post.post_id}")
        return self._plan(
            post,
            Path(folder),
            oneshots,
            None,
            [],
            f"source={post.source} post={post.post_id}",
            absorb=True,
        )

    @staticmethod
    def _target_dir(
        plan: Plan, dest_dir: Path, oneshots: OneshotsDir, notices: list[Problem]
    ) -> Path:
        if plan.kind == "series" and plan.folder:
            sub = dest_dir / plan.folder
        elif oneshots.name:
            sub = dest_dir / oneshots.name
        else:
            notices.append(
                Problem(
                    code="oneshots_not_set",
                    message="set the oneshots directory in Komga; saved flat in the folder",
                )
            )
            return dest_dir
        try:
            sub.mkdir(parents=True, exist_ok=True)
        except OSError:
            raise SaveError(
                "destination_not_writable", f"Pearlie cannot write to {sub}", 422
            ) from None
        return sub

    @staticmethod
    def _move_first(
        plan: Plan,
        dest_dir: Path,
        oneshots: OneshotsDir,
        series_dir: Path,
        tag: str,
        notices: list[Problem],
    ) -> None:
        """Rename earlier oneshots of the group into the series folder; never fails the save."""
        if not plan.move_from or not oneshots.name:
            return
        for name in plan.move_from:
            old = dest_dir / oneshots.name / name
            logger.info("KOMGA %s move start from=%s to=%s", tag, name, series_dir.name)
            if not old.exists():
                logger.info("KOMGA %s move skipped code=missing", tag)
                notices.append(Problem(code="move_skipped", message=f"{name} is gone; not moved"))
                continue
            try:
                if (series_dir / name).exists():
                    raise FileExistsError(errno.EEXIST, "target exists")
                os.rename(old, series_dir / name)
            except OSError as e:
                code = errno.errorcode.get(e.errno or 0, "OSError")
                logger.warning("KOMGA %s move failed code=%s", tag, code)
                notices.append(Problem(code="move_failed", message="first book stays in oneshots"))
                continue
            logger.info("KOMGA %s move done", tag)

    def save(self, post: Post, tags: list[str], placement: str | None = None) -> SaveResult:
        """Download the gallery, pack it as a CBZ, place it in Komga's folder, scan.

        *placement* ("series" or "oneshot") overrides the suggested kind.
        """
        notices: list[Problem] = []
        tag = f"source={post.source} post={post.post_id}"
        if self._saved(post):
            logger.info("KOMGA %s duplicate via=saved_items", tag)
            return self._duplicate("saved_items by post")
        urls = self._urls(post)
        logger.info("KOMGA %s save start pages=%d", tag, len(urls))
        folder = self._folder(post.source)
        existed = Path(folder).is_dir()
        dest_dir = self._check_writable(folder)
        if not existed:
            logger.warning(
                "KOMGA %s folder did not exist, created it folder=%s "
                "(check the Pearlie/Komga path mapping and the mount)",
                tag,
                folder,
            )
        oneshots = self._oneshots(folder, tag)
        plan = self._plan(post, dest_dir, oneshots, placement, notices, tag)

        work = self._settings.komga_temp_dir / f"{TEMP_PREFIX}{post.source}-{post.post_id}"
        try:
            work.mkdir(parents=True, exist_ok=True)
        except OSError:
            raise SaveError(
                "destination_not_writable", f"Pearlie cannot write to {work.parent}", 422
            ) from None
        try:
            try:
                pages = self._fetch(urls, work, post)
                logger.info("KOMGA %s downloaded pages=%d", tag, len(pages))
                cbz = work / "gallery.cbz.part"
                build_cbz(cbz, pages, post, plan)
                md5 = _md5_of(cbz)
                logger.info("KOMGA %s cbz built md5=%s", tag, md5)
                place_dir = self._target_dir(plan, dest_dir, oneshots, notices)
                target, same = self._place(cbz, place_dir, _file_name(post), md5, notices)
            except SaveError as e:
                logger.warning("KOMGA %s save failed code=%s", tag, e.code)
                raise
        finally:
            shutil.rmtree(work, ignore_errors=True)
        self._insert(post, md5)
        if same:
            logger.info("KOMGA %s duplicate via=same file md5=%s", tag, md5)
            return self._duplicate("same file already in the folder")
        logger.info("KOMGA %s placed file=%s pearlie_path=%s", tag, target.name, target.as_posix())
        if plan.kind == "series":
            self._move_first(plan, dest_dir, oneshots, place_dir, tag, notices)
        self._index_cache.invalidate()

        komga_path = destinations.to_stash_path(
            target.as_posix(),
            self._settings.komga_path_prefix_pearlie,
            self._settings.komga_path_prefix_komga,
        )
        library_id = self._scan(komga_path, notices)
        if library_id is not None:
            self._verify(library_id, target.name, komga_path, tag, notices)
        logger.info(
            "KOMGA %s save done pearlie_path=%s komga_path=%s",
            tag,
            target.as_posix(),
            komga_path,
        )
        return SaveResult(status="saved", image_id=None, dest_path=komga_path, notices=notices)

    def _scan(self, komga_path: str, notices: list[Problem]) -> str | None:
        try:
            for lib in self._client.list_libraries():
                root = posixpath.normpath(str(lib.get("root", "")).replace("\\", "/"))
                if komga_path == root or komga_path.startswith(root + "/"):
                    self._client.scan_library(str(lib["id"]))
                    logger.info("KOMGA scan requested library=%s", lib.get("id"))
                    return str(lib["id"])
            raise KomgaError("not_found", "no library holds the folder", 404)
        except KomgaError as e:
            logger.warning("KOMGA scan failed code=%s status=%s", e.code, e.status)
            notices.append(
                Problem(
                    code="scan_failed",
                    message="file saved; Komga will pick it up on its next scan",
                )
            )
            return None

    def _verify(
        self, library_id: str, name: str, komga_path: str, tag: str, notices: list[Problem]
    ) -> None:
        """Poll Komga for the new book; add a notice when it does not show up."""
        for attempt in range(VERIFY_TRIES):
            if attempt:
                self._sleep(VERIFY_DELAY_S)
            try:
                page = self._client.list_books(
                    0, VERIFY_PAGE_SIZE, "", "createdDate,desc", library_id=library_id
                )
            except KomgaError as e:
                logger.warning("KOMGA %s verify failed code=%s status=%s", tag, e.code, e.status)
                return
            for book in page.get("content", []):
                url = str(book.get("url", "")).replace("\\", "/")
                if url == komga_path or posixpath.basename(url) == name:
                    logger.info("KOMGA %s verified book=%s", tag, book.get("id"))
                    return
        logger.warning("KOMGA %s book not found in Komga path=%s", tag, komga_path)
        notices.append(
            Problem(
                code="waiting_for_komga",
                message=(
                    f"waiting for Komga: {komga_path} is not listed yet; "
                    "check the Komga path mapping and the library folder"
                ),
            )
        )

    @staticmethod
    def _place(
        temp: Path, dest_dir: Path, name: str, md5: str, notices: list[Problem]
    ) -> tuple[Path, bool]:
        target = dest_dir / name
        if target.exists():
            if _md5_of(target) == md5:
                return target, True
            stem, suffix, counter = target.stem, target.suffix, 2
            while (dest_dir / f"{stem}_{counter}{suffix}").exists():
                counter += 1
            target = dest_dir / f"{stem}_{counter}{suffix}"
            notices.append(Problem(code="name_clash", message=f"renamed to {target.name}"))
        try:
            os.replace(temp, target)
        except OSError:
            shutil.move(str(temp), str(target))
        return target, False

    def _saved(self, post: Post) -> bool:
        conn = connect(self._settings.db_path)
        try:
            row = conn.execute(
                "SELECT 1 FROM saved_items WHERE source = ? AND post_id = ?",
                (post.source, post.post_id),
            ).fetchone()
        finally:
            conn.close()
        return row is not None

    @staticmethod
    def _duplicate(via: str) -> SaveResult:
        return SaveResult(
            status="duplicate",
            notices=[Problem(code="duplicate", message=f"already saved ({via})")],
        )

    def _insert(self, post: Post, md5: str) -> None:
        conn = connect(self._settings.db_path)
        try:
            conn.execute(
                "INSERT OR IGNORE INTO saved_items (source, post_id, md5, target, image_id) "
                "VALUES (?, ?, ?, 'komga', '')",
                (post.source, post.post_id, md5),
            )
            conn.commit()
        finally:
            conn.close()

    def cleanup_temp(self) -> list[str]:
        """Remove stale work folders left by a crash (older than an hour)."""
        root = self._settings.komga_temp_dir
        removed: list[str] = []
        if not root.is_dir():
            return removed
        for f in root.iterdir():
            if f.name.startswith(TEMP_PREFIX) and self._clock() - f.stat().st_mtime > STALE_S:
                shutil.rmtree(f, ignore_errors=True)
                removed.append(f.name)
        return removed
