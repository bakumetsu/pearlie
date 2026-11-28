"""Stump save target: gallery pages into a CBZ in a Stump library folder."""

from __future__ import annotations

import hashlib
import logging
import posixpath
import shutil
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path

import httpx

from app.bookserver.base import SORT_CREATED_DESC, BookDTO, BookServerError
from app.bookserver.stump import StumpBookServer
from app.config import Settings
from app.db import connect
from app.library.trash import TrashStore
from app.models import Problem
from app.sources.base import Post, Source
from app.sources.nhentai import NHentai
from app.sources.throttle import Throttle
from app.stump import Stump
from app.targets import destinations, stump_client, stump_library
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
from app.targets.stash import PendingScan, SaveError, SaveResult, _md5_of
from app.targets.stump_library import scan_failed_notice as scan_failed_notice
from app.targets.stump_library import waiting_for_stump_notice as waiting_for_stump_notice

logger = logging.getLogger("pearlie.stump")

TEMP_PREFIX = "pearlie-"
STALE_S = 3600
VERIFY_PAGE_SIZE = 50
STALE_GRACE = "-1 day"  # Stump may not have scanned a fresh save yet


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
        self._authors = stump_library.OneshotAuthorCache(clock)

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
            lambda names: self._authors.get(
                self._books, self._lib_dir(dest_dir), oneshots.name or "", names, tag
            ),
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

    def _lib_dir(self, dest_dir: Path) -> str:
        mapped = destinations.to_stash_path(dest_dir.as_posix(), *self._prefixes())
        return posixpath.normpath(mapped)

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
        src = self._sources.get(post.source)
        # Route B needs a working key; the state is read once, here, for the whole job.
        use_api = isinstance(src, NHentai) and src.key_state[0] == "ok"
        urls = [] if use_api else stump_client.page_urls(src, post)
        logger.info("STUMP %s save start route=%s", tag, "api" if use_api else "gallery-dl")
        folder = self._folder(post.source)
        stump_library.check_mounted(self._roots(), folder, self._prefixes(), tag)
        existed = Path(folder).is_dir()
        dest_dir = stump_library.check_writable(folder)
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
                cbz = work / "gallery.cbz.part"
                if use_api:
                    assert isinstance(src, NHentai)
                    use_api = stump_client.fetch_api(
                        self._http,
                        src,
                        self._throttles.get(post.source),
                        post,
                        work,
                        cbz,
                        plan,
                        tag,
                        on_progress,
                    )
                if not use_api:
                    urls = urls or stump_client.page_urls(src, post)
                    assert isinstance(src, NHentai)
                    pages = stump_client.fetch_pages(
                        self._http,
                        src,
                        self._throttles.get(post.source),
                        urls,
                        work,
                        on_progress,
                    )
                    logger.info("STUMP %s downloaded pages=%d route=gallery-dl", tag, len(pages))
                    build_cbz(cbz, pages, post, plan)
                else:
                    logger.info("STUMP %s downloaded route=api", tag)
                md5 = _md5_of(cbz)
                logger.info("STUMP %s cbz built md5=%s", tag, md5)
                place_dir = stump_library.target_dir(plan, dest_dir, oneshots, notices)
                target, same = stump_library.place_file(
                    cbz, place_dir, stump_library.file_name(post), md5, notices
                )
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
            stump_library.move_first(plan, dest_dir, oneshots, place_dir, tag, notices)
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
                if stump_library.root_holds(lib.root, stump_path):
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
        return stump_library.book_matches(book, post_id)

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
        if any(stump_library.book_matches(b, post_id) for b in books):
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
