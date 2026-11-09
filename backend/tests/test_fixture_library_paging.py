"""Fixture-mode library paging."""

import math


def test_stash_images_pages(client):
    resp = client.get("/api/library/stash/images?page_size=20")
    assert resp.status_code == 200
    body = resp.json()
    assert body["pages"] == math.ceil(body["total"] / 20)
    assert body["page"] == 1
    assert len(body["items"]) <= 20


def test_stash_images_page_clamped(client):
    resp = client.get("/api/library/stash/images?page_size=20&page=999")
    assert resp.status_code == 200
    body = resp.json()
    assert body["page"] == body["pages"]
    assert body["next_page"] is None
    assert len(body["items"]) > 0


def test_komga_books_page_clamped(client):
    resp = client.get("/api/library/komga/books?page_size=20&page=999")
    assert resp.status_code == 200
    body = resp.json()
    assert body["page"] == body["pages"]
    assert body["next_page"] is None
    assert len(body["items"]) > 0


def test_komga_series_pages(client):
    resp = client.get("/api/library/komga/series?page_size=20")
    assert resp.status_code == 200
    body = resp.json()
    assert body["pages"] >= 1
