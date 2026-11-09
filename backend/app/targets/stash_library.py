"""Stash GraphQL dict → Pearlie model mapping (pure, no I/O)."""

from __future__ import annotations

import math
import mimetypes
import re
import secrets
from pathlib import PurePosixPath
from urllib.parse import parse_qs, urlsplit

from app.models import LibraryItem, LibraryItemDetail, Problem, StreamOption, Tag

_SEGMENT_RE = re.compile(r"^(stream\.(mp4|webm|m3u8|ts)|[0-9]+\.ts)$")
_RES_RE = re.compile(r"^[A-Z0-9_]+$")


def valid_id(id: str) -> bool:
    """Return True when *id* is a non-empty string of ASCII digits."""
    return bool(id) and id.isascii() and id.isdigit()


def stash_sort(sort: str, seed: int | None = None) -> tuple[str, str]:
    """Map a UI sort key to a Stash sort field and direction."""
    if sort == "newest":
        return ("created_at", "DESC")
    if sort == "rating":
        return ("rating", "DESC")
    if seed is None:
        seed = secrets.randbelow(10**8)
    return (f"random_{seed}", "DESC")


def rating_from_100(r: int | None) -> int | None:
    """Convert a 0-100 rating to a 1-5 scale; None for missing or zero."""
    if r is None or r <= 0:
        return None
    return min(5, math.ceil(r / 20))


def _stash_common(
    dto: dict, kind: str, thumb_url: str, files_key: str, fallback: str
) -> dict:
    """Build the common kwargs shared by item and detail constructors."""
    fid = str(dto["id"])
    files = dto.get(files_key) or []
    title = dto.get("title") or ""
    if not title:
        if files:
            title = PurePosixPath(files[0]["basename"]).stem
        else:
            title = f"{fallback} {fid}"
    return {
        "kind": kind,
        "id": fid,
        "title": title,
        "thumb_url": thumb_url,
        "rating": rating_from_100(dto.get("rating100")),
        "favorite": False,
        "width": files[0]["width"] if files else None,
        "height": files[0]["height"] if files else None,
        "added_at": dto["created_at"],
    }


def _video_mime(files: list[dict]) -> str | None:
    """Guess the MIME type for a video file, handling .mkv explicitly."""
    basename = files[0]["basename"]
    if PurePosixPath(basename).suffix.lower() == ".mkv":
        return "video/x-matroska"
    return mimetypes.guess_type(basename)[0]


def _fallback_streams(fid: str, dto: dict) -> list[StreamOption]:
    streams: list[StreamOption] = []
    for s in dto.get("sceneStreams") or []:
        parts = urlsplit(s["url"])
        name = parts.path.rstrip("/").rsplit("/", 1)[-1]
        if not _SEGMENT_RE.match(name):
            continue
        query = parse_qs(parts.query)
        resolution = query.get("resolution", [None])[0]
        url = f"/api/media/stash/videos/{fid}/s/{name}"
        if resolution is not None and _RES_RE.match(resolution):
            url += f"?resolution={resolution}"
        streams.append(
            StreamOption(
                url=url,
                label=s.get("label") or name,
                mime=s.get("mime_type") or "video/mp4",
            )
        )
    return streams


def image_item(dto: dict) -> LibraryItem:
    """Map a Stash image DTO to a ``LibraryItem``."""
    fid = str(dto["id"])
    kw = _stash_common(
        dto, "image", f"/api/media/stash/images/{fid}/thumb", "visual_files", "Image"
    )
    kw["tags"] = sorted(t["name"] for t in dto.get("tags") or [])
    return LibraryItem(**kw)


def video_item(dto: dict) -> LibraryItem:
    """Map a Stash video (scene) DTO to a ``LibraryItem``."""
    fid = str(dto["id"])
    kw = _stash_common(
        dto, "video", f"/api/media/stash/videos/{fid}/poster", "files", "Video"
    )
    files = dto.get("files") or []
    kw["tags"] = sorted(t["name"] for t in dto.get("tags") or [])
    dur = files[0]["duration"] if files else None
    kw["duration_s"] = float(dur) if dur is not None else None
    return LibraryItem(**kw)


def image_detail(dto: dict, link_base: str = "") -> LibraryItemDetail:
    """Map a Stash image DTO to a ``LibraryItemDetail``."""
    fid = str(dto["id"])
    kw = _stash_common(
        dto, "image", f"/api/media/stash/images/{fid}/thumb", "visual_files", "Image"
    )
    tags = sorted(t["name"] for t in dto.get("tags") or [])
    kw["tags"] = [Tag(name=n) for n in tags]
    kw["source_url_text"] = (dto.get("urls") or [None])[0]
    files = dto.get("visual_files") or []
    kw["full_url"] = f"/api/media/stash/images/{fid}/full"
    kw["mime"] = mimetypes.guess_type(files[0]["basename"])[0] if files else None
    kw["stash_link"] = f"{link_base.rstrip('/')}/images/{fid}" if link_base else None
    return LibraryItemDetail(**kw)


def video_detail(dto: dict, link_base: str = "") -> LibraryItemDetail:
    """Map a Stash video (scene) DTO to a ``LibraryItemDetail``."""
    fid = str(dto["id"])
    kw = _stash_common(
        dto, "video", f"/api/media/stash/videos/{fid}/poster", "files", "Video"
    )
    tags = sorted(t["name"] for t in dto.get("tags") or [])
    kw["tags"] = [Tag(name=n) for n in tags]
    kw["source_url_text"] = (dto.get("urls") or [None])[0]
    files = dto.get("files") or []
    kw["stream_url"] = f"/api/media/stash/videos/{fid}/stream"
    kw["mime"] = _video_mime(files) if files else None
    kw["video_codec"] = files[0].get("video_codec") if files else None
    dur = files[0]["duration"] if files else None
    kw["duration_s"] = float(dur) if dur is not None else None
    kw["fallback_streams"] = _fallback_streams(fid, dto)
    kw["stash_link"] = f"{link_base.rstrip('/')}/scenes/{fid}" if link_base else None
    return LibraryItemDetail(**kw)


def map_items(dtos: list[dict], fn) -> tuple[list[LibraryItem], list[str]]:
    """Apply *fn* to each DTO, collecting bad ids on failure."""
    items: list[LibraryItem] = []
    bad: list[str] = []
    for dto in dtos:
        try:
            items.append(fn(dto))
        except (KeyError, TypeError, ValueError, IndexError):
            bad.append(str(dto.get("id", "?")) if isinstance(dto, dict) else "?")
    return items, bad


def list_notice(favorite: bool | None, bad_ids: list[str]) -> Problem | None:
    """Build a ``Problem`` notice for options Stash cannot honour."""
    parts: list[tuple[str, str]] = []
    if bad_ids:
        msg = f"{len(bad_ids)} item(s) could not be read: " + ", ".join(bad_ids[:10])
        parts.append(("items_unreadable", msg))
    if favorite is not None:
        msg = f"Ignored: favorite={str(favorite).lower()} (Stash has no favorites)"
        parts.append(("option_ignored", msg))
    if not parts:
        return None
    return Problem(code=parts[0][0], message="; ".join(m for _, m in parts))
