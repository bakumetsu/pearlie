"""Stash save target for Pearlie."""

from __future__ import annotations

import hashlib
import os
import posixpath
import re
import shutil
import time
from collections.abc import Callable
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field

from app.config import Settings
from app.db import connect
from app.models import Problem
from app.sources.base import Post, Source
from app.targets.stash_client import StashClient

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp4", ".webm"}
TEMP_PREFIX = "pearlie-"


class SaveError(Exception):
    """Error raised during a save operation."""

    def __init__(self, code: str, message: str, status: int = 502) -> None:
        self.code = code
        self.message = message
        self.status = status
        super().__init__(message)


class SaveResult(BaseModel):
    """Result of a save operation."""

    status: Literal["saved", "duplicate"]
    image_id: str | None = None
    dest_path: str | None = None
    notices: list[Problem] = Field(default_factory=list)


def normalize_tag(tag: str) -> str:
    """Normalise a tag: underscores to spaces, lowercase, collapse whitespace."""
    return re.sub(r"\s+", " ", tag.replace("_", " ").lower()).strip()


def _safe(value: str) -> str:
    """Replace characters outside [A-Za-z0-9._-] with underscores."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", value)


def _md5_of(path: Path) -> str:
    """Compute the MD5 hex digest of a file in 1 MiB chunks."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


class StashTarget:
    """Stash save target."""

    def __init__(
        self,
        settings: Settings,
        client: StashClient,
        http: httpx.Client,
        sources: dict[str, Source],
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._client = client
        self._http = http
        self._sources = sources
        self._sleep = sleep
        self._clock = clock

    def _check_host(self, post: Post) -> str:
        """Validate that the file URL host is allowed for the post's source."""
        url = post.file_url
        if not url:
            raise SaveError("no_file", "post has no file url", 422)
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise SaveError("host_not_allowed", f"file host not allowed for {post.source}", 422)
        source = self._sources.get(post.source)
        if source is None or parsed.hostname not in source.file_hosts:
            raise SaveError("host_not_allowed", f"file host not allowed for {post.source}", 422)
        return url

    def _ext(self, url: str) -> str:
        """Extract the file extension from a URL and validate it."""
        ext = posixpath.splitext(posixpath.basename(urlparse(url).path))[1].lower()
        if ext not in ALLOWED_EXT:
            raise SaveError("bad_extension", "file type not allowed", 422)
        return ext

    def _temp_path(self, post: Post, md5: str, ext: str, part: bool) -> Path:
        """Build the temp file path (creating the directory if needed)."""
        temp_dir = self._settings.stash_temp_dir
        temp_dir.mkdir(parents=True, exist_ok=True)
        name = f"{TEMP_PREFIX}{_safe(post.source)}-{_safe(post.post_id)}-{md5}{ext}"
        if part:
            name += ".part"
        return temp_dir / name

    def _download(self, url: str, post: Post, ext: str) -> tuple[Path, str]:
        """Stream the file to a temp .part file and verify size/MD5."""
        md5_placeholder = post.md5 or "unknown"
        part_path = self._temp_path(post, md5_placeholder, ext, part=True)
        h = hashlib.md5()
        bytes_written = 0
        content_length: str | None = None

        try:
            with self._http.stream("GET", url, follow_redirects=False) as response:
                if response.status_code != 200:
                    raise SaveError(
                        "download_failed",
                        f"download returned {response.status_code}",
                        502,
                    )
                content_length = response.headers.get("content-length")
                with open(part_path, "wb") as f:
                    for chunk in response.iter_bytes():
                        f.write(chunk)
                        h.update(chunk)
                        bytes_written += len(chunk)
        except httpx.HTTPError:
            part_path.unlink(missing_ok=True)
            raise SaveError("download_failed", "download failed", 502) from None
        except SaveError:
            raise
        except Exception:
            part_path.unlink(missing_ok=True)
            raise

        digest = h.hexdigest()

        if bytes_written == 0:
            part_path.unlink(missing_ok=True)
            raise SaveError("size_mismatch", "downloaded file is empty", 502)
        if content_length is not None and int(content_length) != bytes_written:
            part_path.unlink(missing_ok=True)
            raise SaveError("size_mismatch", "downloaded size differs from Content-Length", 502)
        if post.md5 and post.md5.lower() != digest:
            part_path.unlink(missing_ok=True)
            raise SaveError("md5_mismatch", "downloaded file does not match the post MD5", 502)

        final_path = self._temp_path(post, digest, ext, part=False)
        os.replace(part_path, final_path)
        return final_path, digest

    def _move(
        self,
        temp: Path,
        folder: str,
        name_base: str,
        md5: str,
        notices: list[Problem],
    ) -> tuple[Path, bool]:
        """Move temp file into the destination folder, handling name clashes."""
        dest_dir = Path(folder)
        dest_dir.mkdir(parents=True, exist_ok=True)
        target = dest_dir / name_base

        if target.exists():
            if _md5_of(target) == md5:
                temp.unlink()
                return (target, True)
            stem = target.stem
            suffix = target.suffix
            counter = 2
            while True:
                candidate = dest_dir / f"{stem}_{counter}{suffix}"
                if not candidate.exists():
                    target = candidate
                    break
                counter += 1
            notices.append(Problem(code="name_clash", message=f"renamed to {target.name}"))

        try:
            os.replace(temp, target)
        except OSError:
            shutil.move(str(temp), str(target))

        return (target, False)

    def cleanup_temp(self) -> list[str]:
        """Remove stale temp files, keeping those with active jobs."""
        temp_dir = self._settings.stash_temp_dir
        deleted: list[str] = []
        if not temp_dir.exists():
            return deleted

        conn = connect(self._settings.db_path)
        try:
            for f in temp_dir.iterdir():
                if not f.name.startswith(TEMP_PREFIX):
                    continue
                if f.name.endswith(".part"):
                    f.unlink()
                    deleted.append(f.name)
                    continue

                rest = f.name[len(TEMP_PREFIX):]
                parts = rest.rsplit("-", 1)
                if len(parts) != 2:
                    continue
                source_post = parts[0]
                source, post_id = source_post.split("-", 1)

                cur = conn.execute(
                    "SELECT 1 FROM jobs WHERE source = ? AND post_id = ? "
                    "AND status IN ('queued', 'running', 'failed')",
                    (source, post_id),
                )
                if cur.fetchone():
                    continue

                f.unlink()
                deleted.append(f.name)
        finally:
            conn.close()

        return deleted
