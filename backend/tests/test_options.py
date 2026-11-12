"""Options API tests."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def real_client(tmp_path: Path) -> TestClient:
    return TestClient(
        create_app(
            Settings(
                mode="real",
                real="search",
                db_path=tmp_path / "p.db",
                static_dir=tmp_path / "nostatic",
                _env_file=None,  # pyright: ignore[reportCallIssue]
            )
        )
    )


@pytest.fixture(params=["fixture", "real"])
def any_client(request, client, tmp_path: Path) -> TestClient:
    if request.param == "fixture":
        return client
    return real_client(tmp_path)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


def test_defaults(any_client: TestClient) -> None:
    from app.sources.throttle import DEFAULT_PACE

    r = any_client.get("/api/options")
    assert r.status_code == 200
    expected_pace = {
        site: {"value": d, "default": d, "locked": False, "backing_off": False}
        for site, d in DEFAULT_PACE.items()
    }
    assert r.json() == {
        "sfw": False,
        "sfw_set": False,
        "player_rate": 1.0,
        "player_rate_set": False,
        "profile": "desktop",
        "backdrop_strength": 60,
        "backdrop_wall": True,
        "backdrop_item": True,
        "backdrop_lightbox": True,
        "allow_blurred_tags": False,
        "trash_retention_days": 7,
        "infinite_scroll": False,
        "source_pace": expected_pace,
        "hidden_sites": [],
        "site_order": ["danbooru", "gelbooru", "rule34", "nhentai"],
    }


def test_infinite_scroll_off_then_saved(any_client: TestClient) -> None:
    assert any_client.get("/api/options").json()["infinite_scroll"] is False
    r = any_client.put("/api/options", json={"infinite_scroll": True})
    assert r.status_code == 200
    assert r.json()["infinite_scroll"] is True
    assert any_client.get("/api/options").json()["infinite_scroll"] is True
    # Global: the touch profile sees the same value
    touch = any_client.get("/api/options", headers={"X-Pearlie-Device": "touch"})
    assert touch.json()["infinite_scroll"] is True
    r = any_client.put("/api/options", json={"infinite_scroll": False})
    assert r.json()["infinite_scroll"] is False


def test_infinite_scroll_rejects_non_bool(any_client: TestClient) -> None:
    r = any_client.put("/api/options", json={"infinite_scroll": "yes"})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Partial PUT then GET
# ---------------------------------------------------------------------------


def test_partial_put_then_get(any_client: TestClient) -> None:
    r = any_client.put("/api/options", json={"sfw": True, "backdrop_strength": 80})
    assert r.status_code == 200
    data = r.json()
    assert data["sfw"] is True
    assert data["sfw_set"] is True
    assert data["backdrop_strength"] == 80
    # Untouched fields keep defaults
    assert data["player_rate"] == 1.0
    assert data["player_rate_set"] is False
    assert data["backdrop_wall"] is True
    assert data["trash_retention_days"] == 7

    r2 = any_client.get("/api/options")
    assert r2.status_code == 200
    assert r2.json() == data


# ---------------------------------------------------------------------------
# Profile separation vs global sharing
# ---------------------------------------------------------------------------


def test_profiles_separate_sf_rate_global_shared(any_client: TestClient) -> None:
    # Write sfw + rate on desktop
    any_client.put(
        "/api/options",
        json={"sfw": True, "player_rate": 1.5},
        headers={"X-Pearlie-Device": "desktop"},
    )
    # Write backdrop on desktop
    any_client.put(
        "/api/options",
        json={"backdrop_strength": 90},
        headers={"X-Pearlie-Device": "desktop"},
    )

    # Desktop sees its own profile values
    d = any_client.get(
        "/api/options", headers={"X-Pearlie-Device": "desktop"}
    ).json()
    assert d["sfw"] is True
    assert d["sfw_set"] is True
    assert d["player_rate"] == 1.5
    assert d["player_rate_set"] is True
    assert d["backdrop_strength"] == 90

    # Touch sees default profile values but shared global
    t = any_client.get(
        "/api/options", headers={"X-Pearlie-Device": "touch"}
    ).json()
    assert t["sfw"] is False
    assert t["sfw_set"] is False
    assert t["player_rate"] == 1.0
    assert t["player_rate_set"] is False
    assert t["backdrop_strength"] == 90  # shared


# ---------------------------------------------------------------------------
# Header beats UA
# ---------------------------------------------------------------------------


def test_header_beats_ua(any_client: TestClient) -> None:
    # Header says desktop, UA says iPhone (touch) -> header wins
    r = any_client.get(
        "/api/options",
        headers={
            "X-Pearlie-Device": "desktop",
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0)",
        },
    )
    assert r.status_code == 200
    assert r.json()["profile"] == "desktop"

    # Header says touch, UA says Windows Chrome (desktop) -> header wins
    r2 = any_client.get(
        "/api/options",
        headers={
            "X-Pearlie-Device": "touch",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/120.0",
        },
    )
    assert r2.status_code == 200
    assert r2.json()["profile"] == "touch"


# ---------------------------------------------------------------------------
# UA fallback
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ua,expected",
    [
        ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0)", "touch"),
        ("Mozilla/5.0 (iPad; CPU OS 17_0)", "touch"),
        ("Mozilla/5.0 (Linux; Android 14)", "touch"),
        ("Mozilla/5.0 (Mobile; some-thing)", "touch"),
        ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0", "desktop"),
        ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) Safari/605.1.15", "desktop"),
    ],
)
def test_ua_fallback(any_client: TestClient, ua: str, expected: str) -> None:
    r = any_client.get(
        "/api/options",
        headers={"User-Agent": ua},
    )
    assert r.status_code == 200
    assert r.json()["profile"] == expected


def test_invalid_header_falls_to_ua(any_client: TestClient) -> None:
    r = any_client.get(
        "/api/options",
        headers={
            "X-Pearlie-Device": "tablet",  # not a valid value
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0)",
        },
    )
    assert r.status_code == 200
    assert r.json()["profile"] == "touch"

    r2 = any_client.get(
        "/api/options",
        headers={
            "X-Pearlie-Device": "tablet",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/120.0",
        },
    )
    assert r2.json()["profile"] == "desktop"


# ---------------------------------------------------------------------------
# *_set flips only after write
# ---------------------------------------------------------------------------


def test_set_flags_flip_on_write(any_client: TestClient) -> None:
    # Initially unset
    d = any_client.get("/api/options").json()
    assert d["sfw_set"] is False
    assert d["player_rate_set"] is False

    # Write sfw only
    any_client.put("/api/options", json={"sfw": False})
    d = any_client.get("/api/options").json()
    assert d["sfw_set"] is True
    assert d["player_rate_set"] is False

    # Write player_rate
    any_client.put("/api/options", json={"player_rate": 0.75})
    d = any_client.get("/api/options").json()
    assert d["sfw_set"] is True
    assert d["player_rate_set"] is True
    assert d["player_rate"] == 0.75


# ---------------------------------------------------------------------------
# Validation 422
# ---------------------------------------------------------------------------


def test_invalid_rate(any_client: TestClient) -> None:
    r = any_client.put("/api/options", json={"player_rate": 3})
    assert r.status_code == 422


def test_invalid_strength(any_client: TestClient) -> None:
    r = any_client.put("/api/options", json={"backdrop_strength": 101})
    assert r.status_code == 422


def test_invalid_retention(any_client: TestClient) -> None:
    r = any_client.put("/api/options", json={"trash_retention_days": 0})
    assert r.status_code == 422


def test_unknown_field(any_client: TestClient) -> None:
    r = any_client.put("/api/options", json={"nonexistent": True})
    assert r.status_code == 422


def test_corrupt_stored_values_fall_back_to_defaults(tmp_path: Path) -> None:
    import sqlite3

    c = real_client(tmp_path)
    assert c.get("/api/options").status_code == 200
    conn = sqlite3.connect(str(tmp_path / "p.db"))
    conn.executemany(
        "INSERT INTO settings (key, value) VALUES (?, ?)",
        [
            ("options.desktop.player_rate", "fast"),
            ("options.global.backdrop_strength", "x"),
            ("options.global.trash_retention_days", "9999"),
        ],
    )
    conn.commit()
    conn.close()
    body = c.get("/api/options", headers={"X-Pearlie-Device": "desktop"}).json()
    assert body["player_rate"] == 1.0
    assert body["backdrop_strength"] == 60
    assert body["trash_retention_days"] == 365


# ---------------------------------------------------------------------------
# Source pace
# ---------------------------------------------------------------------------


def test_source_pace_put_valid(any_client: TestClient) -> None:
    r = any_client.put("/api/options", json={"source_pace": {"danbooru": 2.5}})
    assert r.status_code == 200
    assert r.json()["source_pace"]["danbooru"]["value"] == 2.5

    r2 = any_client.get("/api/options")
    assert r2.json()["source_pace"]["danbooru"]["value"] == 2.5


def test_source_pace_put_below_default(any_client: TestClient) -> None:
    r = any_client.put("/api/options", json={"source_pace": {"danbooru": 0.5}})
    assert r.status_code == 422


def test_source_pace_put_unknown_site(any_client: TestClient) -> None:
    r = any_client.put("/api/options", json={"source_pace": {"nonexistent": 2.0}})
    assert r.status_code == 422


def test_source_pace_locked(tmp_path: Path) -> None:
    app = create_app(
        Settings(
            mode="real",
            real="search",
            db_path=tmp_path / "p.db",
            static_dir=tmp_path / "nostatic",
            download_interval_s=5.0,
            _env_file=None,  # pyright: ignore[reportCallIssue]
        )
    )
    c = TestClient(app)
    r = c.get("/api/options")
    assert r.status_code == 200
    pace = r.json()["source_pace"]
    assert pace["danbooru"]["locked"] is True
    assert pace["danbooru"]["value"] == 5.0

    r2 = c.put("/api/options", json={"source_pace": {"danbooru": 2.0}})
    assert r2.status_code == 422
    assert "set in .env" in r2.json()["message"]


def test_source_pace_locked_value_floored_at_default(tmp_path: Path) -> None:
    app = create_app(
        Settings(
            mode="real",
            real="search",
            db_path=tmp_path / "p.db",
            static_dir=tmp_path / "nostatic",
            download_interval_s=0.5,
            _env_file=None,  # pyright: ignore[reportCallIssue]
        )
    )
    pace = TestClient(app).get("/api/options").json()["source_pace"]
    assert pace["danbooru"] == {**pace["danbooru"], "value": 1.0, "locked": True}
    assert pace["nhentai"]["value"] == 2.0


def test_source_pace_backing_off(any_client: TestClient) -> None:
    throttles = cast(FastAPI, any_client.app).state.throttles
    throttles["danbooru"].report(429)
    r = any_client.get("/api/options")
    assert r.json()["source_pace"]["danbooru"]["backing_off"] is True
