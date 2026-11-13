"""Deterministic fixture data for backend tests and development."""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from typing import Any

from app.models import Tag

BASE: datetime = datetime(2026, 11, 8, tzinfo=UTC)

TAG_POOL: list[str] = [
    "sunset",
    "forest",
    "lantern",
    "ocean",
    "meadow",
    "candle",
    "river",
    "hill",
    "cloud",
    "moon",
    "star",
    "dawn",
    "dusk",
    "wave",
    "shore",
    "bloom",
    "petal",
    "branch",
    "stone",
    "moss",
    "fern",
    "vine",
    "leaf",
    "bark",
    "root",
    "seed",
    "grain",
    "wheat",
    "corn",
    "hay",
    "straw",
    "flax",
    "linen",
    "cotton",
    "silk",
    "wool",
    "fur",
    "feather",
    "wing",
    "tail",
    "claw",
    "horn",
    "fang",
    "scale",
    "shell",
    "pearl",
    "coral",
    "kelp",
    "algae",
    "lotus",
    "rose",
    "orchid",
    "peony",
    "daisy",
    "tulip",
    "iris",
    "poppy",
    "clover",
    "thistle",
    "dandelion",
    "violet",
    "quartz",
    "granite",
    "marble",
    "slate",
    "basalt",
    "flint",
    "amber",
    "opal",
    "jade",
    "ivory",
    "onyx",
    "ruby",
    "sapphire",
    "garnet",
    "topaz",
    "beryl",
    "malachite",
    "turquoise",
    "obsidian",
]

SCOPES: tuple[str, ...] = ("artist", "character", "series")
WARN_TAGS: list[str] = ["warn_alpha", "warn_beta"]
REJECT_TAGS: list[str] = ["reject_alpha"]
BASE_LIST: list[str] = ["base_one", "base_two", "base_three"]

_ASPECTS: tuple[tuple[int, int], ...] = (
    (1920, 1280),
    (1280, 1920),
    (1600, 1600),
    (1920, 1080),
)
_PAGE_PATTERN: tuple[int, ...] = (8, 10, 12, 14, 9)
_WEB_SOURCES: tuple[str, ...] = ("danbooru", "gelbooru", "nhentai", "rule34")
# Fixture media URLs carry this query so they never share a browser cache entry with real ones.
FIXTURE_SRC = "?src=fixture"


def _iso(offset_hours: int) -> str:
    return (BASE - timedelta(hours=offset_hours)).isoformat()


def _has_reject(tags: list[Tag]) -> bool:
    return any(t.name in REJECT_TAGS for t in tags)


def make_tags(rng: random.Random, n: int) -> list[Tag]:
    """Return *n* pool tags (~25 % scoped); ~4 % add a WARN tag, ~2 % a REJECT tag."""
    tags: list[Tag] = []
    for _ in range(n):
        word = rng.choice(TAG_POOL)
        scope = rng.choice(SCOPES) if rng.random() < 0.25 else None
        tags.append(Tag(name=word, scope=scope))
    if rng.random() < 0.04:
        tags.append(Tag(name=rng.choice(WARN_TAGS), scope=None))
    if rng.random() < 0.02:
        tags.append(Tag(name=REJECT_TAGS[0], scope=None))
    return tags


def build_images() -> list[dict[str, Any]]:
    rng = random.Random(20261108)
    items: list[dict[str, Any]] = []
    for i in range(200):
        w, h = _ASPECTS[(i % 40) % 4]
        tags = make_tags(rng, rng.randint(3, 8))
        item: dict[str, Any] = {
            "id": str(i),
            "kind": "image",
            "title": f"Image {i}",
            "file_name": f"image-{i}.jpg",
            "thumb_url": f"/api/media/stash/images/{i}/thumb{FIXTURE_SRC}",
            "width": w,
            "height": h,
            "rating": rng.randint(1, 5) if rng.random() < 0.5 else None,
            "favorite": rng.random() < 0.10,
            "tags": [t.name for t in tags],
            "_tags": tags,
            "added_at": _iso(i),
        }
        if _has_reject(tags):
            item["_rejected"] = True
        items.append(item)
    return items


def build_videos() -> list[dict[str, Any]]:
    rng = random.Random(20261108)
    items: list[dict[str, Any]] = []
    for i in range(200):
        tags = make_tags(rng, rng.randint(3, 8))
        item: dict[str, Any] = {
            "id": str(i),
            "kind": "video",
            "title": f"Video {i}",
            "thumb_url": f"/api/media/stash/videos/{i}/poster{FIXTURE_SRC}",
            "width": 640,
            "height": 360,
            "duration_s": float(20 + (i * 37) % 3500),  # varied; the served mp4 is always 6 s
            "preview_url": f"/api/media/stash/scene/{i}/preview{FIXTURE_SRC}",
            "studio": f"Studio {i % 7}",
            "date": f"2026-{1 + i % 12:02d}-{1 + i % 28:02d}",
            "size_bytes": 50_000_000 + i * 1_000_003,
            "rating": rng.randint(1, 5) if rng.random() < 0.5 else None,
            "favorite": rng.random() < 0.10,
            "tags": [t.name for t in tags],
            "_tags": tags,
            "added_at": _iso(i),
        }
        if _has_reject(tags):
            item["_rejected"] = True
        items.append(item)
    return items


def build_series() -> list[dict[str, Any]]:
    rng = random.Random(20261108)
    items: list[dict[str, Any]] = []
    for s in range(40):
        tags = make_tags(rng, rng.randint(2, 5))
        item: dict[str, Any] = {
            "id": str(s),
            "kind": "series",
            "title": f"Series {s}",
            "thumb_url": f"/api/media/komga/series/{s}/thumb{FIXTURE_SRC}",
            "width": 1080,
            "height": 1620,
            "book_count": 3,
            "read_count": rng.randint(0, 3),
            "tags": [t.name for t in tags],
            "_tags": tags,
            "added_at": _iso(s),
        }
        if _has_reject(tags):
            item["_rejected"] = True
        items.append(item)
    return items


def build_books() -> list[dict[str, Any]]:
    rng = random.Random(20261108)
    items: list[dict[str, Any]] = []
    for b in range(120):
        page_count = _PAGE_PATTERN[b % 5]
        tags = make_tags(rng, rng.randint(2, 5))
        item: dict[str, Any] = {
            "id": str(b),
            "kind": "book",
            "title": f"Book {b}",
            "thumb_url": f"/api/media/komga/books/{b}/thumb{FIXTURE_SRC}",
            "width": 1080,
            "height": 1620,
            "series_id": b // 3,
            "page_count": page_count,
            "read_page": rng.randint(0, page_count),
            "tags": [t.name for t in tags],
            "_tags": tags,
            "added_at": _iso(b),
        }
        if _has_reject(tags):
            item["_rejected"] = True
        items.append(item)
    return items


def build_web(source: str) -> list[dict[str, Any]]:
    rng = random.Random(20261108)
    is_nhentai = source == "nhentai"
    items: list[dict[str, Any]] = []
    for i in range(200):
        post_id = str(100000 + i)
        w, h = _ASPECTS[i % 4]
        tags = make_tags(rng, rng.randint(3, 8))
        saved: dict[str, str] | None = None
        if rng.random() < 0.15:
            saved = {"kind": rng.choice(("image", "book")), "id": str(rng.randint(0, 199))}
        item: dict[str, Any] = {
            "post_id": post_id,
            "source": source,
            "thumb_url": f"/api/media/web/{source}/{post_id}/thumb{FIXTURE_SRC}",
            "preview_url": f"/api/media/web/{source}/{post_id}/preview{FIXTURE_SRC}",
            "title": f"Gallery {i}" if is_nhentai else None,
            "tags": tags,
            "width": w,
            "height": h,
            "page_count": rng.randint(12, 40) if is_nhentai else None,
            "target": "komga" if is_nhentai else "stash",
            "saved": saved,
            "created_at": _iso(i),
            # hidden keys for the order/rating filters; no rng so the other fields stay stable
            "_rating": "gsqe"[(i * 7 + i // 5) % 4],
            "_score": (i * 37) % 101,
        }
        if _has_reject(tags):
            item["_rejected"] = True
        items.append(item)
    return items


def build_all() -> dict[str, Any]:
    return {
        "images": build_images(),
        "videos": build_videos(),
        "series": build_series(),
        "books": build_books(),
        "web": {src: build_web(src) for src in _WEB_SOURCES},
    }
