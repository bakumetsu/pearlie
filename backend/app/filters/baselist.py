from __future__ import annotations

from pathlib import Path

from app.filters.aliases import fold


class BaseListError(RuntimeError):
    """Raised when the base list file is missing, unreadable, or empty."""


def load_base_list(path: Path) -> dict[str, tuple[str, ...]]:
    """Parse *path* into a mapping of folded tag to tuple of folded aliases."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise BaseListError(f"cannot read base list: {exc}") from exc

    result: dict[str, tuple[str, ...]] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" in stripped:
            tag_part, alias_part = stripped.split(":", 1)
            tag = fold(tag_part)
            aliases = tuple(fold(a.strip()) for a in alias_part.split(",") if a.strip())
        else:
            tag = fold(stripped)
            aliases = ()
        result[tag] = result.get(tag, ()) + aliases

    if not result:
        raise BaseListError("base list contains zero entries")
    return result


BASE_LIST: dict[str, tuple[str, ...]] = load_base_list(Path(__file__).with_name("base_list.txt"))
