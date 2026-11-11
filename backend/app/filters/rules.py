from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from app.db import connect
from app.filters.aliases import alias_table, fold
from app.filters.baselist import BASE_LIST


@dataclass(frozen=True)
class Decision:
    """Outcome of a base-list or reject-layer check."""

    layer: str
    rule: str
    tag: str
    alias: str | None


def load_reject(db_path: Path) -> list[str]:
    """Read the enabled user reject entries (`scope:pattern` or `pattern`) from the rules table."""
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT pattern, scope FROM rules WHERE list = 'reject' AND enabled = 1 ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    return [f"{r['scope']}:{r['pattern']}" if r["scope"] else r["pattern"] for r in rows]


def _tag_sets(post_tags: dict[str, list[str]]) -> tuple[set[str], set[str]]:
    """Build the bare and scoped folded tag sets from a post's tags."""
    bare: set[str] = set()
    scoped: set[str] = set()
    for scope, names in post_tags.items():
        for name in names:
            bare.add(fold(name))
            if scope:
                scoped.add(fold(f"{scope}:{name}"))
    return bare, scoped


def _entry_hit(entry: str, bare: set[str], scoped: set[str]) -> bool:
    """Return True when a folded entry matches the bare or scoped sets."""
    if ":" in entry:
        return entry in scoped
    return entry in bare


def check(post_tags: dict[str, list[str]], reject: Sequence[str]) -> Decision | None:
    """Return the first matching Decision, or None when nothing matches."""
    bare, scoped = _tag_sets(post_tags)

    table = alias_table(BASE_LIST)
    for base_tag, aliases in table.items():
        if base_tag in bare:
            return Decision("base", base_tag, base_tag, None)
        for alias in aliases:
            if alias in bare:
                return Decision("base", base_tag, alias, alias)

    for entry in reject:
        fe = fold(entry)
        if _entry_hit(fe, bare, scoped):
            return Decision("reject", entry, fe, None)

    return None


class StaleVersion(Exception):
    """Raised when the rules version has changed since it was read."""


@dataclass(frozen=True)
class RuleSet:
    """A snapshot of all enabled rules."""

    version: int
    reject: list[str]
    warn: list[str]
    require: list[str]
    mapping: list[tuple[str, str]]


@dataclass(frozen=True)
class Verdict:
    """The result of evaluating a post against a RuleSet."""

    decision: str
    layer: str
    rule: str
    tag: str
    alias: str | None


def _split(entry: str) -> tuple[str | None, str]:
    """Split a `scope:name` entry; returns (None, entry) when no colon."""
    if ":" in entry:
        scope, name = entry.split(":", 1)
        return scope, name
    return None, entry


def _join(scope: str | None, pattern: str) -> str:
    """Inverse of _split: reassemble scope and pattern into a single entry."""
    return f"{scope}:{pattern}" if scope else pattern


def load_rules(db_path: Path) -> RuleSet:
    """Load all enabled rules grouped by list type, plus the current version."""
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT list, pattern, scope, target FROM rules WHERE enabled = 1 ORDER BY id"
        ).fetchall()
        row = conn.execute("SELECT value FROM settings WHERE key = 'rules.version'").fetchone()
    finally:
        conn.close()

    version = int(row["value"]) if row else 1
    reject: list[str] = []
    warn: list[str] = []
    require: list[str] = []
    mapping: list[tuple[str, str]] = []
    for r in rows:
        entry = _join(r["scope"], r["pattern"])
        if r["list"] == "reject":
            reject.append(entry)
        elif r["list"] == "warn":
            warn.append(entry)
        elif r["list"] == "require":
            require.append(entry)
        elif r["list"] == "mapping":
            mapping.append((entry, r["target"]))
    return RuleSet(version, reject, warn, require, mapping)


def save_rules(db_path: Path, expected_version: int, new: RuleSet) -> int:
    """Atomically replace all rules; raises StaleVersion on version mismatch."""
    conn = connect(db_path)
    conn.isolation_level = None
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT value FROM settings WHERE key = 'rules.version'").fetchone()
        version = int(row["value"]) if row else 1
        if version != expected_version:
            conn.execute("ROLLBACK")
            raise StaleVersion()
        conn.execute("DELETE FROM rules WHERE list IN ('reject','warn','require','mapping')")
        for entry in new.reject:
            scope, pattern = _split(entry)
            conn.execute(
                "INSERT INTO rules (list, pattern, scope, enabled) VALUES ('reject', ?, ?, 1)",
                (pattern, scope),
            )
        for entry in new.warn:
            scope, pattern = _split(entry)
            conn.execute(
                "INSERT INTO rules (list, pattern, scope, enabled) VALUES ('warn', ?, ?, 1)",
                (pattern, scope),
            )
        for entry in new.require:
            scope, pattern = _split(entry)
            conn.execute(
                "INSERT INTO rules (list, pattern, scope, enabled) VALUES ('require', ?, ?, 1)",
                (pattern, scope),
            )
        for pattern, target in new.mapping:
            scope, pat = _split(pattern)
            conn.execute(
                "INSERT INTO rules (list, pattern, scope, enabled, target) "
                "VALUES ('mapping', ?, ?, 1, ?)",
                (pat, scope, target),
            )
        new_version = expected_version + 1
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('rules.version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(new_version),),
        )
        conn.execute("COMMIT")
        return new_version
    except StaleVersion:
        raise
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def evaluate(post_tags: dict[str, list[str]], rules: RuleSet) -> Verdict | None:
    """Evaluate a post's tags against a RuleSet; first match decides."""
    bare, scoped = _tag_sets(post_tags)

    d = check(post_tags, rules.reject)
    if d:
        return Verdict("reject", d.layer, d.rule, d.tag, d.alias)

    if rules.require and not any(_entry_hit(fold(e), bare, scoped) for e in rules.require):
        return Verdict("require_missing", "require", rules.require[0], "", None)

    for entry in rules.warn:
        fe = fold(entry)
        if _entry_hit(fe, bare, scoped):
            return Verdict("warn", "warn", entry, fe, None)

    return None
