"""Fixture-mode search paging."""
from __future__ import annotations


def test_fixture_search_single_page_size(client):
    """A single-source search honours page_size and reports page count."""
    r = client.get("/api/search?sources=danbooru&page_size=20")
    assert r.status_code == 200
    section = r.json()["sections"][0]
    assert len(section["items"]) <= 20
    assert section["page_size"] == 20
    assert section["pages"] is not None
    assert section["pages"] >= 1


def test_fixture_search_page_clamped(client):
    """Requesting a page beyond the last one clamps to the last page."""
    r = client.get("/api/search?sources=danbooru&page_size=20&page=999")
    assert r.status_code == 200
    section = r.json()["sections"][0]
    assert len(section["items"]) > 0
    assert section["next_page"] is None


def test_fixture_search_multi_has_no_page_size(client):
    """With multiple sources every section reports page_size as None."""
    r = client.get("/api/search?sources=danbooru,stash_images")
    assert r.status_code == 200
    for section in r.json()["sections"]:
        assert section["page_size"] is None


def test_fixture_search_library_pages(client):
    """A library source with page_size reports a valid page count."""
    r = client.get("/api/search?sources=stash_images&page_size=20")
    assert r.status_code == 200
    section = r.json()["sections"][0]
    assert section["page_size"] == 20
    assert section["pages"] >= 1
