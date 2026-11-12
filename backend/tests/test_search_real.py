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


def test_search_page_size_sent_upstream(tmp_path):
    """page_size is forwarded as limit to danbooru and reflected in the section."""
    recorded: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        recorded["url"] = request.url
        return httpx.Response(200, json=load("search"))

    client = make_client(tmp_path, handler)
    r = client.get("/api/search?q=1girl&sources=danbooru&page_size=20")
    assert r.status_code == 200
    assert recorded["url"].params["limit"] == "20"
    section = r.json()["sections"][0]
    assert section["page_size"] == 20
    assert section["pages"] is None
    assert section["total"] is None


def test_search_page_size_default_60(tmp_path):
    """Without an explicit page_size the default of 60 is used."""
    recorded: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        recorded["url"] = request.url
        return httpx.Response(200, json=load("search"))

    client = make_client(tmp_path, handler)
    r = client.get("/api/search?q=1girl&sources=danbooru")
    assert r.status_code == 200
    assert recorded["url"].params["limit"] == "60"
    assert r.json()["sections"][0]["page_size"] == 60


def test_search_page_size_over_cap_rejected(tmp_path):
    """page_size above 200 is rejected with a 422."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("handler should not be called")

    client = make_client(tmp_path, handler)
    r = client.get("/api/search?sources=danbooru&page_size=201")
    assert r.status_code == 422


def test_search_multi_ignores_page_size(tmp_path):
    """With multiple sources page_size is ignored; limit defaults to 60."""
    recorded: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        recorded["url"] = request.url
        return httpx.Response(200, json=load("search"))

    client = make_client(tmp_path, handler)
    r = client.get("/api/search?q=1girl&sources=danbooru,gelbooru&page_size=20")
    assert r.status_code == 200
    section = r.json()["sections"][0]
    assert section["page_size"] is None
    assert recorded["url"].params["limit"] == "60"


def test_search_page_size_is_what_source_used(tmp_path):
    """page_size is clamped by the source cap and reflected in section and limit."""
    recorded: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        recorded["url"] = request.url
        return httpx.Response(200, json=load("search"))

    client = make_client(tmp_path, handler)
    r = client.get("/api/search?q=1girl&sources=danbooru&page_size=200")
    assert r.status_code == 200
    section = r.json()["sections"][0]
    assert section["page_size"] == 200
    assert recorded["url"].params["limit"] == "200"


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


STASH_URL = "http://stash.test"
STASH_KEY = "s-secret-456"
KOMGA_URL = "http://komga.test"
KOMGA_KEY = "k-secret-123"


def make_library_client(tmp_path, stash_handler=None, komga_handler=None):
    """Build a real-mode client with mock-backed Stash and/or Komga (None = not configured)."""
    from app.komga import Komga
    from app.targets.stash_client import StashClient

    app = create_app(
        Settings(
            mode="real",
            real="search",
            db_path=tmp_path / "p.db",
            static_dir=tmp_path / "nostatic",
            _env_file=None,  # pyright: ignore[reportCallIssue]
        )
    )
    app.state.stash = (
        StashClient(
            STASH_URL,
            STASH_KEY,
            client=httpx.Client(
                base_url=STASH_URL, transport=httpx.MockTransport(stash_handler)
            ),
        )
        if stash_handler
        else None
    )
    app.state.komga = (
        Komga(
            KOMGA_URL,
            KOMGA_KEY,
            client=httpx.Client(
                base_url=KOMGA_URL, transport=httpx.MockTransport(komga_handler)
            ),
        )
        if komga_handler
        else None
    )
    return TestClient(app)


def _stash_ok(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    if "findScenes" in body["query"]:
        scene = {
            "id": "2",
            "title": "Scene",
            "rating100": 60,
            "created_at": "2024-02-01T00:00:00Z",
            "urls": [],
            "tags": [{"name": "t"}],
            "files": [{"basename": "c.mp4", "width": 10, "height": 10, "duration": 5.0, "size": 9}],
        }
        return httpx.Response(
            200, json={"data": {"findScenes": {"count": 1, "filesize": 9, "scenes": [scene]}}}
        )
    image = {
        "id": "1",
        "title": "Image",
        "rating100": 80,
        "created_at": "2024-01-01T00:00:00Z",
        "urls": [],
        "tags": [{"name": "t"}],
        "visual_files": [{"basename": "p.jpg", "width": 10, "height": 10, "size": 9}],
    }
    return httpx.Response(
        200,
        json={
            "data": {
                "findImages": {"count": 1, "megapixels": 1.0, "filesize": 9, "images": [image]}
            }
        },
    )


def _komga_ok(request: httpx.Request) -> httpx.Response:
    book = {
        "id": "b1",
        "name": "Book",
        "created": "2026-01-01T00:00:00Z",
        "media": {"pagesCount": 5},
        "metadata": {"title": "Book One", "tags": ["x"]},
        "readProgress": None,
    }
    return httpx.Response(200, json={"content": [book], "last": True, "totalElements": 1})


def test_search_stash_images_and_videos(tmp_path):
    """Configured Stash answers image and video sections through Pearlie's media proxy."""
    client = make_library_client(tmp_path, stash_handler=_stash_ok)
    r = client.get("/api/search", params={"q": "t", "sources": "stash_images,stash_videos"})
    assert r.status_code == 200
    sections = {s["id"]: s for s in r.json()["sections"]}
    assert sections["stash_images"]["error"] is None
    assert sections["stash_images"]["items"][0]["id"] == "1"
    assert sections["stash_images"]["items"][0]["thumb_url"].startswith("/api/media/")
    assert sections["stash_videos"]["error"] is None
    assert sections["stash_videos"]["items"][0]["id"] == "2"
    assert sections["stash_videos"]["total"] == 1


def test_search_komga_books(tmp_path):
    """Configured Komga answers the books section with a single page."""
    client = make_library_client(tmp_path, komga_handler=_komga_ok)
    r = client.get("/api/search", params={"q": "x", "sources": "komga_books"})
    assert r.status_code == 200
    section = r.json()["sections"][0]
    assert section["id"] == "komga_books"
    assert section["error"] is None
    assert section["total"] == 1
    assert section["next_page"] is None
    assert section["page_size"] == 60
    assert section["items"][0]["id"] == "b1"
    assert section["items"][0]["thumb_url"] == "/api/media/komga/books/b1/thumb"


def test_search_library_not_configured(tmp_path):
    """Without Stash or Komga the old not_configured answer stays."""
    client = make_library_client(tmp_path)
    r = client.get(
        "/api/search", params={"q": "x", "sources": "stash_images,stash_videos,komga_books"}
    )
    assert r.status_code == 200
    for section in r.json()["sections"]:
        assert section["items"] == []
        assert section["error"]["code"] == "not_configured"
        assert section["error"]["message"].endswith("search is not available yet")


def test_search_library_unreachable_keeps_other_sections(tmp_path):
    """Unreachable Stash and Komga give a safe error section; no URL or key leaks."""

    def stash_down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"cannot connect to {STASH_URL} key {STASH_KEY}")

    def komga_down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"cannot connect to {KOMGA_URL} key {KOMGA_KEY}")

    client = make_library_client(tmp_path, stash_handler=stash_down, komga_handler=komga_down)
    r = client.get("/api/search", params={"sources": "stash_images,komga_books"})
    assert r.status_code == 200
    sections = {s["id"]: s for s in r.json()["sections"]}
    assert sections["stash_images"]["items"] == []
    assert sections["stash_images"]["error"] == {
        "code": "upstream_error",
        "message": "Stash is not reachable",
    }
    assert sections["komga_books"]["error"]["code"] == "upstream_error"
    assert sections["komga_books"]["error"]["message"] == "Komga is not reachable"
    for secret in (STASH_URL, STASH_KEY, KOMGA_URL, KOMGA_KEY):
        assert secret not in r.text


def test_search_library_body_has_no_service_url_or_key(tmp_path):
    """Successful library sections never carry a Stash or Komga URL or key."""
    client = make_library_client(tmp_path, stash_handler=_stash_ok, komga_handler=_komga_ok)
    r = client.get("/api/search", params={"q": "t"})
    assert r.status_code == 200
    for secret in (STASH_URL, STASH_KEY, KOMGA_URL, KOMGA_KEY):
        assert secret not in r.text
