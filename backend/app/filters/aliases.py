from __future__ import annotations

import re
from collections.abc import Iterable


def fold(s: str) -> str:
    """Lowercase and normalise spaces/hyphens to underscores."""
    return re.sub(r"[ _-]+", "_", s.lower())


def folded_set(names: Iterable[str]) -> frozenset[str]:
    """Return the folded forms of *names* as a frozenset."""
    return frozenset(fold(n) for n in names)


def alias_table(entries: dict[str, tuple[str, ...]]) -> dict[str, frozenset[str]]:
    """Pre-compute per-tag alias lookups from a folded base-list mapping."""
    return {tag: frozenset(aliases) for tag, aliases in entries.items()}
