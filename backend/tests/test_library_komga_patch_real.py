"""Tests for real-mode Komga PATCH."""

from __future__ import annotations

import json

import httpx
from test_komga_real import KEY, book_dto, make_client, page_of, series_dto


def _make_handler(calls: list, state: dict, patch_error: bool = False):
    """Return a MockTransport handler that records (method, path, json body)."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        calls.append((request.method, request.url.path, body))
        path = request.url.path

        if request.method == "GET" and path.startswith("/api/v1/books/"):
            item_id = path.removeprefix("/api/v1/books/")
            dto = state["books"].get(item_id)
            if dto is None:
                return httpx.Response(404, json={})
            return httpx.Response(200, json=dto)

        if request.method == "GET" and path.startswith("/api/v1/series/"):
            item_id = path.removeprefix("/api/v1/series/")
            dto = state["series"].get(item_id)
            if dto is None:
                return httpx.Response(404, json={})
            return httpx.Response(200, json=dto)

        if request.method == "POST" and path == "/api/v1/books/list":
            return httpx.Response(200, json=page_of([]))

        if request.method == "PATCH" and path.endswith("/metadata"):
            if patch_error:
                return httpx.Response(500, json={"detail": "upstream failure"})
            if "/series/" in path:
                kind = "series"
                item_id = path.removeprefix("/api/v1/series/").removesuffix("/metadata")
            else:
                kind = "books"
                item_id = path.removeprefix("/api/v1/books/").removesuffix("/metadata")
            dto = state[kind].get(item_id)
            if dto is not None and body is not None:
                dto.setdefault("metadata", {})["tags"] = body.get("tags", [])
            return httpx.Response(204)

        return httpx.Response(404, json={})

    return handler


def _state() -> dict:
    return {
        "books": {"b1": book_dto()},
        "series": {"s1": series_dto()},
    }


def _client(tmp_path, calls: list, state: dict, patch_error: bool = False):
    return make_client(tmp_path, _make_handler(calls, state, patch_error))


def _tag_names(tags) -> list:
    return [t if isinstance(t, str) else t.get("name") for t in tags]


def _patch_calls(calls: list) -> list:
    return [c for c in calls if c[0] == "PATCH"]


def test_book_tags_round_trip(tmp_path):
    """Book PATCH tags updates tags and sends one metadata PATCH with tagsLock."""
    calls: list = []
    state = _state()
    client = _client(tmp_path, calls, state)

    r = client.patch("/api/library/books/b1", json={"tags": ["a", "b"]})
    assert r.status_code == 200
    assert _tag_names(r.json()["tags"]) == ["a", "b"]

    patches = _patch_calls(calls)
    assert len(patches) == 1
    assert patches[0][1] == "/api/v1/books/b1/metadata"
    assert patches[0][2] == {"tags": ["a", "b"], "tagsLock": True}
    assert KEY not in r.text


def test_series_tags_round_trip(tmp_path):
    """Series PATCH updates series tags via the series metadata endpoint."""
    calls: list = []
    state = _state()
    client = _client(tmp_path, calls, state)

    r = client.patch("/api/library/series/s1", json={"tags": ["a", "b"]})
    assert r.status_code == 200
    assert _tag_names(r.json()["tags"]) == ["a", "b"]

    patches = _patch_calls(calls)
    assert len(patches) == 1
    assert patches[0][1] == "/api/v1/series/s1/metadata"
    assert patches[0][2] == {"tags": ["a", "b"], "tagsLock": True}


def test_rating_unsupported(tmp_path):
    """Rating is unsupported except null, which is a no-op without metadata PATCH."""
    calls: list = []
    state = _state()
    client = _client(tmp_path, calls, state)

    r = client.patch("/api/library/books/b1", json={"rating": 3})
    assert r.status_code == 422
    assert r.json()["code"] == "unsupported_field"
    assert r.json()["field"] == "rating"
    assert _patch_calls(calls) == []
    assert KEY not in r.text

    r = client.patch("/api/library/books/b1", json={"rating": None})
    assert r.status_code == 200
    assert _patch_calls(calls) == []


def test_favorite_unsupported(tmp_path):
    """Favorite true and false are unsupported before any upstream call."""
    calls: list = []
    state = _state()
    client = _client(tmp_path, calls, state)

    r = client.patch("/api/library/books/b1", json={"favorite": True})
    assert r.status_code == 422
    assert r.json()["code"] == "unsupported_field"
    assert r.json()["field"] == "favorite"
    assert calls == []

    r = client.patch("/api/library/series/s1", json={"favorite": False})
    assert r.status_code == 422
    assert r.json()["code"] == "unsupported_field"
    assert r.json()["field"] == "favorite"
    assert calls == []


def test_mixed_body_unsupported(tmp_path):
    """A mixed body containing rating is rejected before any upstream call."""
    calls: list = []
    state = _state()
    client = _client(tmp_path, calls, state)

    r = client.patch("/api/library/books/b1", json={"rating": 3, "tags": ["a"]})
    assert r.status_code == 422
    assert r.json()["code"] == "unsupported_field"
    assert r.json()["field"] == "rating"
    assert calls == []


def test_unknown_id_not_found(tmp_path):
    """Unknown book or series ids return 404 without any metadata PATCH."""
    calls: list = []
    state = _state()
    client = _client(tmp_path, calls, state)

    r = client.patch("/api/library/books/missing", json={"tags": ["a"]})
    assert r.status_code == 404
    assert r.json()["code"] == "not_found"
    assert _patch_calls(calls) == []

    r = client.patch("/api/library/series/missing", json={"tags": ["a"]})
    assert r.status_code == 404
    assert r.json()["code"] == "not_found"
    assert _patch_calls(calls) == []


def test_invalid_tag(tmp_path):
    """Empty and over-long tags are rejected before any upstream call."""
    calls: list = []
    state = _state()
    client = _client(tmp_path, calls, state)

    r = client.patch("/api/library/books/b1", json={"tags": [""]})
    assert r.status_code == 422
    assert r.json()["code"] == "invalid_tag"
    assert r.json()["field"] == "tags"
    assert calls == []

    r = client.patch("/api/library/books/b1", json={"tags": ["x" * 65]})
    assert r.status_code == 422
    assert r.json()["code"] == "invalid_tag"
    assert r.json()["field"] == "tags"
    assert calls == []


def test_metadata_patch_upstream_500(tmp_path):
    """A 500 from the Komga metadata PATCH becomes 502 upstream_error."""
    calls: list = []
    state = _state()
    client = _client(tmp_path, calls, state, patch_error=True)

    r = client.patch("/api/library/books/b1", json={"tags": ["a"]})
    assert r.status_code == 502
    assert r.json()["code"] == "upstream_error"
    assert len(_patch_calls(calls)) == 1
    assert KEY not in r.text


def test_bad_komga_id_not_found(tmp_path):
    """A Komga id that is not alphanumeric answers 404 before any upstream call."""
    calls: list = []
    state = _state()
    client = _client(tmp_path, calls, state)

    for bad in ("a.b", "a_b", "x" * 65):
        for path in ("books", "series"):
            r = client.patch(f"/api/library/{path}/{bad}", json={"tags": ["a"]})
            assert r.status_code == 404
            assert r.json()["code"] == "not_found"
            r = client.get(f"/api/library/{path}/{bad}")
            assert r.status_code == 404
            assert r.json()["code"] == "not_found"
    assert calls == []
