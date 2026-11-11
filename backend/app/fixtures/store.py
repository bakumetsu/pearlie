"""Fixture store: in-memory library, web, and trash."""

from __future__ import annotations

import re
import threading
import time
import uuid
import zlib
from datetime import UTC, datetime, timedelta
from typing import Any

from app.fixtures import data
from app.fixtures.jobs import JobBoard
from app.fixtures.rules import rules
from app.models import (
    LibraryItem,
    LibraryItemDetail,
    Page,
    ProgressResult,
    RestoreResult,
    SavedRef,
    Tag,
    TrashEmptied,
    TrashItem,
    TrashList,
    TrashResult,
    WebItem,
)
from app.paging import clamp_page, pages_for

_LIBRARY_KEYS = frozenset(
    {
        "id",
        "kind",
        "title",
        "thumb_url",
        "width",
        "height",
        "rating",
        "favorite",
        "tags",
        "added_at",
        "series_id",
        "page_count",
        "read_page",
        "duration_s",
        "preview_url",
        "studio",
        "date",
        "size_bytes",
        "file_name",
        "book_count",
        "read_count",
    }
)

_WEB_KEYS = frozenset(
    {
        "post_id",
        "source",
        "thumb_url",
        "preview_url",
        "title",
        "tags",
        "width",
        "height",
        "page_count",
        "target",
        "saved",
    }
)


def _fold(s: str) -> str:
    return re.sub(r"[\s_-]", "_", s.lower())


class Store:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        raw = data.build_all()
        with self._lock:
            self.images: dict[str, dict] = {r["id"]: r for r in raw["images"]}
            self.videos: dict[str, dict] = {r["id"]: r for r in raw["videos"]}
            self.series: dict[str, dict] = {r["id"]: r for r in raw["series"]}
            self.books: dict[str, dict] = {r["id"]: r for r in raw["books"]}
            self.web: dict[str, list[dict]] = raw["web"]
            self.trash: dict[str, dict] = {}
            self.retention_days = 7
            self.jobs = JobBoard(self.web)
            self.scenario = "default"
            rules.reset()
            self.jobs.reset()

    # ── bucket helpers ─────────────────────────────────────────────

    def _bucket(self, kinds: str) -> dict | None:
        return {
            "images": self.images,
            "videos": self.videos,
            "series": self.series,
            "books": self.books,
        }.get(kinds)

    # ── visibility ─────────────────────────────────────────────────

    def visible(self, kinds: str) -> list[dict]:
        bucket = self._bucket(kinds)
        if bucket is None:
            return []
        return [r for r in bucket.values() if not r.get("_rejected")]

    def hidden_count(self, kinds: str) -> int:
        bucket = self._bucket(kinds)
        if bucket is None:
            return 0
        return sum(1 for r in bucket.values() if r.get("_rejected"))

    # ── model builders ─────────────────────────────────────────────

    def library_item(self, raw: dict) -> LibraryItem:
        kwargs = {k: v for k, v in raw.items() if not k.startswith("_") and k in _LIBRARY_KEYS}
        return LibraryItem(**kwargs)

    def _build_web_item(self, raw: dict) -> WebItem:
        kwargs: dict[str, Any] = {
            k: v for k, v in raw.items() if not k.startswith("_") and k in _WEB_KEYS
        }
        saved = raw.get("saved")
        kwargs["saved"] = SavedRef(kind=saved["kind"], id=saved["id"]) if saved else None
        kwargs["blur"] = None
        return WebItem(**kwargs)

    def library_detail(self, kinds: str, id: str) -> LibraryItemDetail | None:
        bucket = self._bucket(kinds)
        if bucket is None:
            return None
        raw = bucket.get(id)
        if raw is None or raw.get("_rejected"):
            return None
        kwargs = {k: v for k, v in raw.items() if not k.startswith("_") and k in _LIBRARY_KEYS}
        kwargs["tags"] = raw.get("_tags", [])
        if kinds == "images":
            kwargs["full_url"] = f"/api/media/stash/images/{id}/full{data.FIXTURE_SRC}"
        elif kinds == "videos":
            kwargs["stream_url"] = f"/api/media/stash/videos/{id}/stream{data.FIXTURE_SRC}"
            kwargs["mime"] = "video/mp4"
        elif kinds == "series":
            kwargs["books"] = [
                self.library_item(b)
                for b in self.books.values()
                if b.get("series_id") == int(id) and not b.get("_rejected")
            ]
        elif kinds == "books":
            kwargs["page_url"] = f"/api/media/komga/books/{id}/pages/{{n}}{data.FIXTURE_SRC}"
            kwargs["page_thumb_url"] = (
                f"/api/media/komga/books/{id}/pages/{{n}}/thumb{data.FIXTURE_SRC}"
            )
        return LibraryItemDetail(**kwargs)

    # ── search / filter ────────────────────────────────────────────

    @staticmethod
    def matches(tags: list[str], scoped: list[Tag], title: str, q: str) -> bool:
        tokens = q.split()
        folded_title = _fold(title)
        folded_tags = [_fold(t) for t in tags]
        for tok in tokens:
            if tok.startswith("-"):
                if _fold(tok[1:]) in folded_tags:
                    return False
            elif ":" in tok:
                scope, _, value = tok.partition(":")
                fv = _fold(value)
                if not any(t.scope == scope and _fold(t.name) == fv for t in scoped):
                    return False
            else:
                ft = _fold(tok)
                if ft not in folded_tags and ft not in folded_title:
                    return False
        return True

    # ── listing ────────────────────────────────────────────────────

    def list_library(
        self,
        kinds: str,
        page: int,
        page_size: int,
        q: str,
        sort: str,
        favorite: bool | None,
    ) -> Page[LibraryItem] | None:
        if self._bucket(kinds) is None:
            return None
        items = self.visible(kinds)
        if q:
            items = [
                r
                for r in items
                if self.matches(r.get("tags", []), r.get("_tags", []), r.get("title", ""), q)
            ]
        if favorite is not None:
            items = [r for r in items if r.get("favorite") is favorite]
        if sort == "rating":
            items.sort(key=lambda r: (r.get("rating") is None, -(r.get("rating") or 0)))
        elif sort == "random":
            items.sort(key=lambda r: zlib.crc32(f"{kinds}{r['id']}".encode()))
        else:
            items.sort(key=lambda r: r.get("added_at", ""), reverse=True)
        total = len(items)
        pages = pages_for(total, page_size)
        page = clamp_page(page, pages)
        start = (page - 1) * page_size
        end = start + page_size
        page_items = [self.library_item(r) for r in items[start:end]]
        next_page = page + 1 if end < total else None
        return Page(
            items=page_items,
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
            next_page=next_page,
        )

    # ── mutations ──────────────────────────────────────────────────

    def patch(
        self,
        kinds: str,
        id: str,
        rating_set: bool,
        rating: float | None,
        favorite: bool | None,
        tags: list[str] | None,
    ) -> LibraryItemDetail | None:
        bucket = self._bucket(kinds)
        if bucket is None:
            return None
        raw = bucket.get(id)
        if raw is None or raw.get("_rejected"):
            return None
        if tags is not None:
            for t in tags:
                if not t or len(t) > 64:
                    raise ValueError("tag")
        with self._lock:
            if rating_set:
                raw["rating"] = rating
            if favorite is not None:
                raw["favorite"] = favorite
            if tags is not None:
                raw["tags"] = list(tags)
                raw["_tags"] = [Tag(name=t) for t in tags]
        return self.library_detail(kinds, id)

    def delete(self, kinds: str, id: str) -> TrashResult | None:
        bucket = self._bucket(kinds)
        if bucket is None:
            return None
        with self._lock:
            raw = bucket.pop(id, None)
            if raw is None:
                return None
            token = uuid.uuid4().hex
            now = datetime.now(UTC)
            expires_dt = now + timedelta(days=self.retention_days)
            self.trash[token] = {
                "item": raw,
                "bucket": kinds,
                "trashed_at": now.timestamp(),
                "expires": expires_dt.timestamp(),
            }
        return TrashResult(
            token=token,
            expires_at=expires_dt.isoformat(),
            retention_days=self.retention_days,
            item=TrashItem(kind=raw["kind"], id=id, title=raw["title"]),
        )

    def restore(self, token: str) -> RestoreResult | None:
        with self._lock:
            entry = self.trash.pop(token, None)
            if entry is None or entry["expires"] < time.time():
                return None
            bucket = self._bucket(entry["bucket"])
            if bucket is None:
                return None
            raw = entry["item"]
            bucket[raw["id"]] = raw
        return RestoreResult(item=self.library_item(raw))

    def list_trash(self) -> TrashList:
        """List non-expired trash; expired entries are only dropped on restore (pop) and empty."""
        with self._lock:
            now = time.time()
            items = [
                TrashResult(
                    token=token,
                    expires_at=datetime.fromtimestamp(entry["expires"], UTC).isoformat(),
                    retention_days=self.retention_days,
                    item=TrashItem(
                        kind=entry["item"]["kind"],
                        id=entry["item"]["id"],
                        title=entry["item"]["title"],
                    ),
                )
                for token, entry in reversed(list(self.trash.items()))
                if entry["expires"] >= now
            ]
            items.sort(key=lambda r: r.expires_at, reverse=True)
        return TrashList(items=items, retention_days=self.retention_days)

    def empty_trash(self) -> TrashEmptied:
        """Remove all trash, counting only non-expired entries."""
        with self._lock:
            now = time.time()
            count = sum(1 for e in self.trash.values() if e["expires"] >= now)
            self.trash.clear()
        return TrashEmptied(removed=count)

    def set_retention(self, days: int) -> int:
        """Set retention, recompute every entry's expires = trashed_at + days*86400,
        drop entries whose expires < time.time(), return the count dropped.
        Idempotent."""
        with self._lock:
            now = time.time()
            self.retention_days = days
            dropped = 0
            for token in list(self.trash):
                entry = self.trash[token]
                trashed_at = entry.get("trashed_at", entry["expires"] - 7 * 86400)
                entry["expires"] = trashed_at + days * 86400
                if entry["expires"] < now:
                    del self.trash[token]
                    dropped += 1
            return dropped

    def purge_preview(self, days: int) -> int:
        """Count entries that would be purged: trashed_at + days*86400 < time.time().
        No mutation."""
        with self._lock:
            now = time.time()
            count = 0
            for entry in self.trash.values():
                trashed_at = entry.get("trashed_at", entry["expires"] - 7 * 86400)
                if trashed_at + days * 86400 < now:
                    count += 1
            return count

    def set_progress(self, book_id: str, page: int) -> ProgressResult | None:
        raw = self.books.get(book_id)
        if raw is None:
            return None
        with self._lock:
            raw["read_page"] = page
        completed = page >= raw.get("page_count", 0)
        return ProgressResult(
            page=page,
            completed=completed,
        )

    # ── web ────────────────────────────────────────────────────────

    def web_items(self, source: str) -> list[WebItem]:
        return [self._build_web_item(r) for r in self.web.get(source, []) if not r.get("_rejected")]

    def web_hidden(self, source: str) -> int:
        return sum(1 for r in self.web.get(source, []) if r.get("_rejected"))

    def web_get(self, source: str, post_id: str) -> WebItem | None:
        raw = self.web_raw(source, post_id)
        if raw is None or raw.get("_rejected"):
            return None
        return self._build_web_item(raw)

    def web_raw(self, source: str, post_id: str) -> dict | None:
        for r in self.web.get(source, []):
            if r.get("post_id") == post_id:
                return r
        return None


store = Store()
