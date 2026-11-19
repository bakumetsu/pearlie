"""Stump save target: gallery pages into a CBZ in a Stump library folder."""

from __future__ import annotations

import errno
import hashlib
import logging
import os
import posixpath
import re
import shutil
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.bookserver.base import SORT_CREATED_DESC, BookDTO, BookServerError
from app.bookserver.stump import StumpBookServer
from app.config import Settings
from app.db import connect
from app.library.trash import TrashStore
from app.models import Problem
from app.sources.base import Post, Source
from app.sources.nhentai import CDN_HOST, NHentai
from app.sources.throttle import Throttle
from app.stump import Stump
from app.targets import destinations
from app.targets.comicinfo import build_cbz
from app.targets.placement import (
    IndexCache,
    NameIndex,
    OneshotsDir,
    Plan,
    make_plan,
    oneshots_dir_of,
    series_folder_name,
)
from app.targets.placement_name import parse_name
from app.targets.stash import PendingScan, SaveError, SaveResult, _md5_of, _retry_after

logger = logging.getLogger("pearlie.stump")

TEMP_PREFIX = "pearlie-"
MAX_PAGES = 1000
MAX_PAGE_BYTES = 8 * 1024 * 1024
MAX_GALLERY_BYTES = 500 * 1024 * 1024
STALE_S = 3600
VERIFY_PAGE_SIZE = 50
ONESHOT_AUTHOR_PAGE_SIZE = 500
ONESHOT_AUTHOR_MAX_PAGES = 100
AUTHOR_HIT_TTL_S = 3600.0
AUTHOR_MISS_TTL_S = 300.0
STALE_GRACE = "-1 day"  # Stump may not have scanned a fresh save yet


def scan_failed_notice(label: str = "Stump") -> Problem:
    message = f"file saved; {label} will pick it up on its next scan"
    return Problem(code="scan_failed", message=message)


def waiting_for_stump_notice(stump_path: str) -> Problem:
    return Problem(
        code="waiting_for_stump",
        message=(
            f"waiting for Stump: {stump_path} is not listed yet; "
            "check the Stump path mapping and the library folder"
        ),
    )


def _file_name(post: Post) -> str:
    title = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", post.title or "gallery").strip(" .") or "gallery"
    site, pid = (re.sub(r"[^\w.]", "", str(v)) for v in (post.source, post.post_id))
    suffix = f" - {site}-{pid}.cbz"
    return title[:100].rstrip(" .") + suffix


class StumpTarget:
    """Stump save target (nhentai galleries): gallery pages into a CBZ in a Stump library folder."""

    is_book_target = True  # the worker waits for the library scan after a save
    target = "stump"  # saved_items.target of this server
    label = "Stump"

    def __init__(
        self,
        settings: Settings,
        client: Stump | None,
        http: httpx.Client,
        sources: dict[str, Source],
        throttles: dict[str, Throttle] | None = None,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._settings = settings
        self._stump = client
        self._stump_books: StumpBookServer | None = None
        self._http = http
        self._sources = sources
        self._throttles = throttles or {}
        self._clock = clock
        self._sleep = sleep
        self._index_cache = IndexCache()
        self._author_cache: dict[str, tuple[float, list[str]]] = {}
        self._author_retry_at = 0.0

    def set_client(self, client: Stump | None) -> None:
        self._stump = client

    @property
    def _books(self) -> StumpBookServer:
        """The book-server view of the current client (cached per client object)."""
        client = self._stump
        if client is None:
            raise SaveError("not_configured", "Stump is not configured", 503)
        cached = self._stump_books
        if cached is None or cached.client is not client:
            cached = self._stump_books = StumpBookServer(client)
        return cached

    def _incoming(self) -> str:
        return self._settings.stump_incoming_dir

    def _temp_dir(self) -> Path:
        return self._settings.stump_temp_dir

    def _prefixes(self) -> tuple[str, str]:
        """(Pearlie side, server side) path prefixes."""
        s = self._settings
        return s.stump_path_prefix_pearlie, s.stump_path_prefix_stump

    def _folder(self, source_id: str) -> str:
        s = self._settings
        folder = destinations.resolve_site(s.db_path, source_id, self._incoming())
        if not folder:
            raise SaveError(
                "no_destination", "no Stump folder set; choose one in Options > Save folders", 422
            )
        try:
            return destinations.validate_book_folder(folder, self._roots(), *self._prefixes())
        except destinations.DestinationError as e:
            raise SaveError(e.code, e.message, e.status) from e

    def _roots(self) -> list[str]:
        try:
            return [lib.root for lib in self._books.list_libraries()]
        except BookServerError as e:
            raise SaveError(e.code, e.message, e.status) from None

    def _check_mounted(self, folder: str, tag: str) -> None:
        """Fail when the library root is missing on Pearlie's side.

        A wrong mount or prefix map would otherwise make the save create a
        fresh folder tree that Stump never scans.
        """
        mapped = destinations.to_stash_path(folder, *self._prefixes())
        for root in self._roots():
            root = posixpath.normpath(root.replace("\\", "/"))
            if mapped != root and not mapped.startswith(root + "/"):
                continue
            local = destinations.to_pearlie_path(root, *self._prefixes())
            if Path(local).is_dir():
                return
            logger.warning("STUMP %s library root missing on Pearlie side root=%s", tag, local)
            raise SaveError(
                "library_not_mounted",
                f"Stump library {root} is not found at {local} in Pearlie; "
                "check the Pearlie/Stump path mapping and the mount",
                422,
            )

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
                f"Pearlie cannot write to {folder}; give it write access to the Stump library",
                422,
            )
        return path

    def _urls(self, post: Post) -> list[str]:
        src = self._sources.get(post.source)
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

    def _fetch(
        self,
        urls: list[str],
        work: Path,
        post: Post,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> list[Path]:
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
            if on_progress:
                on_progress(n, len(urls))
        return pages

    def _place_mode(self) -> str:
        conn = connect(self._settings.db_path)
        try:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = 'stump.place_mode'"
            ).fetchone()
        finally:
            conn.close()
        return "auto" if row is not None and row["value"] == "auto" else "suggest"

    def _oneshots(self, folder: str, tag: str) -> OneshotsDir:
        try:
            libs = self._books.list_libraries()
        except BookServerError:
            return OneshotsDir(None, "oneshots_not_set")
        found = oneshots_dir_of(libs, folder, *self._prefixes())
        logger.info(
            "STUMP %s oneshots dir=%s via=%s",
            tag,
            found.name or "",
            "stump" if found.name else "none",
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
        index = self._index_cache.get(
            dest_dir,
            oneshots.name,
            lambda names: self._oneshot_authors(dest_dir, oneshots.name or "", names, tag),
        )
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
            "STUMP %s placement kind=%s root_hash=%s number=%s via=%s mode=%s",
            tag,
            plan.kind,
            hashlib.md5((plan.series or "").encode()).hexdigest()[:8],
            plan.number or "-",
            plan.via,
            "override" if override else mode,
        )
        return plan

    def _oneshot_authors(
        self, dest_dir: Path, oneshots_name: str, names: list[str], tag: str
    ) -> dict[str, list[str]]:
        """Cached writer names per oneshot file; Stump is asked only for names not cached.

        A found author is kept AUTHOR_HIT_TTL_S, a miss (not scanned yet) and a failed
        call AUTHOR_MISS_TTL_S, so a later scan pairs the book and an outage is not hammered.
        """
        now = self._clock()
        out: dict[str, list[str]] = {}
        missing: list[str] = []
        for n in names:
            hit = self._author_cache.get(n)
            if hit is not None and hit[0] > now:
                out[n] = hit[1]
            else:
                missing.append(n)
        if not missing:
            return out
        if self._author_retry_at > now:
            return out
        found = self._scan_oneshot_authors(dest_dir, oneshots_name, missing, tag)
        if found is None:
            self._author_retry_at = now + AUTHOR_MISS_TTL_S
            return out
        for n in missing:
            authors = found.get(n, [])
            ttl = AUTHOR_HIT_TTL_S if authors else AUTHOR_MISS_TTL_S
            self._author_cache[n] = (now + ttl, authors)
            out[n] = authors
        return out

    def _scan_oneshot_authors(
        self, dest_dir: Path, oneshots_name: str, names: list[str], tag: str
    ) -> dict[str, list[str]] | None:
        """Stump writer names of the oneshot books *names* (read only; None on a failure)."""
        lib_dir = posixpath.normpath(
            destinations.to_stash_path(dest_dir.as_posix(), *self._prefixes())
        )
        wanted = set(names)
        found: dict[str, list[str]] = {}
        try:
            lib_id = next(
                (
                    lib.id
                    for lib in self._books.list_libraries()
                    if lib_dir == posixpath.normpath(lib.root.replace("\\", "/"))
                    or lib_dir.startswith(posixpath.normpath(lib.root.replace("\\", "/")) + "/")
                ),
                None,
            )
            if lib_id is None:
                return {}
            for page_no in range(ONESHOT_AUTHOR_MAX_PAGES):
                page = self._books.list_books(
                    page_no + 1,
                    ONESHOT_AUTHOR_PAGE_SIZE,
                    "",
                    SORT_CREATED_DESC,
                    library_id=lib_id,
                )
                for b in page.items:
                    url = b.path.replace("\\", "/")
                    name = posixpath.basename(url)
                    if (
                        name not in wanted
                        or posixpath.basename(posixpath.dirname(url)) != oneshots_name
                    ):
                        continue
                    found[name] = b.writers or b.authors
                if len(found) == len(wanted) or not page.items:
                    break
                if page.last:
                    break
            else:
                logger.warning("STUMP %s oneshot author scan stopped at the page cap", tag)
        except BookServerError as e:
            logger.warning("STUMP %s oneshot author lookup failed code=%s", tag, e.code)
            return None
        return found

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
                    message="set the oneshots directory in Stump; saved flat in the folder",
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
            logger.info("STUMP %s move start from=%s to=%s", tag, name, series_dir.name)
            if not old.exists():
                logger.info("STUMP %s move skipped code=missing", tag)
                notices.append(Problem(code="move_skipped", message=f"{name} is gone; not moved"))
                continue
            try:
                if (series_dir / name).exists():
                    raise FileExistsError(errno.EEXIST, "target exists")
                os.rename(old, series_dir / name)
            except OSError as e:
                code = errno.errorcode.get(e.errno or 0, "OSError")
                logger.warning("STUMP %s move failed code=%s", tag, code)
                notices.append(Problem(code="move_failed", message="first book stays in oneshots"))
                continue
            logger.info("STUMP %s move done", tag)

    def save(
        self,
        post: Post,
        tags: list[str],
        placement: str | None = None,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> SaveResult:
        """Download the gallery, pack it as a CBZ, place it in Stump's folder.

        The scan is not requested here: a saved result with `pending_scan` goes to ScanWait.

        *placement* ("series" or "oneshot") overrides the suggested kind.
        """
        notices: list[Problem] = []
        tag = f"source={post.source} post={post.post_id}"
        if self._saved(post):
            logger.info("STUMP %s duplicate via=saved_items", tag)
            return self._duplicate("saved_items by post")
        urls = self._urls(post)
        logger.info("STUMP %s save start pages=%d", tag, len(urls))
        folder = self._folder(post.source)
        self._check_mounted(folder, tag)
        existed = Path(folder).is_dir()
        dest_dir = self._check_writable(folder)
        if not existed:
            logger.warning(
                "STUMP %s folder did not exist, created it folder=%s "
                "(check the Pearlie/Stump path mapping and the mount)",
                tag,
                folder,
            )
        oneshots = self._oneshots(folder, tag)
        plan = self._plan(post, dest_dir, oneshots, placement, notices, tag)

        work = self._temp_dir() / f"{TEMP_PREFIX}{post.source}-{post.post_id}"
        try:
            work.mkdir(parents=True, exist_ok=True)
        except OSError:
            raise SaveError(
                "destination_not_writable", f"Pearlie cannot write to {work.parent}", 422
            ) from None
        try:
            try:
                pages = self._fetch(urls, work, post, on_progress)
                logger.info("STUMP %s downloaded pages=%d", tag, len(pages))
                cbz = work / "gallery.cbz.part"
                build_cbz(cbz, pages, post, plan)
                md5 = _md5_of(cbz)
                logger.info("STUMP %s cbz built md5=%s", tag, md5)
                place_dir = self._target_dir(plan, dest_dir, oneshots, notices)
                target, same = self._place(cbz, place_dir, _file_name(post), md5, notices)
            except SaveError as e:
                logger.warning("STUMP %s save failed code=%s", tag, e.code)
                raise
        finally:
            shutil.rmtree(work, ignore_errors=True)
        self._insert(post, md5)
        if same:
            logger.info("STUMP %s duplicate via=same file md5=%s", tag, md5)
            return self._duplicate("same file already in the folder")
        logger.info("STUMP %s placed file=%s pearlie_path=%s", tag, target.name, target.as_posix())
        if plan.kind == "series":
            self._move_first(plan, dest_dir, oneshots, place_dir, tag, notices)
        self._index_cache.invalidate()

        stump_path = destinations.to_stash_path(target.as_posix(), *self._prefixes())
        library_id, outside = self._find_library(stump_path, notices)
        pending: PendingScan | None = None
        if outside:
            self._forget(post)
            logger.warning("STUMP %s index row dropped: file is outside every library", tag)
        elif library_id is not None:
            pending = PendingScan(
                library_id=library_id,
                name=target.name,
                stump_path=stump_path,
                source=post.source,
                post_id=post.post_id,
            )
        logger.info(
            "STUMP %s save done pearlie_path=%s stump_path=%s",
            tag,
            target.as_posix(),
            stump_path,
        )
        return SaveResult(
            status="saved",
            image_id=None,
            dest_path=stump_path,
            notices=notices,
            pending_scan=pending,
        )

    def _find_library(self, stump_path: str, notices: list[Problem]) -> tuple[str | None, bool]:
        """Find the library holding the file; the flag says no library holds it."""
        outside = False
        try:
            for lib in self._books.list_libraries():
                root = posixpath.normpath(lib.root.replace("\\", "/"))
                if stump_path == root or stump_path.startswith(root + "/"):
                    return lib.id, False
            outside = True
            raise BookServerError("not_found", "no library holds the folder", 404)
        except BookServerError as e:
            logger.warning("STUMP library lookup failed code=%s status=%s", e.code, e.status)
            if outside:
                notices.append(
                    Problem(
                        code="outside_library",
                        message=(
                            "file saved outside every Stump library; "
                            "check the Pearlie/Stump path mapping"
                        ),
                    )
                )
            else:
                notices.append(scan_failed_notice(self.label))
            return None, outside

    def _forget(self, post: Post) -> None:
        conn = connect(self._settings.db_path)
        try:
            conn.execute(
                "DELETE FROM saved_items WHERE target = ? AND source = ? AND post_id = ?",
                (self.target, post.source, post.post_id),
            )
            conn.commit()
        finally:
            conn.close()

    def scan(self, library_id: str) -> None:
        """Ask the book server for one scan of the library; raises BookServerError."""
        self._books.scan_library(library_id)

    def find_books(self, library_id: str, books: dict[str, PendingScan]) -> dict[str, str]:
        """Job id -> Stump book id of each book Stump lists now: one `mediaByPath` call per book.

        A path that is not known yet is a miss. Raises BookServerError.
        """
        found: dict[str, str] = {}
        for job_id, pending in books.items():
            hit = self._books.find_by_path("books", library_id, pending.stump_path, "")
            if hit is None:
                continue
            found[job_id] = hit.id
            self._record_book(pending, hit.id)
        return found

    def _record_book(self, pending: PendingScan, book_id: str) -> None:
        """Keep the Stump book id in the saved index row (D-28 Part B); never fails a save."""
        if not book_id or not pending.post_id:
            return
        conn = connect(self._settings.db_path)
        try:
            conn.execute(
                "UPDATE saved_items SET library_id = ? WHERE target = ? "
                "AND source = ? AND post_id = ? AND library_id IS NULL",
                (book_id, self.target, pending.source, pending.post_id),
            )
            conn.commit()
        except sqlite3.Error:
            logger.warning("STUMP book id not stored post=%s", pending.post_id)
        finally:
            conn.close()

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
    def _book_matches(book: BookDTO, post_id: str) -> bool:
        """True when a library book is the saved copy of *post_id* (file name or Web link)."""
        url = book.path.replace("\\", "/")
        base = posixpath.basename(url)
        if f"[{post_id}]" in base or posixpath.splitext(base)[0].endswith(f"-{post_id}"):
            return True
        return any(f"/{post_id}/" in url_.rstrip("/") + "/" for _label, url_ in book.links)

    def trash_token(self, source: str, post_id: str) -> str | None:
        """Token of a live trash row that holds this post (the book or its series)."""
        store = TrashStore(self._settings.db_path, self._settings.trash_dir)
        row = store.find_in_trash(source, post_id)
        if row is None:
            conn = connect(self._settings.db_path)
            try:
                r = conn.execute(
                    "SELECT library_id FROM saved_items WHERE target = ? "
                    "AND source = ? AND post_id = ?",
                    (self.target, source, post_id),
                ).fetchone()
            finally:
                conn.close()
            if r and r["library_id"]:
                row = store.stump_covering(r["library_id"])
        return row["token"] if row else None

    def drop_if_gone(self, source: str, post_id: str) -> bool:
        """Drop the index row of a post when Stump no longer has its book.

        One search per dedupe hit. A row younger than STALE_GRACE, a Stump error
        and a full result page keep the row: only a clear "no matching book"
        counts as gone.
        """
        tag = f"source={source} post={post_id}"
        if self.trash_token(source, post_id) is not None:
            return False
        conn = connect(self._settings.db_path)
        try:
            fresh = conn.execute(
                "SELECT 1 FROM saved_items WHERE target = ? AND source = ? "
                "AND post_id = ? AND created_at > datetime('now', ?)",
                (self.target, source, post_id, STALE_GRACE),
            ).fetchone()
        finally:
            conn.close()
        if fresh is not None:
            logger.info("STUMP %s stale check skipped: saved within the grace period", tag)
            return False
        try:
            page = self._books.list_books(1, VERIFY_PAGE_SIZE, post_id, SORT_CREATED_DESC)
        except BookServerError as e:
            logger.warning("STUMP %s stale check failed code=%s status=%s", tag, e.code, e.status)
            return False
        books = page.items
        if any(self._book_matches(b, post_id) for b in books):
            return False
        if len(books) >= VERIFY_PAGE_SIZE:
            logger.warning("STUMP %s stale check inconclusive: full result page", tag)
            return False
        conn = connect(self._settings.db_path)
        try:
            conn.execute(
                "DELETE FROM saved_items WHERE target = ? AND source = ? AND post_id = ?",
                (self.target, source, post_id),
            )
            conn.commit()
        finally:
            conn.close()
        logger.info("STUMP %s stale index row dropped", tag)
        return True

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
                "VALUES (?, ?, ?, ?, '')",
                (post.source, post.post_id, md5, self.target),
            )
            conn.commit()
        finally:
            conn.close()

    def cleanup_temp(self) -> list[str]:
        """Remove stale work folders left by a crash (older than an hour)."""
        root = self._temp_dir()
        removed: list[str] = []
        if not root.is_dir():
            return removed
        for f in root.iterdir():
            if f.name.startswith(TEMP_PREFIX) and self._clock() - f.stat().st_mtime > STALE_S:
                shutil.rmtree(f, ignore_errors=True)
                removed.append(f.name)
        return removed
