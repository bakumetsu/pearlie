"""Tests for the /api/logs endpoints."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest

from app import logs as logs_mod
from app.api import logs as logs_api
from app.db import connect

# ---------------------------------------------------------------------------
# Autouse fixture – identical to _reset_logging in test_logs_app.py
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_logging():
    os.environ.pop(logs_mod.ENV_DEBUG, None)
    logs_mod.clear_secrets()
    yield
    if logs_mod._handler is not None:
        logging.getLogger().removeHandler(logs_mod._handler)
        logs_mod._handler.close()
    logs_mod._handler = None
    logs_mod.clear_secrets()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _line(ts: str, level: str, logger: str, msg: str) -> str:
    """Build one log line matching the on-disk format."""
    return f"{ts} {level}  {logger}  {msg}"


def day_file(log_dir: Path, date: str, lines: list[str] | None = None) -> Path:
    """Write (or overwrite) the day file and return its path."""
    path = log_dir / f"pearlie-{date}.log"
    content = "\n".join(lines) + "\n" if lines else ""
    path.write_text(content, encoding="utf-8")
    return path


def _log_dir(client: Any) -> Path:
    """Return the log directory the running app uses."""
    d = logs_mod.log_dir()
    assert d is not None
    return d


def _collect_all_pages(
    client: Any, date: str, level: str = "debug", limit: int = 1000
) -> list[dict]:
    """Fetch every page of /api/logs/<date> and return the flat line list."""
    out: list[dict] = []
    cursor: str | None = None
    while True:
        params: dict[str, str] = {"level": level, "limit": str(limit)}
        if cursor is not None:
            params["cursor"] = cursor
        r = client.get(f"/api/logs/{date}", params=params)
        assert r.status_code == 200, r.text
        body = r.json()
        out.extend(body["lines"])
        cursor = body.get("next_cursor")
        if cursor is None:
            break
    return out


# ---------------------------------------------------------------------------
# 1 – Listing
# ---------------------------------------------------------------------------


def test_list(client: Any, settings: Any, tmp_path: Path) -> None:
    ld = _log_dir(client)
    ld.mkdir(parents=True, exist_ok=True)

    day_file(
        ld,
        "2026-11-13",
        [
            _line("2026-11-13 10:00:00.000", "INFO", "pearlie.app", "a"),
            _line("2026-11-13 10:00:01.000", "INFO", "pearlie.app", "b"),
        ],
    )
    day_file(ld, "2026-11-12", [_line("2026-11-12 10:00:00.000", "INFO", "pearlie.app", "c")])

    # non-log file that must NOT appear
    (ld / "notes.txt").write_text("ignore me", encoding="utf-8")

    # file older than keep_days (8 days) – should be purged by listing
    old = day_file(
        ld, "2026-11-01", [_line("2026-11-01 10:00:00.000", "INFO", "pearlie.app", "old")]
    )

    r = client.get("/api/logs")
    assert r.status_code == 200, r.text
    body = r.json()

    # top-level fields
    assert body["keep_days"] == 7
    assert body["dir_name"] == "logs"
    assert isinstance(body["cap_bytes"], int)
    assert body["debug"] is False

    files = body["files"]
    # newest first
    assert [f["date"] for f in files] == ["2026-11-13", "2026-11-12"]
    # notes.txt not listed
    assert all(f["date"] != "notes" for f in files)
    # per-file fields
    f0 = files[0]
    assert f0["date"] == "2026-11-13"
    assert f0["size_bytes"] > 0
    assert f0["lines"] == 2

    # old file purged
    assert not old.exists()


# ---------------------------------------------------------------------------
# 2 – Cursor paging
# ---------------------------------------------------------------------------


def test_cursor_paging(client: Any, settings: Any) -> None:
    ld = _log_dir(client)
    ld.mkdir(parents=True, exist_ok=True)
    date = "2026-11-13"
    lines = [
        _line(
            f"2026-11-13 10:{i // 60:02d}:{i % 60:02d}.000", "INFO", "pearlie.app", f"line-{i:02d}"
        )
        for i in range(25)
    ]
    day_file(ld, date, lines)

    # first page
    r = client.get(f"/api/logs/{date}", params={"limit": "10"})
    assert r.status_code == 200, r.text
    body = r.json()
    texts = [ln["text"] for ln in body["lines"]]
    assert texts == [f"line-{i:02d}" for i in range(24, 14, -1)]
    assert body["next_cursor"] is not None

    cursor = body["next_cursor"]

    # second page
    r2 = client.get(f"/api/logs/{date}", params={"limit": "10", "cursor": str(cursor)})
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    texts2 = [ln["text"] for ln in body2["lines"]]
    assert texts2 == [f"line-{i:02d}" for i in range(14, 4, -1)]

    cursor2 = body2["next_cursor"]

    # third page
    r3 = client.get(f"/api/logs/{date}", params={"limit": "10", "cursor": str(cursor2)})
    assert r3.status_code == 200, r3.text
    body3 = r3.json()
    texts3 = [ln["text"] for ln in body3["lines"]]
    assert texts3 == [f"line-{i:02d}" for i in range(4, -1, -1)]
    assert body3["next_cursor"] is None

    # no duplicates, all 25 seen
    all_texts = texts + texts2 + texts3
    assert len(all_texts) == 25
    assert len(set(all_texts)) == 25


def test_cursor_paging_big_file(client: Any, settings: Any) -> None:
    ld = _log_dir(client)
    ld.mkdir(parents=True, exist_ok=True)
    date = "2026-11-13"
    n = 3000
    lines = []
    for i in range(n):
        ts = f"2026-11-13 {10 + i // 3600:02d}:{(i // 60) % 60:02d}:{i % 60:02d}.{i % 1000:03d}"
        msg = f"line-{i:04d}-" + "x" * 30  # pad so file > 64 KB
        lines.append(_line(ts, "INFO", "pearlie.app", msg))
    day_file(ld, date, lines)
    assert (ld / f"pearlie-{date}.log").stat().st_size > 64 * 1024

    all_lines = _collect_all_pages(client, date, level="info", limit=1000)
    assert len(all_lines) == n
    # in reverse order
    assert all_lines[0]["text"].startswith(f"line-{n - 1:04d}")
    assert all_lines[-1]["text"].startswith("line-0000")
    # exactly once
    texts = [ln["text"] for ln in all_lines]
    assert len(set(texts)) == n


# ---------------------------------------------------------------------------
# 3 – Level filter
# ---------------------------------------------------------------------------


def test_level_filter(client: Any, settings: Any) -> None:
    ld = _log_dir(client)
    ld.mkdir(parents=True, exist_ok=True)
    date = "2026-11-13"
    lines = [
        _line("2026-11-13 10:00:00.000", "ERROR", "pearlie.app", "err-msg"),
        _line("2026-11-13 10:00:01.000", "WARNING", "pearlie.app", "warn-msg"),
        _line("2026-11-13 10:00:02.000", "INFO", "pearlie.app", "info-msg"),
        _line("2026-11-13 10:00:03.000", "DEBUG", "pearlie.app", "debug-msg"),
    ]
    day_file(ld, date, lines)

    # level=error → only ERROR
    r = client.get(f"/api/logs/{date}", params={"level": "error"})
    assert r.status_code == 200, r.text
    assert [ln["text"] for ln in r.json()["lines"]] == ["err-msg"]

    # level=warning → ERROR + WARNING
    r = client.get(f"/api/logs/{date}", params={"level": "warning"})
    assert r.status_code == 200
    assert len(r.json()["lines"]) == 2

    # default (info) → 3
    r = client.get(f"/api/logs/{date}")
    assert r.status_code == 200
    assert len(r.json()["lines"]) == 3

    # level=debug → all 4
    r = client.get(f"/api/logs/{date}", params={"level": "debug"})
    assert r.status_code == 200
    assert len(r.json()["lines"]) == 4

    # level=bogus → 422, code "invalid"
    r = client.get(f"/api/logs/{date}", params={"level": "bogus"})
    assert r.status_code == 422
    assert r.json()["code"] == "invalid"

    # uppercase accepted
    r = client.get(f"/api/logs/{date}", params={"level": "ERROR"})
    assert r.status_code == 200
    assert [ln["text"] for ln in r.json()["lines"]] == ["err-msg"]


# ---------------------------------------------------------------------------
# 4 – q (query) filter
# ---------------------------------------------------------------------------


def test_q_filter(client: Any, settings: Any) -> None:
    ld = _log_dir(client)
    ld.mkdir(parents=True, exist_ok=True)
    date = "2026-11-13"
    lines = [
        _line("2026-11-13 10:00:00.000", "INFO", "pearlie.app", "the Quick fox"),
        _line("2026-11-13 10:00:01.000", "INFO", "pearlie.app", "a lazy dog"),
    ]
    day_file(ld, date, lines)

    # case-insensitive substring
    r = client.get(f"/api/logs/{date}", params={"q": "quick"})
    assert r.status_code == 200, r.text
    texts = [ln["text"] for ln in r.json()["lines"]]
    assert "the Quick fox" in texts
    assert "a lazy dog" not in texts

    # unparseable raw line
    date2 = "2026-11-14"
    raw = "this is not a parseable line hello-world"
    day_file(ld, date2, [raw])
    r = client.get(f"/api/logs/{date2}", params={"q": "hello", "level": "debug"})
    assert r.status_code == 200, r.text
    ln = r.json()["lines"][0]
    assert ln["level"] == "info"
    assert ln["ts"] == ""
    assert ln["text"] == raw


# ---------------------------------------------------------------------------
# 5 – limit / cursor validation
# ---------------------------------------------------------------------------


def test_limit_and_cursor_validation(client: Any, settings: Any) -> None:
    ld = _log_dir(client)
    ld.mkdir(parents=True, exist_ok=True)
    date = "2026-11-13"
    day_file(
        ld,
        date,
        [_line("2026-11-13 10:00:00.000", "INFO", "pearlie.app", f"line-{i}") for i in range(5)],
    )

    # limit 0 → 422
    r = client.get(f"/api/logs/{date}", params={"limit": "0"})
    assert r.status_code == 422

    # limit 1001 → 422
    r = client.get(f"/api/logs/{date}", params={"limit": "1001"})
    assert r.status_code == 422

    # bad cursor "abc"
    r = client.get(f"/api/logs/{date}", params={"cursor": "abc"})
    assert r.status_code == 422

    # bad cursor "-1"
    r = client.get(f"/api/logs/{date}", params={"cursor": "-1"})
    assert r.status_code == 422

    # cursor past file size
    r = client.get(f"/api/logs/{date}", params={"cursor": "999999"})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# 6 – Bad / traversal dates
# ---------------------------------------------------------------------------

BAD_DATES = [
    "2026-13-45",
    "abc",
    "2026-11-13x",
    "..",
    "%2e%2e",
    "..%2fx",
    "%2e%2e%2f%2e%2e%2fetc%2fpasswd",
    "2026-11-13%00",
    "..%5c..%5cx",
    "2026-11-12",  # valid format but no file
]


@pytest.mark.parametrize("bad", BAD_DATES)
def test_bad_date(client: Any, settings: Any, tmp_path: Path, bad: str) -> None:
    # place a secret next to the log dir that must never be served
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP-SECRET-DATA-xyz789", encoding="utf-8")

    ld = _log_dir(client)
    ld.mkdir(parents=True, exist_ok=True)

    for ep in ("", "/download"):
        url = f"/api/logs/{bad}{ep}"
        r = client.get(url)
        assert r.status_code in (404, 422), f"bad={bad!r} ep={ep!r} got {r.status_code}"
        # secret must never leak
        assert "TOP-SECRET-DATA-xyz789" not in r.text


def test_bad_date_missing_valid(client: Any, settings: Any) -> None:
    """2026-11-12 is a valid date but no file exists → 404 code not_found."""
    r = client.get("/api/logs/2026-11-12")
    assert r.status_code == 404
    assert r.json()["code"] == "not_found"

    r = client.get("/api/logs/2026-11-12/download")
    assert r.status_code == 404
    assert r.json()["code"] == "not_found"


def test_path_traversal_never_serves_secret(client: Any, settings: Any, tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret_content = "TOP-SECRET-TRAVERSAL-abc123"
    secret.write_text(secret_content, encoding="utf-8")

    for url in ("/api/logs/../x", "/api/logs/%2e%2e/x", "/api/logs/..%2fsecret.txt"):
        r = client.get(url)
        assert secret_content not in r.text
        r2 = client.get(url.replace("/x", "/download") if "/x" in url else url + "/download")
        assert secret_content not in r2.text


# ---------------------------------------------------------------------------
# 7 – Download
# ---------------------------------------------------------------------------


def test_download(client: Any, settings: Any) -> None:
    ld = _log_dir(client)
    ld.mkdir(parents=True, exist_ok=True)
    date = "2026-11-13"
    lines = [
        _line("2026-11-13 10:00:00.000", "ERROR", "pearlie.app", "boom"),
        _line("2026-11-13 10:00:01.000", "INFO", "pearlie.app", "ok"),
    ]
    day_file(ld, date, lines)

    r = client.get(f"/api/logs/{date}/download")
    assert r.status_code == 200, r.text
    ct = r.headers["content-type"]
    assert ct.startswith("text/plain")
    assert "charset=utf-8" in ct.lower()
    assert r.headers["content-disposition"] == f'attachment; filename="pearlie-{date}.log"'
    # body contains both lines
    assert "boom" in r.text
    assert "ok" in r.text

    # level=error → only ERROR
    r = client.get(f"/api/logs/{date}/download", params={"level": "error"})
    assert r.status_code == 200
    assert "boom" in r.text
    assert "ok" not in r.text

    # level=bogus → 422
    r = client.get(f"/api/logs/{date}/download", params={"level": "bogus"})
    assert r.status_code == 422

    # scrubbing: api_key=... → ***
    date2 = "2026-11-14"
    day_file(
        ld,
        date2,
        [_line("2026-11-14 10:00:00.000", "INFO", "pearlie.app", "token api_key=abc123xyz done")],
    )
    r = client.get(f"/api/logs/{date2}/download")
    assert r.status_code == 200
    assert "abc123xyz" not in r.text
    assert "***" in r.text

    # registered secret scrubbed
    logs_mod.register_secret("SENTINEL-DL-7f3a9c")
    date3 = "2026-11-15"
    day_file(
        ld,
        date3,
        [_line("2026-11-15 10:00:00.000", "INFO", "pearlie.app", "x SENTINEL-DL-7f3a9c y")],
    )
    r = client.get(f"/api/logs/{date3}/download")
    assert r.status_code == 200
    assert "SENTINEL-DL-7f3a9c" not in r.text


# ---------------------------------------------------------------------------
# 8 – PUT /api/logs/settings
# ---------------------------------------------------------------------------


def test_put_settings_debug(client: Any, settings: Any) -> None:
    # enable
    r = client.put("/api/logs/settings", json={"debug": True})
    assert r.status_code == 200, r.text
    assert r.json() == {"debug": True}
    assert logs_mod.is_debug() is True

    # reflected in GET /api/logs
    r = client.get("/api/logs")
    assert r.status_code == 200
    assert r.json()["debug"] is True

    # persisted in db
    db = connect(settings.db_path)
    try:
        row = db.execute("SELECT value FROM settings WHERE key=?", ("logs.debug",)).fetchone()
        assert row is not None
        assert row[0] == "1"
    finally:
        db.close()

    # disable
    r = client.put("/api/logs/settings", json={"debug": False})
    assert r.status_code == 200
    assert r.json() == {"debug": False}
    assert logs_mod.is_debug() is False

    db = connect(settings.db_path)
    try:
        row = db.execute("SELECT value FROM settings WHERE key=?", ("logs.debug",)).fetchone()
        assert row is not None
        assert row[0] == "0"
    finally:
        db.close()


def test_put_settings_validation(client: Any, settings: Any) -> None:
    bad_bodies = [
        {"debug": "yes"},
        {"debug": 1},
        {},
    ]
    for body in bad_bodies:
        r = client.put("/api/logs/settings", json=body)
        assert r.status_code == 422, f"body={body} got {r.status_code}"

    # no body
    r = client.put("/api/logs/settings", content=b"", headers={"Content-Type": "application/json"})
    assert r.status_code == 422

    # extra field
    r = client.put("/api/logs/settings", json={"debug": True, "extra": 1})
    assert r.status_code == 422


def test_put_settings_csrf_origin(client: Any, settings: Any) -> None:
    r = client.put(
        "/api/logs/settings", json={"debug": True}, headers={"Origin": "http://evil.example"}
    )
    assert r.status_code == 403


@pytest.mark.no_default_origin
def test_put_settings_csrf_no_origin(client: Any, settings: Any) -> None:
    r = client.put("/api/logs/settings", json={"debug": True})
    assert r.status_code == 403


def test_put_settings_wrong_content_type(client: Any, settings: Any) -> None:
    r = client.put(
        "/api/logs/settings", content='{"debug": true}', headers={"Content-Type": "text/plain"}
    )
    assert r.status_code == 415


# ---------------------------------------------------------------------------
# 9 – GET /api/logs/settings never reads a log file
# ---------------------------------------------------------------------------


def test_get_settings_no_log_read(
    client: Any, settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(*a: Any, **kw: Any) -> Any:
        raise AssertionError("log file must not be opened")

    monkeypatch.setattr(logs_api, "_log_file", _boom)
    monkeypatch.setattr(logs_api, "_count_lines", _boom)

    r = client.get("/api/logs/settings")
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body["debug"], bool)


# ---------------------------------------------------------------------------
# 10 – Sentinel scrubbing across every endpoint
# ---------------------------------------------------------------------------


def test_sentinel_scrubbing(client: Any, settings: Any) -> None:
    SENT_A = "SENTINEL-API-KEY-5b2e91"
    SENT_B = "SENTINEL-COOKIE-77c0d4"
    BEARER = "abcdefghijklmnop"
    date = "2026-11-13"

    ld = _log_dir(client)
    ld.mkdir(parents=True, exist_ok=True)

    lines = [
        _line("2026-11-13 10:00:00.000", "INFO", "pearlie.app", f"raw {SENT_A} end"),
        _line(
            "2026-11-13 10:00:01.000", "INFO", "pearlie.app", f"enc {quote(SENT_A, safe='')} end"
        ),
        _line("2026-11-13 10:00:02.000", "INFO", "pearlie.app", f"api_key={SENT_A}"),
        _line("2026-11-13 10:00:03.000", "INFO", "pearlie.app", f"Cookie: sid={SENT_B}"),
        _line("2026-11-13 10:00:04.000", "DEBUG", "pearlie.app", f"Authorization: Bearer {BEARER}"),
        _line(
            "2026-11-13 10:00:05.000", "INFO", "pearlie.app", f"http://x.example/?token={SENT_A}"
        ),
    ]
    day_file(ld, date, lines)

    # register AFTER writing
    logs_mod.register_secret(SENT_A)
    logs_mod.register_secret(SENT_B)
    logs_mod.register_secret(BEARER)

    collected: list[str] = []

    # listing
    r = client.get("/api/logs")
    collected.append(r.text)

    # settings
    r = client.get("/api/logs/settings")
    collected.append(r.text)

    # full day at debug, all pages
    r = client.get(f"/api/logs/{date}", params={"level": "debug", "limit": "1000"})
    collected.append(r.text)
    cursor = r.json().get("next_cursor")
    while cursor is not None:
        r = client.get(
            f"/api/logs/{date}", params={"level": "debug", "limit": "1000", "cursor": str(cursor)}
        )
        collected.append(r.text)
        cursor = r.json().get("next_cursor")

    # q=sentinel
    r = client.get(f"/api/logs/{date}", params={"q": "sentinel", "level": "debug", "limit": "1000"})
    collected.append(r.text)

    # download (no level)
    r = client.get(f"/api/logs/{date}/download")
    collected.append(r.text)

    # download (level=debug)
    r = client.get(f"/api/logs/{date}/download", params={"level": "debug"})
    collected.append(r.text)

    # PUT answer
    r = client.put("/api/logs/settings", json={"debug": True})
    collected.append(r.text)

    blob = "\n".join(collected)
    assert SENT_A not in blob, "SENT_A leaked"
    assert SENT_B not in blob, "SENT_B leaked"
    assert BEARER not in blob, "BEARER leaked"
