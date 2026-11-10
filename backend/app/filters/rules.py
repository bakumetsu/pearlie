from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.filters.aliases import alias_table, fold
from app.filters.baselist import BASE_LIST


@dataclass(frozen=True)
class Decision:
    """Outcome of a base-list or reject-layer check."""

    layer: str
    rule: str
    tag: str
    alias: str | None


def check(post_tags: dict[str, list[str]], reject: Sequence[str]) -> Decision | None:
    """Return the first matching Decision, or None when nothing matches."""
    bare: set[str] = set()
    scoped: set[str] = set()
    for scope, names in post_tags.items():
        for name in names:
            bare.add(fold(name))
            if scope:
                scoped.add(fold(f"{scope}:{name}"))

    table = alias_table(BASE_LIST)
    for base_tag, aliases in table.items():
        if base_tag in bare:
            return Decision("base", base_tag, base_tag, None)
        for alias in aliases:
            if alias in bare:
                return Decision("base", base_tag, alias, alias)

    for entry in reject:
        fe = fold(entry)
        if ":" in fe:
            if fe in scoped:
                return Decision("reject", entry, fe, None)
        elif fe in bare:
            return Decision("reject", entry, fe, None)

    return None
