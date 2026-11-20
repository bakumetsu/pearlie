"""Debug key: one revocable, read-only credential for the /api/debug/ router (D-34).

Only a SHA-256 hash is stored (the key has 256 bits of entropy). The key is shown once at
creation and never logged. DebugKeyGuard is an ASGI middleware for the whole /api/debug prefix,
so a request that reaches no route is still answered 401 unless the key is valid.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import secrets
import sqlite3
import time
from collections import deque
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qsl

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app import logs
from app.db import connect

SETTING_KEY = "debug_key"
PREFIX = "pdk_"
GUARDED_PREFIX = "/api/debug"
TTLS: dict[str, timedelta] = {
    "1h": timedelta(hours=1),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
}
TOUCH_INTERVAL_S = 60.0
FAIL_LIMIT = 10
FAIL_WINDOW_S = 60.0
_BAD_PATH_PARTS = ("..", "//", "%", ";", "\\")
# Fixed hash so "off" costs the same hash and compare as "wrong key" (no timing tell).
_DUMMY_HASH = hashlib.sha256(b"pearlie-debug-key-off").hexdigest()

log = logging.getLogger("pearlie.debugkey")


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8", errors="replace")).hexdigest()


def _read_raw(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (SETTING_KEY,)).fetchone()
    return row["value"] if row else None


def _load(raw: str | None) -> dict | None:
    if raw is None:
        return None
    try:
        rec = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(rec, dict) or not isinstance(rec.get("hash"), str):
        return None
    return rec


def read_record(db_path: Path) -> dict | None:
    """The stored row (never holds the key), or None when the feature is off."""
    conn = connect(db_path)
    try:
        return _load(_read_raw(conn))
    finally:
        conn.close()


def create_key(db_path: Path, ttl: str) -> tuple[str, dict]:
    """Make a key and replace any old one in one statement. The key is returned once."""
    if ttl not in TTLS:
        raise ValueError("ttl must be 1h, 24h or 7d")
    key = PREFIX + secrets.token_urlsafe(32)
    digest = _digest(key)
    now = _now()
    record = {
        "id": digest[:8],
        "hash": digest,
        "created_at": _iso(now),
        "expires_at": _iso(now + TTLS[ttl]),
        "last_used_at": None,
        "uses": 0,
    }
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (SETTING_KEY, json.dumps(record)),
        )
        conn.commit()
    finally:
        conn.close()
    logs.register_secret(key)
    log.info("created kid=%s ttl=%s", record["id"], ttl)
    return key, record


def revoke_key(db_path: Path) -> None:
    conn = connect(db_path)
    try:
        record = _load(_read_raw(conn))
        conn.execute("DELETE FROM settings WHERE key = ?", (SETTING_KEY,))
        conn.commit()
    finally:
        conn.close()
    if record is not None:
        log.info("revoked kid=%s", record.get("id", "?"))


def key_status(record: dict | None) -> dict:
    """Admin view: state and counters, never the key or the hash."""
    if record is None:
        return {
            "state": "off",
            "id": None,
            "created_at": None,
            "expires_at": None,
            "last_used_at": None,
            "uses_approx": 0,
        }
    expires = _parse(record.get("expires_at"))
    expired = expires is None or expires <= _now()
    return {
        "state": "expired" if expired else "active",
        "id": record.get("id"),
        "created_at": record.get("created_at"),
        "expires_at": record.get("expires_at"),
        "last_used_at": record.get("last_used_at"),
        "uses_approx": int(record.get("uses") or 0),
    }


def authenticate(db_path: Path, token: str | None) -> dict | None:
    """The record when the token is the live key, else None.

    Wrong, expired, revoked and off all hash the token and compare once, so they look alike.
    """
    record = read_record(db_path)
    stored = record["hash"] if record is not None else _DUMMY_HASH
    match = hmac.compare_digest(_digest(token or ""), stored)
    if record is None or not match or not token:
        return None
    expires = _parse(record.get("expires_at"))
    if expires is None or expires <= _now():
        return None
    return record


def touch(db_path: Path, record: dict) -> None:
    """Update last_used_at and uses at most once per minute; never fails the request."""
    try:
        now = _now()
        last = _parse(record.get("last_used_at"))
        if last is not None and (now - last).total_seconds() < TOUCH_INTERVAL_S:
            return
        updated = {**record, "last_used_at": _iso(now), "uses": int(record.get("uses") or 0) + 1}
        conn = connect(db_path)
        try:
            raw = _read_raw(conn)
            # Compare-and-set on the old text: a replaced or revoked key is not brought back.
            current = _load(raw)
            if current is None or current.get("hash") != record["hash"]:
                return
            conn.execute(
                "UPDATE settings SET value = ? WHERE key = ? AND value = ?",
                (json.dumps(updated), SETTING_KEY, raw),
            )
            conn.commit()
        finally:
            conn.close()
    except (sqlite3.Error, OSError) as exc:
        log.warning("last-used update failed: %s", type(exc).__name__)


class FailureLimiter:
    """In-memory failure limit per peer: 10 failures in 60 s give 429 until the window clears."""

    def __init__(self, limit: int = FAIL_LIMIT, window_s: float = FAIL_WINDOW_S) -> None:
        self._limit = limit
        self._window = window_s
        self._fails: dict[str, deque[float]] = {}
        self._pending = 0
        self._last_warn = time.monotonic()

    def _prune(self, peer: str, now: float) -> deque[float]:
        q = self._fails.setdefault(peer, deque())
        while q and now - q[0] >= self._window:
            q.popleft()
        if not q:
            self._fails.pop(peer, None)
            return deque()
        return q

    def retry_after(self, peer: str) -> int:
        """Seconds to wait, or 0 when the peer may try."""
        now = time.monotonic()
        q = self._prune(peer, now)
        if len(q) < self._limit:
            return 0
        return max(1, int(self._window - (now - q[0])) + 1)

    def fail(self, peer: str) -> None:
        now = time.monotonic()
        if len(self._fails) > 1024:  # bounded memory under a spray of peers
            self._fails.clear()
        q = self._fails.setdefault(peer, deque())
        q.append(now)
        self._pending += 1
        if now - self._last_warn >= self._window:
            log.warning("auth failed n=%d peer=%s", self._pending, _clean(peer, 64))
            self._pending = 0
            self._last_warn = now


_CLEAN_RE = re.compile(r"[^\x21-\x7e]")


def _clean(value: str, limit: int) -> str:
    return _CLEAN_RE.sub("?", value)[:limit]


def _param_names(scope: Scope) -> str:
    raw = scope.get("query_string", b"").decode("latin-1")
    names: list[str] = []
    for name, _value in parse_qsl(raw, keep_blank_values=True):
        name = re.sub(r"[^A-Za-z0-9_]", "", name)[:32]
        if name and name not in names:
            names.append(name)
    return ",".join(names[:10]) or "-"


def _unauthorized() -> JSONResponse:
    return JSONResponse(
        {"code": "unauthorized", "message": "unauthorized"},
        status_code=401,
        headers={"Cache-Control": "no-store", "WWW-Authenticate": "Bearer"},
    )


def _bearer(headers: Headers) -> str | None:
    values = headers.getlist("authorization")
    if len(values) != 1 or not values[0].startswith("Bearer "):
        return None
    token = values[0][len("Bearer ") :]
    return token if token and token == token.strip() else None


class DebugKeyGuard:
    """Key check for every request under /api/debug; the key is accepted nowhere else."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.limiter = FailureLimiter()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(GUARDED_PREFIX):
            await self.app(scope, receive, send)
            return
        started = time.monotonic()
        client = scope.get("client")
        peer = client[0] if client else "-"
        wait = self.limiter.retry_after(peer)
        if wait:
            response = JSONResponse(
                {"code": "rate_limited", "message": "too many failed attempts"},
                status_code=429,
                headers={"Cache-Control": "no-store", "Retry-After": str(wait)},
            )
            await response(scope, receive, send)
            return
        db_path: Path = scope["app"].state.settings.db_path
        headers = Headers(scope=scope)
        path: str = scope["path"]
        token = _bearer(headers)
        record = authenticate(db_path, token)  # always hashes, even for a bad header
        path_ok = path.startswith(GUARDED_PREFIX + "/") and not any(
            part in path for part in _BAD_PATH_PARTS
        )
        if record is None or not path_ok:
            self.limiter.fail(peer)
            await _unauthorized()(scope, receive, send)
            return
        scope["debug_key"] = record
        status = 500

        async def wrapped(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, wrapped)
        finally:
            xff = headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
            log.info(
                "kid=%s %s %s params=%s status=%d ms=%d peer=%s xff=%s",
                record["id"],
                _clean(scope["method"], 8),
                _clean(path, 128),
                _param_names(scope),
                status,
                int((time.monotonic() - started) * 1000),
                _clean(peer, 64),
                _clean(xff, 64) or "-",
            )
            touch(db_path, record)
