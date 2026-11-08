"""Tests for the real-mode /api/search endpoint."""
from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models import SearchResponse, WebItem
from app.sources.danbooru import Danbooru
from app.sources.throttle import Throttle

FIX = Path(__file__).parent / "fixtures" / "danbooru"


def load(name: str):
    """Return parsed JSON fixture."""
    return json.loads((FIX / f"{name}.json").read_text())


def make_client(tmp_path, handler):
    """Build a TestClient with a mock-backed Danbooru source."""
    app = create_app(
        Settings(
            mode="real",
            real="search",
            db_path=tmp_path / "p.db",
            static_dir=tmp_path / "nostatic",
            _env_file=None,  # pyright: ignore[reportCallIssue]
        )
    )
    app.state.sources["danbooru"] = Danbooru(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        throttle=Throttle(0.0),
    )
    return TestClient(app)


def test_search_danbooru(tmp_path):
    """GET /api/search returns mapped danbooru results in a valid SearchResponse."""
    recorded: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        recorded["url"] = request.url
        return httpx.Response(200, json=load("search"))

    client = make_client(tmp_path, handler)
    r = client.get("/api/search?q=1girl&sources=danbooru&page=2")
    assert r.status_code == 200
    resp = SearchResponse.model_validate(r.json())
    assert len(resp.sections) == 1
    section = resp.sections[0]
    assert section.id == "danbooru"
    assert len(section.items) == 3
    first = section.items[0]
    assert isinstance(first, WebItem)
    assert first.post_id == "101"
    assert first.source == "danbooru"
    assert first.target == "stash"
    assert first.width == 1280
    assert any(t.name == "artist_a" and t.scope == "artist" for t in first.tags)
    assert recorded["url"].params["tags"] == "1girl"
    assert recorded["url"].params["page"] == "2"
    assert section.next_page is None


def test_search_unknown_source(tmp_path):
    """Requesting an unconfigured source returns 422 with an invalid code."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("handler should not be called")

    client = make_client(tmp_path, handler)
    r = client.get("/api/search?q=test&sources=nope")
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "invalid"
    assert body["field"] == "sources"


def test_search_upstream_error_is_section_error(tmp_path):
    """A 500 from upstream produces a section-level error, not an HTTP error."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = make_client(tmp_path, handler)
    r = client.get("/api/search?q=test&sources=danbooru")
    assert r.status_code == 200
    resp = SearchResponse.model_validate(r.json())
    section = resp.sections[0]
    assert section.error is not None
    assert section.error.code == "upstream_error"
    assert section.items == []


def test_search_not_connected_sections(tmp_path):
    """Sources absent from app.state.sources yield not_configured errors."""
    called: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        called.append(1)
        return httpx.Response(200, json=load("search"))

    client = make_client(tmp_path, handler)
    r = client.get("/api/search?q=test&sources=stash_images,nhentai")
    assert r.status_code == 200
    resp = SearchResponse.model_validate(r.json())
    for section in resp.sections:
        assert section.error is not None
        assert section.error.code == "not_configured"
        assert section.items == []
    assert called == []


def test_fixture_mode_unchanged(client):
    """In fixture mode /api/search serves fixture data with no error."""
    r = client.get("/api/search?sources=danbooru")
    assert r.status_code == 200
    resp = SearchResponse.model_validate(r.json())
    section = resp.sections[0]
    assert len(section.items) > 0
    assert section.error is None
    assert "search" in client.app.state.fixture_routers


def test_real_search_replaces_fixture_search(tmp_path):
    """In real mode the fixture search router is not mounted."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=load("search"))

    client = make_client(tmp_path, handler)
    assert "search" not in cast(FastAPI, client.app).state.fixture_routers


def test_search_reports_dropped_metatag(tmp_path):
    def handler(request):
        return httpx.Response(200, json=load("search"))

    client = make_client(tmp_path, handler)
    resp = client.get("/api/search", params={"q": "a b order:score", "sources": "danbooru"})
    assert resp.status_code == 200
    section = resp.json()["sections"][0]
    assert section["error"]["code"] == "filter_dropped"
    assert section["error"]["message"] == "Ignored: order:score (Danbooru allows 2 tags)"
    assert len(section["items"]) == 3


def test_search_rating_filter_has_no_error(tmp_path):
    def handler(request):
        return httpx.Response(200, json=load("search"))

    client = make_client(tmp_path, handler)
    resp = client.get("/api/search", params={"q": "a b rating:e", "sources": "danbooru"})
    assert resp.status_code == 200
    section = resp.json()["sections"][0]
    assert section["error"] is None
    assert len(section["items"]) == 1
    item = section["items"][0]
    assert item["post_id"] == "102"
