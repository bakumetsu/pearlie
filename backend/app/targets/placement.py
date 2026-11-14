"""Plan where a Komga save goes: existing folders, name index, oneshots dir."""

from __future__ import annotations

import os
import posixpath
import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from app.targets.destinations import to_stash_path
from app.targets.placement_name import ParsedName, parse_name

MAX_ENTRIES = 50_000
CACHE_TTL_S = 30.0
# Komga libraries JSON field; confirmed from Komga LibraryDto.kt (T-198), keep it in one place.
ONESHOTS_FIELD = "oneshotsDirectory"
_BAD_CHARS = re.compile(r'[<>:"/\|?*]')
_FOLDER_AUTHOR_RE = re.compile(r"^(\[[^\]]+\])\s*(.*)$")


def clean_folder_name(name: str) -> str:
    """The Sort-Doujin folder name rule: drop bad chars, trim '. ', default name."""
    cleaned = _BAD_CHARS.sub("", name.strip()).rstrip(". ")
    return cleaned or "Grouped_Series"


def series_folder_name(author: str, root: str) -> str:
    return clean_folder_name(f"{author} {root}".strip())


@dataclass(frozen=True)
class OneshotsDir:
    name: str | None
    notice: str | None = None  # "oneshots_not_set" when name is None


def oneshots_dir_name(
    libraries: Iterable[dict],
    series_root: str,
    prefix_pearlie: str = "",
    prefix_komga: str = "",
) -> OneshotsDir:
    """Read ``oneshotsDirectory`` (a folder NAME) of the library holding *series_root*.

    *series_root* is a Pearlie path; it is mapped to the Komga path first.
    """
    komga_path = posixpath.normpath(to_stash_path(series_root, prefix_pearlie, prefix_komga))
    best: dict | None = None
    best_len = -1
    for lib in libraries:
        root = posixpath.normpath(str(lib.get("root", "")))
        if komga_path == root or komga_path.startswith(root.rstrip("/") + "/"):
            if len(root) > best_len:
                best, best_len = lib, len(root)
    raw = best.get(ONESHOTS_FIELD) if best else None
    name = raw.strip() if isinstance(raw, str) else ""
    if name.startswith("/"):  # Komga: a leading "/" only anchors the match
        name = name[1:]
    if not name or name.startswith(".") or ".." in name or "/" in name or "\\" in name:
        return OneshotsDir(None, "oneshots_not_set")
    return OneshotsDir(name)


@dataclass(frozen=True)
class NameIndex:
    # author tag (lowercase, "" for none) -> sanitized root (lowercase) -> real folder name
    series: dict[str, dict[str, str]] = field(default_factory=dict)
    # author tag (lowercase) -> list of (sanitized root lowercase, file name)
    oneshots: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    too_large: bool = False


def _scan(path: Path) -> list[os.DirEntry] | None:
    """List *path*; None when it is missing or over the cap."""
    out: list[os.DirEntry] = []
    try:
        with os.scandir(path) as it:
            for entry in it:
                out.append(entry)
                if len(out) > MAX_ENTRIES:
                    return None
    except OSError:
        return []
    return out


def _split_folder(name: str) -> tuple[str, str]:
    m = _FOLDER_AUTHOR_RE.match(name)
    return (m.group(1), m.group(2)) if m else ("", name)


def build_index(series_root: Path, oneshots_name: str | None) -> NameIndex:
    """Scan the series root (folders) and the oneshots folder (files) once each."""
    series: dict[str, dict[str, str]] = {}
    oneshots: dict[str, list[tuple[str, str]]] = {}
    entries = _scan(series_root)
    if entries is None:
        return NameIndex(too_large=True)
    for e in entries:
        if not e.is_dir() or e.name == oneshots_name:
            continue
        author, root = _split_folder(e.name)
        series.setdefault(author.lower(), {})[clean_folder_name(root).lower()] = e.name
    if oneshots_name:
        files = _scan(series_root / oneshots_name)
        if files is None:
            return NameIndex(series, {}, too_large=True)
        for f in files:
            if not f.is_file():
                continue
            p = parse_name(Path(f.name).stem)
            oneshots.setdefault(p.author.lower(), []).append(
                (clean_folder_name(p.root).lower(), f.name)
            )
    return NameIndex(series, oneshots)


class IndexCache:
    """Per-folder NameIndex cache; dropped after Pearlie places or moves a file."""

    def __init__(self, ttl: float = CACHE_TTL_S, clock: Callable[[], float] = time.monotonic):
        self._ttl = ttl
        self._clock = clock
        self._items: dict[tuple[str, str | None], tuple[float, NameIndex]] = {}

    def get(self, series_root: Path, oneshots_name: str | None) -> NameIndex:
        key = (str(series_root), oneshots_name)
        hit = self._items.get(key)
        if hit and self._clock() - hit[0] < self._ttl:
            return hit[1]
        index = build_index(series_root, oneshots_name)
        self._items[key] = (self._clock(), index)
        return index

    def invalidate(self) -> None:
        self._items.clear()


@dataclass(frozen=True)
class Plan:
    kind: str  # "series" | "oneshot"
    series: str | None  # root to write as ComicInfo Series
    number: str
    folder: str | None  # series folder name (series only)
    via: str  # folder | new | absorb | oneshot_pair | oneshot
    move_from: tuple[str, ...] = ()  # oneshot file names to move into the folder


def make_plan(
    index: NameIndex,
    parsed: ParsedName,
    mode: str = "auto",
    oneshots_available: bool = True,
) -> Plan:
    """Decide series or oneshot. Absorb by whole-word prefix runs in mode ``suggest`` only."""
    akey = parsed.author.lower()
    root = parsed.root
    rkey = clean_folder_name(root).lower()
    folders = index.series.get(akey, {})
    ones = index.oneshots.get(akey, [])
    via = ""

    if rkey in folders:
        via = "folder"
    elif any(r == rkey for r, _ in ones):
        via = "oneshot_pair"
    elif mode == "suggest":
        cands = sorted(set(folders) | {r for r, _ in ones}, key=len)
        for cand in cands:
            if cand != rkey and rkey.startswith(cand) and rkey[len(cand) : len(cand) + 1].isspace():
                root = _split_folder(folders[cand])[1] if cand in folders else root[: len(cand)]
                rkey, via = cand, "absorb"
                break

    if via or parsed.is_series:
        folder = folders.get(rkey) or series_folder_name(parsed.author, root)
        moves = tuple(name for r, name in ones if r == rkey)
        return Plan("series", root, parsed.number, folder, via or "new", moves)
    return Plan("oneshot", None, "", None, "oneshot")
