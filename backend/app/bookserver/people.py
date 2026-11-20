"""Author of a book: the author field first, else the title prefix (D-36 section 3.2)."""

from __future__ import annotations

import re

from app.bookserver.base import BookDTO

_AUTHOR_RE = re.compile(r"^\s*\[([^\]]+)\]")
_PAIR_RE = re.compile(r"^(.*?)\s*\((.*)\)\s*$")


def title_people(title: str | None) -> tuple[str, str]:
    """(artist, group) from a `[Group (Artist)]` or `[Artist]` title prefix; empty when absent."""
    m = _AUTHOR_RE.match(title or "")
    if not m:
        return "", ""
    inner = m.group(1).strip()
    pair = _PAIR_RE.match(inner)
    if pair and pair.group(1).strip() and pair.group(2).strip():
        return pair.group(2).strip(), pair.group(1).strip()
    return inner, ""


def book_author(b: BookDTO) -> str:
    if b.authors and b.authors[0]:
        return b.authors[0]
    artist, group = title_people(b.title)
    return artist or group
