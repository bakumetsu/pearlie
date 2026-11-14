"""Disposable thumbnail cache on disk (D-17 part A).

One folder per web site, hashed file names, atomic writes, LRU by mtime.
The folder is the truth: no index, and deleting it loses nothing.
"""

import hashlib
import logging
import os
import shutil
import threading
import time
from collections.abc import Iterable
from pathlib import Path

logger = logging.getLogger("pearlie.thumbcache")

SOURCES = ("danbooru", "gelbooru", "rule34", "nhentai")
SUFFIX = ".img"
PART_SUFFIX = ".part"
MAX_THUMB_BYTES = 5 * 1024 * 1024
DEFAULT_MAX_MB = 1024
MIN_MAX_MB = 50
MAX_MAX_MB = 20480
EVICT_TARGET = 0.9
FULL_DISK_TARGET = 0.8
WARN_INTERVAL_S = 60.0

_MB = 1024 * 1024


def sniff_image_type(data: bytes) -> str | None:
    """Content type from the first bytes (JPEG, PNG, WebP, GIF, AVIF), else None."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[4:8] == b"ftyp" and data[8:12] in (b"avif", b"avis"):
        return "image/avif"
    return None


def valid_max_mb(value: object) -> bool:
    if not isinstance(value, int) or isinstance(value, bool):
        return False
    return MIN_MAX_MB <= value <= MAX_MAX_MB


class ThumbCache:
    def __init__(
        self,
        root: Path,
        max_mb: int = DEFAULT_MAX_MB,
        forbidden: Iterable[Path] = (),
    ) -> None:
        self.root = root
        self._max_bytes = max_mb * _MB
        self._lock = threading.Lock()
        self._evict_lock = threading.Lock()
        self._used = 0
        self._files = 0
        self._last_warn = 0.0
        self._gen = 0
        self._available = self._prepare(forbidden)

    @property
    def available(self) -> bool:
        return self._available

    @property
    def max_mb(self) -> int:
        return self._max_bytes // _MB

    def _prepare(self, forbidden: Iterable[Path]) -> bool:
        try:
            root = self.root.resolve()
            for bad in forbidden:
                bad_resolved = bad.resolve()
                if root == bad_resolved or bad_resolved in root.parents:
                    logger.warning("thumbcache root is in a protected folder; pass-through mode")
                    return False
            for site in SOURCES:
                (self.root / site).mkdir(parents=True, exist_ok=True)
            probe = self.root / f".probe{PART_SUFFIX}"
            probe.write_bytes(b"")
            probe.unlink()
        except OSError as exc:
            logger.warning("thumbcache folder unusable (%s); pass-through mode", type(exc).__name__)
            return False
        return True

    def start(self) -> None:
        """Clean leftover .part files and build the size total in a background thread."""
        if not self._available:
            return
        threading.Thread(target=self.rescan, name="thumbcache-walk", daemon=True).start()

    def rescan(self) -> None:
        if not self._evict_lock.acquire(blocking=True):
            return
        try:
            for attempt in range(3):
                with self._lock:
                    gen = self._gen
                used = files = 0
                for path in self._walk():
                    if path.name.endswith(PART_SUFFIX):
                        self._unlink(path)
                        continue
                    try:
                        used += path.stat().st_size
                    except OSError:
                        continue
                    files += 1
                with self._lock:
                    if self._gen == gen or attempt == 2:
                        self._used = used
                        self._files = files
                        break
        finally:
            self._evict_lock.release()

    def _walk(self) -> Iterable[Path]:
        for site in SOURCES:
            site_dir = self.root / site
            if not site_dir.is_dir():
                continue
            for dirpath, _dirs, names in os.walk(site_dir):
                for name in names:
                    yield Path(dirpath) / name

    @staticmethod
    def _unlink(path: Path) -> bool:
        try:
            path.unlink()
        except OSError:
            return False
        return True

    def path_for(self, source: str, post_id: str) -> Path:
        if source not in SOURCES:
            raise ValueError("unknown source")
        digest = hashlib.sha256(f"{source}\0{post_id}".encode()).hexdigest()
        return self.root / source / digest[:2] / f"{digest}{SUFFIX}"

    def get(self, source: str, post_id: str) -> Path | None:
        """Path of a cached thumbnail (touched as last used), or None on a miss."""
        if not self._available:
            return None
        path = self.path_for(source, post_id)
        try:
            with path.open("rb") as fh:
                head = fh.read(16)
            size = path.stat().st_size
        except OSError:
            return None
        if size == 0 or sniff_image_type(head) is None:
            self._drop(path)
            return None
        try:
            os.utime(path)
        except OSError:
            pass
        return path

    def _drop(self, path: Path) -> None:
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        if self._unlink(path):
            with self._lock:
                self._used = max(0, self._used - size)
                self._files = max(0, self._files - 1)
                self._gen += 1

    def put(self, source: str, post_id: str, data: bytes) -> bool:
        """Store bytes atomically. False when nothing was stored."""
        if not self._available or not data or len(data) > MAX_THUMB_BYTES:
            return False
        if sniff_image_type(data) is None:
            return False
        path = self.path_for(source, post_id)
        tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}{PART_SUFFIX}")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_bytes(data)
        except OSError:
            self._unlink(tmp)
            self._warn_disk_full()
            return False
        try:
            with self._lock:
                try:
                    old = path.stat().st_size
                except OSError:
                    old = None
                os.replace(tmp, path)
                self._used += len(data) - (old or 0)
                self._files += 0 if old is not None else 1
                self._gen += 1
                over = self._used > self._max_bytes
        except OSError:
            self._unlink(tmp)
            self._warn_disk_full()
            return False
        if over:
            self._evict(EVICT_TARGET)
        return True

    def _warn_disk_full(self) -> None:
        with self._lock:
            now = time.monotonic()
            should_warn = now - self._last_warn >= WARN_INTERVAL_S
            if should_warn:
                self._last_warn = now
        if should_warn:
            logger.warning("thumbcache write failed; serving without storing")
        self._evict(FULL_DISK_TARGET)

    def _evict(self, fraction: float) -> None:
        """Delete oldest-mtime files until the total is at most fraction of the cap."""
        if not self._evict_lock.acquire(blocking=False):
            return
        try:
            target = int(self._max_bytes * fraction)
            for attempt in range(3):
                with self._lock:
                    gen = self._gen
                entries: list[tuple[float, int, Path]] = []
                for path in self._walk():
                    if path.name.endswith(PART_SUFFIX):
                        continue
                    try:
                        st = path.stat()
                    except OSError:
                        continue
                    entries.append((st.st_mtime, st.st_size, path))
                total = sum(size for _m, size, _p in entries)
                entries.sort(key=lambda e: e[0])
                freed_files = 0
                for _mtime, size, path in entries:
                    if total <= target:
                        break
                    if self._unlink(path):
                        total -= size
                        freed_files += 1
                with self._lock:
                    if self._gen == gen or attempt == 2:
                        self._used = total
                        self._files = len(entries) - freed_files
                        break
        finally:
            self._evict_lock.release()

    def set_max_mb(self, max_mb: int) -> None:
        if not valid_max_mb(max_mb):
            raise ValueError("max_mb out of range")
        self._max_bytes = max_mb * _MB
        if self._available:
            with self._lock:
                over = self._used > self._max_bytes
            if over:
                self._evict(EVICT_TARGET)

    def stats(self) -> dict[str, int | float | bool]:
        with self._lock:
            used, files = self._used, self._files
        return {
            "max_mb": self.max_mb,
            "used_bytes": used,
            "used_mb": round(used / _MB, 1),
            "files": files,
            "available": self._available,
        }

    def clear(self) -> int:
        """Delete every cached file; returns the bytes freed. Never follows symlinks."""
        if not self._available:
            return 0
        freed = 0
        for site in SOURCES:
            site_dir = self.root / site
            if site_dir.is_symlink() or not site_dir.is_dir():
                continue
            for entry in list(site_dir.iterdir()):
                if entry.is_symlink() or not entry.is_dir():
                    freed += self._size_and_unlink(entry)
                    continue
                for dirpath, _dirs, names in os.walk(entry):
                    for name in names:
                        freed += self._size_and_unlink(Path(dirpath) / name)
                shutil.rmtree(entry, ignore_errors=True)
        self.rescan()
        return freed

    def _size_and_unlink(self, path: Path) -> int:
        try:
            size = path.lstat().st_size
        except OSError:
            return 0
        return size if self._unlink(path) else 0
