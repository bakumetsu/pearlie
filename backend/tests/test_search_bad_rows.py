"""Tests for bad-row skipping in search and short-secret warning."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import httpx

from app import logs
from app.sources.danbooru import Danbooru
from app.sources.dapi import Rule34
from app.sources.throttle import Throttle


def test_dapi_search_skips_bad_row(caplog):
    rows = [
        {
            "id": 1,
            "hash": "h1",
            "file_url": "https://x/1.jpg",
            "preview_url": "https://x/1p.jpg",
            "sample_url": "https://x/1s.jpg",
            "width": 100,
            "height": 200,
            "rating": "explicit",
            "tags": "a b",
        },
        {
            "id": 2,
            "hash": "h2",
            "file_url": "https://x/2.jpg",
            "preview_url": "https://x/2p.jpg",
            "sample_url": "https://x/2s.jpg",
            "width": "abc",
            "height": 200,
            "rating": "explicit",
            "tags": "a b",
        },
        {
            "id": 3,
            "hash": "h3",
            "file_url": "https://x/3.jpg",
            "preview_url": "https://x/3p.jpg",
            "sample_url": "https://x/3s.jpg",
            "width": 100,
            "height": 200,
            "rating": "explicit",
            "tags": "a b",
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=rows)

    src = Rule34(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        throttle=Throttle(0.0),
    )
    with caplog.at_level(logging.WARNING, logger="app.sources.dapi"):
        page = src.search(["x"])

    ids = [p.post_id for p in page.posts]
    assert ids == ["1", "3"]

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    msg = warnings[0].message
    assert "skipped 1 bad row" in msg
    assert "id=2" in msg
    assert "abc" not in msg


def test_danbooru_search_skips_bad_row(caplog):
    rows = [
        {
            "id": 1,
            "md5": "m",
            "file_url": "https://x/y.jpg",
            "image_width": 10,
            "image_height": 10,
            "rating": "g",
            "tag_string_general": "a b",
        },
        {
            "id": 2,
            "md5": "m",
            "file_url": "https://x/y.jpg",
            "image_width": 10,
            "image_height": 10,
            "rating": "g",
            "tag_string_general": 5,
        },
        {
            "id": 3,
            "md5": "m",
            "file_url": "https://x/y.jpg",
            "image_width": 10,
            "image_height": 10,
            "rating": "g",
            "tag_string_general": "a b",
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=rows)

    src = Danbooru(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        throttle=Throttle(0.0),
    )
    with caplog.at_level(logging.WARNING, logger="app.sources.danbooru"):
        page = src.search(["x"])

    ids = [p.post_id for p in page.posts]
    assert ids == ["1", "3"]

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    msg = warnings[0].message
    assert "skipped 1 bad row" in msg
    assert "id=2" in msg
    assert "abc" not in msg


def test_short_secret_warns_once_by_name(caplog):
    logs.clear_secrets()
    settings = SimpleNamespace(stash_api_key="abc", stump_api_key="long-enough-key-123")
    with caplog.at_level(logging.WARNING, logger="pearlie.logs"):
        logs.register_settings_secrets(settings)
        logs.register_settings_secrets(settings)

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    msg = warnings[0].message
    assert "stash_api_key" in msg
    assert "abc" not in msg
    assert "stump_api_key" not in msg
    assert logs.scrub("x abc y") == "x abc y"

    logs.clear_secrets()


def test_dapi_to_post_drops_duplicate_tags():
    post = Rule34._to_post(
        SimpleNamespace(_base_url="https://api.rule34.xxx", id="rule34", md5_key="hash"),  # type: ignore[arg-type]
        {"id": 1, "hash": "h", "tags": "female a female b a"},
    )
    assert post.tags == {"general": ["female", "a", "b"]}
