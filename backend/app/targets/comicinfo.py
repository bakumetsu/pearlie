"""Build a deterministic CBZ (pages + ComicInfo.xml) for a gallery."""

from __future__ import annotations

import zipfile
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING
from xml.etree import ElementTree as ET

from app.sources.base import Post

if TYPE_CHECKING:
    from app.targets.placement import Plan

FIXED_TIME = (1980, 1, 1, 0, 0, 0)
LANG_ISO = {
    "english": "en",
    "japanese": "ja",
    "chinese": "zh",
    "korean": "ko",
    "french": "fr",
    "german": "de",
    "spanish": "es",
    "russian": "ru",
}


def comic_info(post: Post, page_count: int, placement: Plan | None = None) -> bytes:
    """ComicInfo.xml bytes for a post (names escaped by ElementTree)."""
    root = ET.Element("ComicInfo")

    def add(tag: str, value: str | None) -> None:
        if value:
            ET.SubElement(root, tag).text = value

    parody = post.tags.get("parody", [])
    artists = ", ".join(post.tags.get("artist", []))
    add("Title", post.title)
    if placement is None:
        add("Series", parody[0] if parody else post.title)
    elif placement.kind == "series":
        add("Series", placement.series)
        if placement.number:
            add("Number", placement.number)
    add("Tags", ", ".join(post.tags.get("general", [])))
    add("Genre", ", ".join(post.tags.get("category", [])))
    add("Writer", artists)
    add("Penciller", artists)
    langs = post.tags.get("language", [])
    iso = next((LANG_ISO[n.lower()] for n in langs if n.lower() in LANG_ISO), None)
    add("LanguageISO", iso)
    add("PageCount", str(page_count))
    add("Web", post.source_url)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _entry(zf: zipfile.ZipFile, name: str, data: bytes) -> None:
    info = zipfile.ZipInfo(name, FIXED_TIME)
    info.compress_type = zipfile.ZIP_STORED
    info.external_attr = 0o644 << 16
    zf.writestr(info, data)


def build_cbz(dest: Path, pages: Sequence[Path], post: Post, placement: Plan | None = None) -> None:
    """Write pages as 001.ext... plus ComicInfo.xml into dest, byte-for-byte repeatable."""
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_STORED) as zf:
        for n, page in enumerate(pages, 1):
            _entry(zf, f"{n:03d}{page.suffix.lower()}", page.read_bytes())
        _entry(zf, "ComicInfo.xml", comic_info(post, len(pages), placement))
