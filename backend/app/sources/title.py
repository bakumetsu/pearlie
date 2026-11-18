"""Gallery title parser: splits a Komga-style or nhentai title into display fields."""

from __future__ import annotations

import re
from dataclasses import dataclass

LANGUAGES = frozenset(
    {
        "english",
        "japanese",
        "chinese",
        "korean",
        "spanish",
        "french",
        "german",
        "russian",
        "italian",
        "portuguese",
        "thai",
        "vietnamese",
        "indonesian",
        "polish",
        "turkish",
        "arabic",
    }
)
_EVENT = re.compile(r"\(((?:COMIC|C\d{2,3}|Comiket)[^)]*)\)", re.IGNORECASE)
_CIRCLE_ARTIST = re.compile(r"^(.*?)\s*\((.+)\)$")
_SPLIT = re.compile(r"\s--?\s")
_DROPPED_TAGS = frozenset({"digital"})


@dataclass(frozen=True)
class ParsedTitle:
    title_main: str
    title_sub: str | None
    artist: str | None
    circle: str | None
    event: str | None
    language: str | None
    translator: str | None


def parse_title(raw: str, japanese: str | None = None) -> ParsedTitle:
    """Split a title like `[Circle (Artist)] Romaji - English (C99) [English] [Translator]`.

    Line 1 is the English part, else the romaji. Line 2 is the Japanese title when given,
    else the romaji when line 1 is English, else none. `[Digital]`, a trailing
    `-nhentai-<id>.cbz` and a cut-off bracket are dropped.
    """
    s = re.sub(r"\.cbz$", "", raw, flags=re.IGNORECASE)
    s = re.sub(r"\s*-\s*nhentai-\d+$", "", s, flags=re.IGNORECASE)
    circle = artist = event = language = translator = None
    head = re.match(r"^\s*\[([^\]]+)\]\s*", s)
    if head:
        s = s[head.end() :]
        pair = _CIRCLE_ARTIST.match(head.group(1))
        if pair:
            circle, artist = pair.group(1) or None, pair.group(2)
        else:
            artist = head.group(1)
    found = _EVENT.search(s)
    if found:
        event = found.group(1)
        s = s[: found.start()] + s[found.end() :]
    for tag in re.findall(r"\[([^\]]*)\]", s):
        low = tag.strip().lower()
        if low in _DROPPED_TAGS or not low:
            continue
        if low in LANGUAGES:
            language = language or tag.strip()
        elif translator is None:
            translator = tag.strip()
    s = re.sub(r"\[[^\]]*\]", "", s)
    s = re.sub(r"\[[^\]]*$", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    romaji, english = s, ""
    cut = _SPLIT.search(s)
    if cut and cut.start() > 0:
        romaji, english = s[: cut.start()], s[cut.end() :].strip()
    jp = (japanese or "").strip()
    main = english or romaji
    sub = jp or (romaji if english else "")
    return ParsedTitle(main, sub or None, artist, circle, event, language, translator)


_KANA = re.compile(r"[぀-ヿｦ-ﾟ]")
_HAN = re.compile(r"[㐀-䶿一-鿿]")
_LATIN = re.compile(r"[A-Za-zÀ-ɏ]")


def script_of(text: str) -> str:
    """`ja` when the text has kana, `cjk` when it has Han and no Latin letters, else `latin`."""
    if _KANA.search(text):
        return "ja"
    if _HAN.search(text) and not _LATIN.search(text):
        return "cjk"
    return "latin"


def name_lines(pretty: str | None, english: str | None, japanese: str | None) -> list[str]:
    """Book name lines, at most 3: Latin name first, its Latin twin second, kana or Han last.

    Without a Latin name, one Japanese or Han name stands alone.
    """
    latin: list[str] = []
    ja: list[str] = []
    cjk: list[str] = []
    seen: set[str] = set()
    for raw in (pretty, english, japanese):
        s = (raw or "").strip()
        if not s or s.casefold() in seen:
            continue
        seen.add(s.casefold())
        {"latin": latin, "ja": ja, "cjk": cjk}[script_of(s)].append(s)
    tail = (ja + cjk)[:1]
    return (latin[:2] + tail)[:3]
