"""Quote-aware search-box tokens and the reserved `title:` chip (mirrors frontend query.ts)."""

from __future__ import annotations

from dataclasses import dataclass

TITLE_MAX = 200
RESERVED_SCOPES = ("title", "id")


@dataclass(frozen=True)
class Title:
    """One title chip: the text to match and whether it is excluded."""

    value: str
    exclude: bool = False

    @property
    def token(self) -> str:
        """Canonical token, the same text the web page keeps as the chip raw."""
        return f'{"-" if self.exclude else ""}title:"{self.value}"'


def split_terms(q: str) -> list[str]:
    """Split on whitespace and commas, but not inside quotes; quotes stay in the token."""
    out: list[str] = []
    cur: list[str] = []
    quoted = False
    for ch in q:
        if ch == '"':
            quoted = not quoted
            cur.append(ch)
        elif not quoted and (ch.isspace() or ch == ","):
            if cur:
                out.append("".join(cur))
                cur = []
        else:
            cur.append(ch)
    if cur:
        out.append("".join(cur))
    return out


def parse_title(token: str) -> Title | None:
    """The title behind a `"x"` or `title:x` token (with optional `-`), else None."""
    exclude = token.startswith("-")
    rest = token[1:] if exclude else token
    if rest.startswith('"'):
        value = rest
    elif rest.startswith("title:"):
        value = rest[len("title:") :]
    else:
        return None
    value = value.replace('"', "").strip()[:TITLE_MAX].strip()
    return Title(value, exclude) if value else None


def title_terms(tokens: list[str]) -> tuple[list[Title], list[str]]:
    """Split tokens into title chips and everything else; empty title tokens are dropped."""
    titles: list[Title] = []
    others: list[str] = []
    seen: set[str] = set()
    for tok in tokens:
        t = parse_title(tok)
        if t is not None:
            if t.token not in seen:
                seen.add(t.token)
                titles.append(t)
        elif tok.lstrip("-") not in ("", "title:") and not tok.lstrip("-").startswith('"'):
            others.append(tok)
    return titles, others


def is_reserved(entry: str) -> bool:
    """True for a rule or test tag that starts with a reserved chip scope (`title:`, `id:`)."""
    body = entry.strip().lstrip("-").lower()
    return any(body.startswith(f"{s}:") for s in RESERVED_SCOPES)
