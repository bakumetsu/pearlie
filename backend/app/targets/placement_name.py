"""Parse manga/anime release names into structured components."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedName:
    author: str
    root: str
    number: str
    is_series: bool


_KW = r"(?:volume|vol|chapter|ch|episode|issue|part|no|v|c|#)"
_VOL_RE = re.compile(
    rf"^(?P<root>.+?)(?:\s|#)\s*(?P<kw>{_KW})?\.?\s*"
    r"(?P<num>\d+(?:\.\d+)?|[IVX]{1,4})(?P<tail>[\s-].*)?$",
    re.IGNORECASE,
)
_REST_VOL_RE = re.compile(
    rf"^(?:(?:{_KW})\.?\s*)?(\d+(?:\.\d+)?|[IVX]{{1,4}})$",
    re.IGNORECASE,
)
_TRAIL_BRACKET_RE = re.compile(r"(\[[^\]]*\]|\([^()]*\))$")
_AUTHOR_TAG_RE = re.compile(r"\[[^\]]+\]")
_ACTUAL_KWS = frozenset(
    ("volume", "vol", "chapter", "ch", "episode", "issue", "part", "no", "v", "c"),
)
_ROMAN_RE = re.compile(r"^[IVX]{1,4}$")


def _roman_to_int(s: str) -> int:
    vals = {"I": 1, "V": 5, "X": 10}
    total, prev = 0, 0
    for ch in reversed(s):
        v = vals[ch]
        total += -v if v < prev else v
        prev = v
    return total


def _is_year(num: str) -> bool:
    return re.fullmatch(r"\d{4}", num) is not None and 1900 <= int(num) <= 2099


def _is_bare(kw: str | None) -> bool:
    return kw is None or kw.lower() not in _ACTUAL_KWS


def _try_volume(primary: str, hardened: bool) -> tuple[str, str] | None:
    m = _VOL_RE.match(primary)
    if not m:
        return None
    root = m.group("root").strip()
    kw = m.group("kw")
    num = m.group("num")
    tail = m.group("tail")
    if hardened:
        if _is_year(num):
            return None  # H1
        if _ROMAN_RE.match(num) and tail is not None:
            return None  # H2
        if _is_bare(kw) and tail is not None:
            return None  # H3
    if _ROMAN_RE.match(num):
        num = str(_roman_to_int(num))
    return root, num


def parse_name(
    title: str,
    artists: Sequence[str] = (),
    hardened: bool = True,
) -> ParsedName:
    # 1. Clean trailing bracket groups
    s = title.strip()
    while True:
        m = _TRAIL_BRACKET_RE.search(s)
        if not m:
            break
        s = s[: m.start()].rstrip()
        s = s.strip()

    # 2. Author
    am = _AUTHOR_TAG_RE.search(s)
    if am:
        author = am.group(0)
        title_part = s[am.end() :].strip()
    else:
        author = f"[{artists[0]}]" if artists else ""
        title_part = s

    # 3. Cut at first ~ or 〜
    cuts = [i for i in (title_part.find("~"), title_part.find("〜")) if i != -1]
    if cuts:
        title_part = title_part[: min(cuts)].strip()

    # 4. Split at first " - "
    parts = title_part.split(" - ", 1)
    primary = parts[0].strip()
    rest: str | None = parts[1].strip() if len(parts) > 1 else None

    # 5. Volume on primary
    vol = _try_volume(primary, hardened)
    if vol is not None:
        return ParsedName(author, vol[0], vol[1], True)

    # 6. Volume on rest
    if rest is not None:
        rm = _REST_VOL_RE.match(rest)
        if rm and not (hardened and _is_year(rm.group(1))):
            num = rm.group(1)
            if _ROMAN_RE.match(num):
                num = str(_roman_to_int(num))
            return ParsedName(author, primary, num, True)

    # 7. Fallback
    root = primary if primary else "Unknown_Title"
    return ParsedName(author, root, "", False)
