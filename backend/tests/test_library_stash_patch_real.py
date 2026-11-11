"""Tests for real-mode Stash PATCH."""

from __future__ import annotations

import json

import httpx
from test_library_stash_real import KEY, image_dto, make_client, scene_dto


def _make_patch_handler(calls: list, state: dict, update_error: bool = False):
    """Return a MockTransport handler that records calls and answers by GraphQL op text."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body)
        query = body.get("query", "")
        variables = body.get("variables", {})

        if "findImage(" in query:
            return httpx.Response(200, json={"data": {"findImage": state["image"]}})

        if "findScene(" in query:
            return httpx.Response(200, json={"data": {"findScene": state["scene"]}})

        if "findTags" in query:
            name = variables.get("v", "")
            lower_name = name.casefold()
            matches = [t for t in state["existing_tags"] if t["name"].casefold() == lower_name]
            for t in matches:
                state["tag_table"][t["id"]] = t["name"]
            return httpx.Response(200, json={"data": {"findTags": {"tags": matches}}})

        if "tagCreate" in query:
            name = variables.get("n", "")
            state["tag_table"]["99"] = name
            return httpx.Response(200, json={"data": {"tagCreate": {"id": "99"}}})

        if "imageUpdate(" in query or "sceneUpdate(" in query:
            if update_error:
                return httpx.Response(500, text="upstream failure")
            inp = variables.get("i", {})
            target = state["image"] if "imageUpdate(" in query else state["scene"]
            if "rating100" in inp:
                target["rating100"] = inp["rating100"]
            if "tag_ids" in inp:
                target["tags"] = [
                    {"name": state["tag_table"][tid]}
                    for tid in inp["tag_ids"]
                    if tid in state["tag_table"]
                ]
            key = "imageUpdate" if "imageUpdate(" in query else "sceneUpdate"
            return httpx.Response(200, json={"data": {key: {"id": target["id"]}}})

        return httpx.Response(200, json={"data": {}})

    return handler


def _state(**over):
    base = {
        "image": image_dto("1"),
        "scene": scene_dto("2"),
        "existing_tags": [{"id": "1", "name": "Foo"}],
        "tag_table": {"1": "Foo"},
    }
    base.update(over)
    return base


def _client(tmp_path, calls, state, update_error=False):
    return make_client(tmp_path, _make_patch_handler(calls, state, update_error))


def _updates(calls, kind):
    """Return list of update call bodies of the given kind ('imageUpdate(' or 'sceneUpdate(')."""
    return [c for c in calls if kind in c.get("query", "")]


# ---------------------------------------------------------------------------
# 1 – image rating
# ---------------------------------------------------------------------------


def test_image_rating(tmp_path):
    """PATCH image rating 4 → 200, rating == 4, one imageUpdate with rating100=80."""
    calls: list = []
    state = _state()
    client = _client(tmp_path, calls, state)

    r = client.patch("/api/library/images/1", json={"rating": 4})
    assert r.status_code == 200
    assert r.json()["rating"] == 4

    updates = _updates(calls, "imageUpdate(")
    assert len(updates) == 1
    assert updates[0]["variables"]["i"] == {"id": "1", "rating100": 80}
    # KEY never in response
    assert KEY not in r.text


# ---------------------------------------------------------------------------
# 2 – scene rating
# ---------------------------------------------------------------------------


def test_scene_rating(tmp_path):
    """PATCH scene rating 5 → 200, one sceneUpdate with rating100=100."""
    calls: list = []
    state = _state()
    client = _client(tmp_path, calls, state)

    r = client.patch("/api/library/videos/2", json={"rating": 5})
    assert r.status_code == 200
    assert r.json()["rating"] == 5

    updates = _updates(calls, "sceneUpdate(")
    assert len(updates) == 1
    assert updates[0]["variables"]["i"]["rating100"] == 100


# ---------------------------------------------------------------------------
# 3 – rating null clears
# ---------------------------------------------------------------------------


def test_rating_null_clears(tmp_path):
    """PATCH {"rating": None} → rating100 None sent, response rating None."""
    calls: list = []
    state = _state()
    client = _client(tmp_path, calls, state)

    r = client.patch("/api/library/images/1", json={"rating": None})
    assert r.status_code == 200
    assert r.json()["rating"] is None

    updates = _updates(calls, "imageUpdate(")
    assert len(updates) == 1
    assert updates[0]["variables"]["i"]["rating100"] is None


# ---------------------------------------------------------------------------
# 4 – tags round-trip on image
# ---------------------------------------------------------------------------


def test_tags_round_trip_image(tmp_path):
    """Existing 'Foo' reused case-insensitively, 'new' created; one imageUpdate with tag_ids."""
    calls: list = []
    state = _state()
    client = _client(tmp_path, calls, state)

    r = client.patch("/api/library/images/1", json={"tags": ["foo", "new"]})
    assert r.status_code == 200

    # One imageUpdate carrying tag_ids
    updates = _updates(calls, "imageUpdate(")
    assert len(updates) == 1
    tag_ids = updates[0]["variables"]["i"]["tag_ids"]
    assert "1" in tag_ids  # existing "Foo" id
    assert "99" in tag_ids  # created "new" id

    # tagCreate was called for "new"
    creates = [c for c in calls if "tagCreate" in c.get("query", "")]
    assert len(creates) == 1

    # Response tag names match
    resp_tags = [t if isinstance(t, str) else t.get("name") for t in r.json()["tags"]]
    assert set(resp_tags) == {"Foo", "new"}


# ---------------------------------------------------------------------------
# 5 – rating and tags together → one update
# ---------------------------------------------------------------------------


def test_rating_and_tags_one_update(tmp_path):
    """PATCH with both rating and tags → single update call with rating100 and tag_ids."""
    calls: list = []
    state = _state()
    client = _client(tmp_path, calls, state)

    r = client.patch("/api/library/images/1", json={"rating": 3, "tags": ["foo"]})
    assert r.status_code == 200

    updates = _updates(calls, "imageUpdate(")
    assert len(updates) == 1
    inp = updates[0]["variables"]["i"]
    assert "rating100" in inp
    assert inp["rating100"] == 60
    assert "tag_ids" in inp


# ---------------------------------------------------------------------------
# 6 – favorite unsupported
# ---------------------------------------------------------------------------


def test_favorite_true_unsupported(tmp_path):
    """favorite true → 422 unsupported_field, field favorite, zero upstream calls."""
    calls: list = []
    state = _state()
    client = _client(tmp_path, calls, state)

    r = client.patch("/api/library/images/1", json={"favorite": True})
    assert r.status_code == 422
    assert r.json()["code"] == "unsupported_field"
    assert r.json()["field"] == "favorite"
    assert calls == []
    assert KEY not in r.text


def test_favorite_false_unsupported(tmp_path):
    """favorite false → 422 unsupported_field, field favorite, zero upstream calls."""
    calls: list = []
    state = _state()
    client = _client(tmp_path, calls, state)

    r = client.patch("/api/library/videos/2", json={"favorite": False})
    assert r.status_code == 422
    assert r.json()["code"] == "unsupported_field"
    assert r.json()["field"] == "favorite"
    assert calls == []


# ---------------------------------------------------------------------------
# 7 – mixed body with unsupported field
# ---------------------------------------------------------------------------


def test_mixed_body_rating_favorite(tmp_path):
    """{"rating":3,"favorite":True} → 422, zero upstream calls."""
    calls: list = []
    state = _state()
    client = _client(tmp_path, calls, state)

    r = client.patch("/api/library/images/1", json={"rating": 3, "favorite": True})
    assert r.status_code == 422
    assert calls == []


# ---------------------------------------------------------------------------
# 8 – unknown / invalid id
# ---------------------------------------------------------------------------


def test_unknown_id_not_found(tmp_path):
    """findImage returns null → 404 not_found."""
    calls: list = []
    state = _state(image=None)
    client = _client(tmp_path, calls, state)

    r = client.patch("/api/library/images/999", json={"rating": 3})
    assert r.status_code == 404
    assert r.json()["code"] == "not_found"


def test_non_numeric_id_no_calls(tmp_path):
    """Non-numeric id 'abc' → 404, zero upstream calls."""
    calls: list = []
    state = _state()
    client = _client(tmp_path, calls, state)

    r = client.patch("/api/library/images/abc", json={"rating": 3})
    assert r.status_code == 404
    assert r.json()["code"] == "not_found"
    assert calls == []


# ---------------------------------------------------------------------------
# 9 – invalid tag
# ---------------------------------------------------------------------------


def test_invalid_tag_empty(tmp_path):
    """Empty tag '' → 422 invalid_tag, zero upstream calls."""
    calls: list = []
    state = _state()
    client = _client(tmp_path, calls, state)

    r = client.patch("/api/library/images/1", json={"tags": [""]})
    assert r.status_code == 422
    assert r.json()["code"] == "invalid_tag"
    assert calls == []


def test_invalid_tag_too_long(tmp_path):
    """65-char tag → 422 invalid_tag, zero upstream calls."""
    calls: list = []
    state = _state()
    client = _client(tmp_path, calls, state)

    r = client.patch("/api/library/images/1", json={"tags": ["x" * 65]})
    assert r.status_code == 422
    assert r.json()["code"] == "invalid_tag"
    assert calls == []


# ---------------------------------------------------------------------------
# 10 – upstream 500 on update
# ---------------------------------------------------------------------------


def test_upstream_500_on_update(tmp_path):
    """Upstream returns 500 on update → 502 upstream_error."""
    calls: list = []
    state = _state()
    client = _client(tmp_path, calls, state, update_error=True)

    r = client.patch("/api/library/images/1", json={"rating": 4})
    assert r.status_code == 502
    assert r.json()["code"] == "upstream_error"
    assert KEY not in r.text


# ---------------------------------------------------------------------------
# 11 – secret leak (covered inline in tests 1, 6, 10)
# ---------------------------------------------------------------------------
