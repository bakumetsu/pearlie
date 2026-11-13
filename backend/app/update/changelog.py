"""Changelog for Options > Update, built from commit subjects on api.github.com."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from app.db import connect
from app.update.repo import (
    SHA_RE,
    TAG_RE,
    TAGS_URL,
    compare_page_url,
    compare_url,
    release_page_url,
    tag_commits_url,
)
from app.update.version import parse_semver

_TIMEOUT = 5.0
_SETTINGS_KEY = "update.changelog"
_MAX_ITEMS = 50
PAGE_SIZE = 10
_CACHE_VERSION = 2
_KINDS = {"feat": "Added", "fix": "Fixed", "refactor": "Reworked", "perf": "Reworked"}
_ORDER = ("Added", "Fixed", "Reworked")
_KIND_TYPE = {"Added": "feat", "Fixed": "fix", "Reworked": "refactor"}
_SUBJECT_RE = re.compile(r"^(feat|fix|refactor|perf)(?:\([^)]*\))?!?:\s*(\S.*)$")

Block = dict[str, Any]


class _Unavailable(Exception):
    pass


def parse_subject(message: str) -> tuple[str, str] | None:
    """Return (kind, text) for a conventional subject worth showing, else None."""
    subject = message.split("\n", 1)[0].strip()
    m = _SUBJECT_RE.match(subject)
    if m is None:
        return None
    text = m.group(2).strip()
    return _KINDS[m.group(1)], text[0].upper() + text[1:]


def build_block(
    title: str,
    commits: list[dict[str, Any]],
    more_url: str | None,
    *,
    range_label: str | None = None,
    version: str | None = None,
    date: str | None = None,
) -> Block:
    """Group commits (newest first) into Added/Fixed/Reworked, capped at 50 items."""
    items: list[tuple[str, str]] = []
    for c in commits:
        parents = c.get("parents")
        if isinstance(parents, list) and len(parents) > 1:
            continue
        commit = c.get("commit")
        message = commit.get("message") if isinstance(commit, dict) else None
        if not isinstance(message, str):
            continue
        parsed = parse_subject(message)
        if parsed is not None:
            items.append(parsed)
    shown = items[:_MAX_ITEMS]
    groups = [
        {"kind": kind, "items": [t for k, t in shown if k == kind]}
        for kind in _ORDER
        if any(k == kind for k, _ in shown)
    ]
    return {
        "title": title,
        "range": range_label,
        "version": version,
        "date": date,
        "groups": groups,
        "total": len(items),
        "more": len(items) - len(shown),
        "more_url": more_url,
    }


def commit_date(commits: list[dict[str, Any]]) -> str | None:
    """ISO date (UTC) of the newest commit (first in the list), before any filter."""
    if not commits:
        return None
    commit = commits[0].get("commit")
    committer = commit.get("committer") if isinstance(commit, dict) else None
    raw = committer.get("date") if isinstance(committer, dict) else None
    if not isinstance(raw, str) or not re.match(r"^\d{4}-\d{2}-\d{2}", raw):
        return None
    return raw[:10]


class Changelog:
    def __init__(self, client: httpx.Client, db_path: Path, user_agent: str) -> None:
        self._client = client
        self._db_path = db_path
        self._user_agent = user_agent
        self._lock = threading.Lock()

    def get(
        self,
        channel: str,
        *,
        installed_version: str,
        installed_commit: str | None,
        installed_known: bool,
        latest_ref: str | None,
        enabled: bool,
        force: bool,
        offset: int = 0,
        limit: int = PAGE_SIZE,
    ) -> dict[str, Any]:
        """One page of the changelog; fetches only when allowed (see _part, _page)."""
        limit = max(1, min(limit, PAGE_SIZE))
        offset = max(0, offset)
        with self._lock:
            store = self._load()
            ok = True
            rb = self._release_blocks(store)
            rel_key = f"v{latest_ref}" if channel == "main" and latest_ref else None
            stale_tags = not rb["tags"] or (rel_key is not None and rb["tags"][0] != rel_key)
            refresh_tags = force or (enabled and stale_tags)
            tags_done: list[bool] = []

            def tags() -> list[str]:
                if refresh_tags and not tags_done:
                    tags_done.append(True)
                    rb["tags"] = self._tags()
                return rb["tags"]

            try:
                tags()
            except _Unavailable:
                ok = False
            names: list[str] = rb["tags"]
            releases, more_tags, next_cached, page_ok = self._page(
                rb, names, offset, limit, force or enabled
            )
            ok = ok and page_ok
            has_more = (
                more_tags
                and page_ok
                and (force or enabled or next_cached)
                and len(releases) == len(names[offset : offset + limit])
            )
            dev: Block | None = None
            whats_new: Block | None = None
            if offset == 0:
                if channel == "dev":
                    head = latest_ref if latest_ref and SHA_RE.match(latest_ref) else None
                    try:
                        dev = self._part(
                            store, "dev", head, force, enabled, lambda: self._dev_block(names)
                        )
                    except _Unavailable:
                        dev, ok = store.get("dev", {}).get("data"), False
                whats_new = self._whats_new(
                    store,
                    channel,
                    releases,
                    installed_version,
                    installed_commit,
                    installed_known,
                    latest_ref,
                    enabled,
                    force,
                )
            self._save(store)
        history: list[Block] = ([dev] if dev else []) + releases
        return {
            "channel": channel,
            "unavailable": not history and whats_new is None,
            "stale": not ok,
            "whats_new": whats_new,
            "history": history,
            "has_more": has_more,
        }

    @staticmethod
    def _release_blocks(store: dict[str, Any]) -> dict[str, Any]:
        """The per-tag block cache; an old-format cache is dropped (blocks lack a date)."""
        store.pop("releases", None)
        rb = store.get("release_blocks")
        valid = (
            isinstance(rb, dict)
            and rb.get("version") == _CACHE_VERSION
            and isinstance(rb.get("tags"), list)
            and isinstance(rb.get("blocks"), dict)
        )
        if not valid:
            rb = {"version": _CACHE_VERSION, "tags": [], "blocks": {}}
        store["release_blocks"] = rb
        return rb  # type: ignore[no-any-return]

    def _page(
        self, rb: dict[str, Any], names: list[str], offset: int, limit: int, fetch: bool
    ) -> tuple[list[Block], bool, bool, bool]:
        """Blocks for names[offset:offset+limit]: (blocks, more_tags, next_cached, ok).

        A tag block never changes, so a cached one is never refetched. Without
        permission to fetch, the page stops at the first uncached tag.
        """
        blocks: dict[str, Block] = rb["blocks"]
        picked = names[offset : offset + limit]
        out: list[Block] = []
        ok = True
        for i, tag in enumerate(picked):
            block = blocks.get(tag)
            if block is None:
                if not fetch:
                    break
                prev = names[offset + i + 1] if offset + i + 1 < len(names) else None
                try:
                    block = self._release(tag, prev)
                except _Unavailable:
                    ok = False
                    break
                blocks[tag] = block
            out.append(block)
        more_tags = len(names) > offset + limit
        next_cached = more_tags and names[offset + limit] in blocks
        return out, more_tags, next_cached, ok

    # -- cache ---------------------------------------------------------------

    @staticmethod
    def _part(
        store: dict[str, Any],
        name: str,
        key: str | None,
        force: bool,
        enabled: bool,
        build: Callable[[], Any],
    ) -> Any:
        """Cached part; refetched on force, or when missing/moved and checks are on."""
        entry: Any = store.get(name)
        have = isinstance(entry, dict) and "data" in entry
        fresh = have and (key is None or entry["key"] == key)
        if have and fresh and not force:
            return entry["data"]
        if not (force or enabled):
            return entry["data"] if have else None
        data = build()
        store[name] = {"key": key, "data": data}
        return data

    def _load(self) -> dict[str, Any]:
        try:
            with connect(self._db_path) as conn:
                row = conn.execute(
                    "SELECT value FROM settings WHERE key = ?", (_SETTINGS_KEY,)
                ).fetchone()
            data = json.loads(row["value"]) if row else {}
        except (sqlite3.Error, json.JSONDecodeError, ValueError, TypeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save(self, store: dict[str, Any]) -> None:
        try:
            with connect(self._db_path) as conn:
                conn.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (_SETTINGS_KEY, json.dumps(store)),
                )
        except sqlite3.Error:
            pass  # never let a DB failure break the card

    # -- GitHub --------------------------------------------------------------

    def _get(self, url: str) -> Any:
        headers = {"User-Agent": self._user_agent, "Accept": "application/vnd.github+json"}
        try:
            resp = self._client.get(url, headers=headers, timeout=_TIMEOUT)
            if resp.status_code != 200:
                raise _Unavailable
            return resp.json()
        except (httpx.HTTPError, ValueError) as e:
            raise _Unavailable from e

    def _compare(self, base: str, head: str) -> list[dict[str, Any]]:
        data = self._get(compare_url(base, head))
        commits = data.get("commits") if isinstance(data, dict) else None
        if not isinstance(commits, list):
            raise _Unavailable
        return [c for c in reversed(commits) if isinstance(c, dict)]  # newest first

    def _tags(self) -> list[str]:
        """Release tags, newest first."""
        data = self._get(TAGS_URL)
        if not isinstance(data, list):
            raise _Unavailable
        found: list[tuple[tuple[int, int, int], str]] = []
        for item in data:
            name = item.get("name") if isinstance(item, dict) else None
            if isinstance(name, str) and TAG_RE.match(name):
                ver = parse_semver(name[1:])
                if ver is not None:
                    found.append((ver, name))
        found.sort(reverse=True)
        return [name for _, name in found]

    def _release(self, tag: str, prev: str | None) -> Block:
        if prev is not None:
            commits = self._compare(prev, tag)
            more_url = compare_page_url(prev, tag)
        else:
            data = self._get(tag_commits_url(tag))
            if not isinstance(data, list):
                raise _Unavailable
            commits = [c for c in data if isinstance(c, dict)]
            more_url = release_page_url(tag)
        return build_block(tag, commits, more_url, version=tag[1:], date=commit_date(commits))

    def _dev_block(self, tags: list[str]) -> Block:
        if not tags:
            raise _Unavailable
        last = tags[0]
        commits = self._compare(last, "dev")
        return build_block(f"Since {last}", commits, compare_page_url(last, "dev"))

    def _whats_new(
        self,
        store: dict[str, Any],
        channel: str,
        releases: list[Block] | None,
        installed_version: str,
        installed_commit: str | None,
        installed_known: bool,
        latest_ref: str | None,
        enabled: bool,
        force: bool,
    ) -> Block | None:
        """Installed -> latest block; None for a local/unknown build or nothing newer."""
        if not installed_known or not latest_ref:
            return None
        if channel == "main":
            base = installed_version.split("-", 1)[0]
            have, want = parse_semver(base), parse_semver(latest_ref)
            if have is None or want is None or want <= have:
                return None
            picked = [
                b
                for b in releases or []
                if (v := parse_semver(b.get("version") or "")) is not None and have < v <= want
            ]
            if not picked:
                return None
            merged = [
                {"commit": {"message": f"{_KIND_TYPE[g['kind']]}: {text}"}}
                for b in picked
                for g in b["groups"]
                for text in g["items"]
            ]
            return build_block(
                "What's new",
                merged,
                compare_page_url(f"v{base}", f"v{latest_ref}"),
                range_label=f"{installed_version} → {latest_ref}",
            )
        if installed_commit is None or not SHA_RE.match(latest_ref):
            return None
        if installed_commit == latest_ref or not SHA_RE.match(installed_commit):
            return None
        try:
            block: Block | None = self._part(
                store,
                "whats_new",
                f"{installed_commit}...{latest_ref}",
                force,
                enabled,
                lambda: build_block(
                    "What's new",
                    self._compare(installed_commit, latest_ref),
                    compare_page_url(installed_commit, latest_ref),
                    range_label=f"{installed_commit[:7]} → {latest_ref[:7]}",
                ),
            )
        except _Unavailable:
            return None
        return block


class FakeChangelog:
    """Fixture-mode stand-in: canned data, no network."""

    def get(self, channel: str, **_: Any) -> dict[str, Any]:
        block = build_block(
            "v0.0.1",
            [{"commit": {"message": "feat(demo): sample change"}}],
            None,
            version="0.0.1",
        )
        return {
            "channel": channel,
            "unavailable": False,
            "stale": False,
            "whats_new": None,
            "history": [block],
            "has_more": False,
        }
