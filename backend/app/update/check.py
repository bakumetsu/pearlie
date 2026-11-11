"""Update checker for main and dev channels."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

from app.db import connect
from app.update.repo import (
    DEV_HEAD_URL,
    DEV_TREE_URL,
    LATEST_RELEASE_URL,
    RELEASES_URL,
    SHA_RE,
    TAG_RE,
    TAGS_URL,
    release_page_url,
)
from app.update.version import parse_semver

_TIMEOUT = 5.0
_SETTINGS_KEY = "update.last"


@dataclass(frozen=True)
class Latest:
    version: str
    commit: str | None
    url: str


@dataclass(frozen=True)
class CheckResult:
    latest: Latest | None
    error: str | None
    retry_after: int | None
    checked_at: str | None


@dataclass
class _Entry:
    result: CheckResult
    etag: str | None
    last_call: float


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _latest_to_dict(latest: Latest) -> dict[str, str | None]:
    return {"version": latest.version, "commit": latest.commit, "url": latest.url}


def _latest_from_dict(d: dict[str, str | None]) -> Latest:
    return Latest(
        version=str(d["version"]),
        commit=d.get("commit") if isinstance(d.get("commit"), str) else None,
        url=str(d["url"]),
    )


def _result_from_dict(d: dict[str, object]) -> CheckResult:
    raw_latest = d.get("latest")
    latest: Latest | None = None
    if isinstance(raw_latest, dict):
        try:
            latest = _latest_from_dict(raw_latest)
        except (KeyError, TypeError):
            latest = None
    ca = d.get("checked_at")
    ra = d.get("retry_after")
    return CheckResult(
        latest=latest,
        error=None,
        retry_after=int(ra) if isinstance(ra, int) else None,
        checked_at=ca if isinstance(ca, str) else None,
    )


class UpdateChecker:
    def __init__(
        self,
        client: httpx.Client,
        db_path: Path,
        user_agent: str,
        now: Callable[[], float] = time.time,
        floor_s: float = 300.0,
    ) -> None:
        self._client = client
        self._db_path = db_path
        self._user_agent = user_agent
        self._now = now
        self._floor_s = floor_s
        self._lock = threading.Lock()
        self._cache: dict[str, _Entry] = {}

    def check(self, channel: str, force: bool = False) -> CheckResult:
        with self._lock:
            entry = self._cache.get(channel)
            if entry is not None:
                if self._now() - entry.last_call < self._floor_s:
                    return entry.result
                if entry.result.retry_after is not None and self._now() < entry.result.retry_after:
                    return entry.result

            etag = entry.etag if entry is not None else None
            cached_latest = entry.result.latest if entry is not None else None

            if channel == "main":
                result, new_etag = self._fetch_main(etag, cached_latest)
            elif channel == "dev":
                result, new_etag = self._fetch_dev(etag, cached_latest)
            else:
                result = CheckResult(None, "unreachable", None, _iso_now())
                new_etag = etag

            self._cache[channel] = _Entry(result=result, etag=new_etag, last_call=self._now())
            self._persist(channel, result)
            return result

    def cached(self, channel: str) -> CheckResult | None:
        with self._lock:
            entry = self._cache.get(channel)
            if entry is not None:
                return entry.result
        stored = self._load_db()
        if stored is None:
            return None
        data = stored.get(channel)
        if not isinstance(data, dict):
            return None
        return _result_from_dict(data)

    # -- private helpers -----------------------------------------------------

    def _hdrs(self, etag: str | None) -> dict[str, str]:
        h: dict[str, str] = {
            "User-Agent": self._user_agent,
            "Accept": "application/vnd.github+json",
        }
        if etag is not None:
            h["If-None-Match"] = etag
        return h

    @staticmethod
    def _rate_limited(resp: httpx.Response) -> int | None:
        reset = resp.headers.get("X-RateLimit-Reset")
        return int(reset) if reset is not None else None

    def _fetch_main(
        self, etag: str | None, cached_latest: Latest | None
    ) -> tuple[CheckResult, str | None]:
        hdrs = self._hdrs(etag)
        try:
            resp = self._client.get(LATEST_RELEASE_URL, headers=hdrs, timeout=_TIMEOUT)
        except httpx.HTTPError:
            return CheckResult(None, "unreachable", None, _iso_now()), etag

        if resp.status_code == 304:
            return CheckResult(cached_latest, None, None, _iso_now()), etag

        if resp.status_code in (403, 429) and resp.headers.get("X-RateLimit-Remaining") == "0":
            ra = self._rate_limited(resp)
            return CheckResult(None, "rate_limited", ra, _iso_now()), etag

        new_etag = resp.headers.get("ETag") or etag

        if resp.status_code == 200:
            try:
                data = resp.json()
            except (json.JSONDecodeError, ValueError):
                return CheckResult(None, "unreachable", None, _iso_now()), new_etag
            tag = data.get("tag_name") if isinstance(data, dict) else None
            if isinstance(tag, str) and TAG_RE.match(tag):
                latest = Latest(version=tag[1:], commit=None, url=release_page_url(tag))
                return CheckResult(latest, None, None, _iso_now()), new_etag

        # 404 or tag mismatch → fall back
        return self._fetch_tags(new_etag)

    def _fetch_tags(self, etag: str | None) -> tuple[CheckResult, str | None]:
        hdrs = self._hdrs(etag)
        try:
            resp = self._client.get(TAGS_URL, headers=hdrs, timeout=_TIMEOUT)
        except httpx.HTTPError:
            return CheckResult(None, "unreachable", None, _iso_now()), etag

        if resp.status_code in (403, 429) and resp.headers.get("X-RateLimit-Remaining") == "0":
            ra = self._rate_limited(resp)
            return CheckResult(None, "rate_limited", ra, _iso_now()), etag

        if resp.status_code != 200:
            return CheckResult(None, "unreachable", None, _iso_now()), etag

        try:
            items: object = resp.json()
        except (json.JSONDecodeError, ValueError):
            return CheckResult(None, "unreachable", None, _iso_now()), etag

        if not isinstance(items, list):
            return CheckResult(None, "unreachable", None, _iso_now()), etag

        best_ver: tuple[int, int, int] | None = None
        best_name: str | None = None
        for item in items:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not isinstance(name, str):
                continue
            if TAG_RE.match(name):
                ver = parse_semver(name)
                if ver is not None and (best_ver is None or ver > best_ver):
                    best_ver = ver
                    best_name = name

        if best_name is not None:
            latest = Latest(version=best_name[1:], commit=None, url=release_page_url(best_name))
            return CheckResult(latest, None, None, _iso_now()), etag

        return CheckResult(None, None, None, _iso_now()), etag

    def _fetch_dev(
        self, etag: str | None, cached_latest: Latest | None
    ) -> tuple[CheckResult, str | None]:
        hdrs = self._hdrs(etag)
        try:
            resp = self._client.get(DEV_HEAD_URL, headers=hdrs, timeout=_TIMEOUT)
        except httpx.HTTPError:
            return CheckResult(None, "unreachable", None, _iso_now()), etag

        if resp.status_code == 304:
            return CheckResult(cached_latest, None, None, _iso_now()), etag

        if resp.status_code in (403, 429) and resp.headers.get("X-RateLimit-Remaining") == "0":
            ra = self._rate_limited(resp)
            return CheckResult(None, "rate_limited", ra, _iso_now()), etag

        if resp.status_code != 200:
            return CheckResult(None, "unreachable", None, _iso_now()), etag

        try:
            data: object = resp.json()
        except (json.JSONDecodeError, ValueError):
            return CheckResult(None, "unreachable", None, _iso_now()), etag

        sha = data.get("sha") if isinstance(data, dict) else None
        if not isinstance(sha, str) or not SHA_RE.match(sha):
            return CheckResult(None, "unreachable", None, _iso_now()), etag

        new_etag = resp.headers.get("ETag") or etag
        latest = Latest(version=sha[:7], commit=sha, url=DEV_TREE_URL)
        return CheckResult(latest, None, None, _iso_now()), new_etag

    def _persist(self, channel: str, result: CheckResult) -> None:
        try:
            stored = self._load_db()
            if stored is None:
                stored = {}
            stored[channel] = {
                "latest": _latest_to_dict(result.latest) if result.latest else None,
                "checked_at": result.checked_at,
                "retry_after": result.retry_after,
            }
            payload = json.dumps(stored)
            with connect(self._db_path) as conn:
                conn.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (_SETTINGS_KEY, payload),
                )
        except sqlite3.Error:
            pass  # never let DB failure break the check

    def _load_db(self) -> dict[str, dict[str, object]] | None:
        try:
            with connect(self._db_path) as conn:
                row = conn.execute(
                    "SELECT value FROM settings WHERE key = ?", (_SETTINGS_KEY,)
                ).fetchone()
        except sqlite3.Error:
            return None
        if row is None:
            return None
        try:
            data: object = json.loads(row["value"])
        except (json.JSONDecodeError, ValueError, TypeError):
            return None
        if not isinstance(data, dict):
            return None
        return data  # type: ignore[return-value]


class FakeChecker:
    def __init__(self, answer: str = "available") -> None:
        self.answer = answer

    def check(self, channel: str, force: bool = False) -> CheckResult:
        ts = _iso_now()
        if self.answer == "unreachable":
            return CheckResult(None, "unreachable", None, ts)
        if channel == "dev":
            if self.answer == "available":
                sha = "abcdef1" + "0" * 33
                return CheckResult(Latest("abcdef1", sha, DEV_TREE_URL), None, None, ts)
            return CheckResult(Latest("0000000", "0" * 40, DEV_TREE_URL), None, None, ts)
        # main
        if self.answer == "available":
            return CheckResult(Latest("9.9.9", None, RELEASES_URL), None, None, ts)
        return CheckResult(Latest("0.0.0", None, RELEASES_URL), None, None, ts)

    def cached(self, channel: str) -> CheckResult | None:
        return None
