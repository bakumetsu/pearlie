from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

import httpx

from app.update.check import FakeChecker, UpdateChecker
from app.update.repo import LATEST_RELEASE_URL, TAGS_URL


def _chk(
    db: Path,
    handler: Callable[[httpx.Request], httpx.Response],
    clock: list[float],
    floor_s: float = 300.0,
) -> UpdateChecker:
    return UpdateChecker(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        db_path=db,
        user_agent="t",
        now=lambda: clock[0],
        floor_s=floor_s,
    )


def test_main_200(tmp_path: Path) -> None:
    clock: list[float] = [1_000.0]
    seen: list[httpx.Request] = []

    def h(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json={"tag_name": "v1.2.3"}, headers={"ETag": "e1"})

    r = _chk(tmp_path / "p.db", h, clock).check("main")
    assert r.error is None
    assert r.latest is not None
    assert r.latest.version == "1.2.3"
    assert r.latest.url.endswith("/releases/tag/v1.2.3")


def test_etag_304_after_floor(tmp_path: Path) -> None:
    clock: list[float] = [1_000.0]
    seen: list[httpx.Request] = []

    def h(req: httpx.Request) -> httpx.Response:
        if str(req.url) == TAGS_URL:
            return httpx.Response(404)
        seen.append(req)
        if len(seen) == 1:
            return httpx.Response(200, json={"tag_name": "v1.2.3"}, headers={"ETag": "e1"})
        assert req.headers["If-None-Match"] == "e1"
        return httpx.Response(304)

    c = _chk(tmp_path / "p.db", h, clock)
    c.check("main")
    clock[0] += 301.0
    r = c.check("main")
    assert r.latest is not None
    assert r.latest.version == "1.2.3"
    assert r.error is None


def test_no_request_within_floor(tmp_path: Path) -> None:
    clock: list[float] = [1_000.0]
    n: list[int] = [0]

    def h(req: httpx.Request) -> httpx.Response:
        if str(req.url) == LATEST_RELEASE_URL:
            n[0] += 1
        return httpx.Response(200, json={"tag_name": "v1.2.3"})

    c = _chk(tmp_path / "p.db", h, clock)
    c.check("main")
    clock[0] += 299.0
    c.check("main")
    assert n[0] == 1


def test_rate_limited(tmp_path: Path) -> None:
    clock: list[float] = [1_000.0]

    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "9999999999"},
        )

    r = _chk(tmp_path / "p.db", h, clock).check("main")
    assert r.error == "rate_limited"
    assert r.retry_after == 9_999_999_999
    assert r.latest is None


def test_connect_error(tmp_path: Path) -> None:
    clock: list[float] = [1_000.0]

    def h(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nope")

    r = _chk(tmp_path / "p.db", h, clock).check("main")
    assert r.error == "unreachable"
    assert r.latest is None


def test_tags_fallback(tmp_path: Path) -> None:
    clock: list[float] = [1_000.0]

    def h(req: httpx.Request) -> httpx.Response:
        if str(req.url) == LATEST_RELEASE_URL:
            return httpx.Response(404)
        if str(req.url) == TAGS_URL:
            return httpx.Response(
                200,
                json=[{"name": "v1.2.0"}, {"name": "v1.10.0"}, {"name": "junk"}],
            )
        return httpx.Response(404)

    r = _chk(tmp_path / "p.db", h, clock).check("main")
    assert r.error is None
    assert r.latest is not None
    assert r.latest.version == "1.10.0"


def test_stale_release_loses_to_newer_tag(tmp_path: Path) -> None:
    clock: list[float] = [1_000.0]

    def h(req: httpx.Request) -> httpx.Response:
        if str(req.url) == LATEST_RELEASE_URL:
            return httpx.Response(200, json={"tag_name": "v0.1.0"})
        if str(req.url) == TAGS_URL:
            return httpx.Response(
                200,
                json=[{"name": "v0.1.0"}, {"name": "v0.2.2"}],
            )
        return httpx.Response(404)

    r = _chk(tmp_path / "p.db", h, clock).check("main")
    assert r.error is None
    assert r.latest is not None
    assert r.latest.version == "0.2.2"
    assert r.latest.url.endswith("/releases/tag/v0.2.2")


def test_release_equal_to_highest_tag(tmp_path: Path) -> None:
    clock: list[float] = [1_000.0]

    def h(req: httpx.Request) -> httpx.Response:
        if str(req.url) == LATEST_RELEASE_URL:
            return httpx.Response(200, json={"tag_name": "v1.2.3"})
        if str(req.url) == TAGS_URL:
            return httpx.Response(
                200,
                json=[{"name": "v1.2.3"}, {"name": "v1.0.0"}],
            )
        return httpx.Response(404)

    r = _chk(tmp_path / "p.db", h, clock).check("main")
    assert r.error is None
    assert r.latest is not None
    assert r.latest.version == "1.2.3"


def test_tags_failure_keeps_release(tmp_path: Path) -> None:
    clock: list[float] = [1_000.0]

    def h(req: httpx.Request) -> httpx.Response:
        if str(req.url) == LATEST_RELEASE_URL:
            return httpx.Response(200, json={"tag_name": "v1.2.3"})
        if str(req.url) == TAGS_URL:
            return httpx.Response(500)
        return httpx.Response(404)

    r = _chk(tmp_path / "p.db", h, clock).check("main")
    assert r.error is None
    assert r.latest is not None
    assert r.latest.version == "1.2.3"


def test_dev_good_and_bad(tmp_path: Path) -> None:
    clock: list[float] = [1_000.0]

    def h_good(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"sha": "a" * 40})

    r = _chk(tmp_path / "a.db", h_good, clock).check("dev")
    assert r.latest is not None
    assert r.latest.version == "aaaaaaa"
    assert r.latest.commit == "a" * 40

    clock2: list[float] = [1_000.0]

    def h_bad(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"sha": "xyz"})

    r2 = _chk(tmp_path / "b.db", h_bad, clock2).check("dev")
    assert r2.error == "unreachable"
    assert r2.latest is None


def test_fake_checker() -> None:
    latest = FakeChecker("available").check("main").latest
    assert latest is not None
    assert latest.version == "9.9.9"
    assert FakeChecker("unreachable").check("main").error == "unreachable"


def test_cached_new_checker(tmp_path: Path) -> None:
    clock: list[float] = [1_000.0]
    db = tmp_path / "p.db"

    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.commit()
    conn.close()

    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"tag_name": "v1.2.3"})

    _chk(db, h, clock).check("main")

    clock2: list[float] = [2_000.0]
    c2 = _chk(db, lambda r: httpx.Response(200, json={"tag_name": "v9.9.9"}), clock2)
    cached = c2.cached("main")
    assert cached is not None
    assert cached.latest is not None
    assert cached.latest.version == "1.2.3"
