"""Tests for the backend safe-mode filter."""

from __future__ import annotations

import itertools
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import connect
from app.filters.safe_mode import is_hidden_in_safe_mode
from app.models import Blur
from tests.test_search_rules_real import _client, _post, _put_rules, _section


@pytest.mark.parametrize(
    ("has_blur", "safe", "allow"), list(itertools.product([True, False], repeat=3))
)
def test_truth_table(has_blur: bool, safe: bool, allow: bool) -> None:
    """A post is hidden only when blurred, safe on and blurred tags not allowed."""
    blur = Blur(tag="x") if has_blur else None
    assert is_hidden_in_safe_mode(blur, safe, allow) is (has_blur and safe and not allow)


def _setting(client: TestClient, key: str, value: str) -> None:
    conn = connect(client.app.state.settings.db_path)  # pyright: ignore[reportAttributeAccessIssue]
    try:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        conn.commit()
    finally:
        conn.close()


def _setup(tmp_path: Path) -> TestClient:
    posts = [
        _post(1, {"general": ["plain"]}),
        _post(2, {"general": ["warnme"]}),
        _post(3, {"general": ["rejectme"]}),
    ]
    client = _client(tmp_path, posts)
    _put_rules(client, reject=["rejectme"], warn=["warnme"])
    return client


def _ids(client: TestClient, query: str = "") -> tuple[list[str], int]:
    sec = _section(client.get(f"/api/search?q=a&sources=danbooru{query}"), "danbooru")
    return [i["post_id"] for i in sec["items"]], sec["hidden"]


def test_safe_on_drops_warn(tmp_path: Path) -> None:
    """safe=1 drops the warn post; hidden counts warn and reject."""
    assert _ids(_setup(tmp_path), "&safe=1") == (["1"], 2)


def test_safe_on_allow_blurred_keeps_warn(tmp_path: Path) -> None:
    """safe=1 with allow_blurred_tags on keeps the warn post, blurred."""
    client = _setup(tmp_path)
    _setting(client, "options.global.allow_blurred_tags", "1")
    sec = _section(client.get("/api/search?q=a&sources=danbooru&safe=1"), "danbooru")
    assert [i["post_id"] for i in sec["items"]] == ["1", "2"]
    assert sec["items"][1]["blur"] == {"tag": "warnme"}
    assert sec["hidden"] == 1


def test_safe_off_keeps_warn(tmp_path: Path) -> None:
    """safe=0 keeps the warn post even when sfw is stored on."""
    client = _setup(tmp_path)
    _setting(client, "options.desktop.sfw", "1")
    assert _ids(client, "&safe=0") == (["1", "2"], 1)


def test_param_absent_uses_stored(tmp_path: Path) -> None:
    """Without the parameter the stored sfw value decides."""
    client = _setup(tmp_path)
    assert _ids(client) == (["1", "2"], 1)
    _setting(client, "options.desktop.sfw", "1")
    assert _ids(client) == (["1"], 2)
