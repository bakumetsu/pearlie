"""Stump library and placement rules: names, roots, folders, moves, oneshot authors."""

from __future__ import annotations

import errno
import logging
import os
import posixpath
import re
import shutil
from collections.abc import Callable
from pathlib import Path

from app.bookserver.base import SORT_CREATED_DESC, BookDTO, BookServerError
from app.bookserver.stump import StumpBookServer
from app.models import Problem
from app.sources.base import Post
from app.targets import destinations
from app.targets.placement import OneshotsDir, Plan
from app.targets.stash import SaveError, _md5_of

logger = logging.getLogger("pearlie.stump")

ONESHOT_AUTHOR_PAGE_SIZE = 500
ONESHOT_AUTHOR_MAX_PAGES = 100
AUTHOR_HIT_TTL_S = 3600.0
AUTHOR_MISS_TTL_S = 300.0


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


def file_name(post: Post) -> str:
    title = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", post.title or "gallery").strip(" .") or "gallery"
    site, pid = (re.sub(r"[^\w.]", "", str(v)) for v in (post.source, post.post_id))
    suffix = f" - {site}-{pid}.cbz"
    return title[:100].rstrip(" .") + suffix


def root_holds(root: str, path: str) -> bool:
    """True when *path* (server side, posix) is the library *root* or inside it."""
    root = posixpath.normpath(root.replace("\\", "/"))
    return path == root or path.startswith(root + "/")


def book_matches(book: BookDTO, post_id: str) -> bool:
    """True when a library book is the saved copy of *post_id* (file name or Web link)."""
    url = book.path.replace("\\", "/")
    base = posixpath.basename(url)
    if f"[{post_id}]" in base or posixpath.splitext(base)[0].endswith(f"-{post_id}"):
        return True
    return any(f"/{post_id}/" in url_.rstrip("/") + "/" for _label, url_ in book.links)


def check_writable(folder: str) -> Path:
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


def check_mounted(roots: list[str], folder: str, prefixes: tuple[str, str], tag: str) -> None:
    """Fail when the library root is missing on Pearlie's side.

    A wrong mount or prefix map would otherwise make the save create a
    fresh folder tree that Stump never scans.
    """
    mapped = destinations.to_stash_path(folder, *prefixes)
    for root in roots:
        root = posixpath.normpath(root.replace("\\", "/"))
        if not root_holds(root, mapped):
            continue
        local = destinations.to_pearlie_path(root, *prefixes)
        if Path(local).is_dir():
            return
        logger.warning("STUMP %s library root missing on Pearlie side root=%s", tag, local)
        raise SaveError(
            "library_not_mounted",
            f"Stump library {root} is not found at {local} in Pearlie; "
            "check the Pearlie/Stump path mapping and the mount",
            422,
        )


def target_dir(plan: Plan, dest_dir: Path, oneshots: OneshotsDir, notices: list[Problem]) -> Path:
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
        raise SaveError("destination_not_writable", f"Pearlie cannot write to {sub}", 422) from None
    return sub


def move_first(
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


def place_file(
    temp: Path, dest_dir: Path, name: str, md5: str, notices: list[Problem]
) -> tuple[Path, bool]:
    """Move *temp* to *dest_dir*/*name*; (path, True) when the same file is already there."""
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


def scan_oneshot_authors(
    books: StumpBookServer,
    lib_dir: str,
    oneshots_name: str,
    names: list[str],
    tag: str,
) -> dict[str, list[str]] | None:
    """Stump writer names of the oneshot books *names* (read only; None on a failure)."""
    wanted = set(names)
    found: dict[str, list[str]] = {}
    try:
        lib_id = next(
            (lib.id for lib in books.list_libraries() if root_holds(lib.root, lib_dir)), None
        )
        if lib_id is None:
            return {}
        for page_no in range(ONESHOT_AUTHOR_MAX_PAGES):
            page = books.list_books(
                page_no + 1, ONESHOT_AUTHOR_PAGE_SIZE, "", SORT_CREATED_DESC, library_id=lib_id
            )
            for b in page.items:
                url = b.path.replace("\\", "/")
                name = posixpath.basename(url)
                parent = posixpath.basename(posixpath.dirname(url))
                if name not in wanted or parent != oneshots_name:
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


class OneshotAuthorCache:
    """Cached writer names per oneshot file; Stump is asked only for names not cached.

    A found author is kept AUTHOR_HIT_TTL_S, a miss (not scanned yet) and a failed
    call AUTHOR_MISS_TTL_S, so a later scan pairs the book and an outage is not hammered.
    """

    def __init__(self, clock: Callable[[], float]) -> None:
        self._clock = clock
        self._cache: dict[str, tuple[float, list[str]]] = {}
        self._retry_at = 0.0

    def get(
        self,
        books: StumpBookServer,
        lib_dir: str,
        oneshots_name: str,
        names: list[str],
        tag: str,
    ) -> dict[str, list[str]]:
        now = self._clock()
        out: dict[str, list[str]] = {}
        missing: list[str] = []
        for n in names:
            hit = self._cache.get(n)
            if hit is not None and hit[0] > now:
                out[n] = hit[1]
            else:
                missing.append(n)
        if not missing or self._retry_at > now:
            return out
        found = scan_oneshot_authors(books, lib_dir, oneshots_name, missing, tag)
        if found is None:
            self._retry_at = now + AUTHOR_MISS_TTL_S
            return out
        for n in missing:
            authors = found.get(n, [])
            ttl = AUTHOR_HIT_TTL_S if authors else AUTHOR_MISS_TTL_S
            self._cache[n] = (now + ttl, authors)
            out[n] = authors
        return out
