"""Tabs API tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def real_client(tmp_path):
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
def any_client(request, client, tmp_path):
    if request.param == "fixture":
        return client
    return real_client(tmp_path)


def _valid_tab():
    return {
        "id": "a",
        "q": "cat",
        "src": "web",
        "sites": ["danbooru"],
        "order": "score",
        "rating": ["g", "s"],
    }


def test_get_defaults(any_client):
    r = any_client.get("/api/tabs")
    assert r.status_code == 200
    assert r.json() == {"tabs": [], "active": None, "rev": 0}


def test_put_roundtrip(any_client):
    tab = _valid_tab()
    r = any_client.put("/api/tabs", json={"tabs": [tab], "active": "a", "rev": 0})
    assert r.status_code == 200
    body = r.json()
    assert body["rev"] == 1
    assert body["active"] == "a"
    assert body["tabs"] == [tab]
    r2 = any_client.get("/api/tabs")
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["rev"] == 1
    assert body2["active"] == "a"
    assert body2["tabs"] == [tab]


def test_stale_rev(any_client):
    tab = _valid_tab()
    any_client.put("/api/tabs", json={"tabs": [tab], "active": "a", "rev": 0})
    r = any_client.put("/api/tabs", json={"tabs": [tab], "active": "a", "rev": 0})
    assert r.status_code == 409
    body = r.json()
    assert body["code"] == "conflict"
    assert body["rev"] == 1
    r2 = any_client.get("/api/tabs")
    assert r2.json() == {"tabs": [tab], "active": "a", "rev": 1}


def test_close_last_tab(any_client):
    tab = _valid_tab()
    any_client.put("/api/tabs", json={"tabs": [tab], "active": "a", "rev": 0})
    r = any_client.put("/api/tabs", json={"tabs": [], "active": None, "rev": 1})
    assert r.status_code == 200
    body = r.json()
    assert body["tabs"] == []
    assert body["active"] is None


@pytest.mark.parametrize(
    "mutate",
    [
        lambda t: t | {"q": "a" * 501},
        lambda t: t | {"sites": ["foo"]},
        lambda t: t | {"order": "random"},
        lambda t: t | {"rating": ["x"]},
        lambda t: t | {"src": "nosrc"},
    ],
    ids=["q_501", "unknown_site", "bad_order", "bad_rating", "unknown_src"],
)
def test_put_invalid_tab_field(any_client, mutate):
    tabs = [mutate(_valid_tab())]
    r = any_client.put("/api/tabs", json={"tabs": tabs, "active": "a", "rev": 0})
    assert r.status_code == 422


def test_put_too_many_tabs(any_client):
    tabs = [{**_valid_tab(), "id": f"t{i}"} for i in range(9)]
    r = any_client.put("/api/tabs", json={"tabs": tabs, "active": "t0", "rev": 0})
    assert r.status_code == 422


def test_put_duplicate_ids(any_client):
    tabs = [_valid_tab(), _valid_tab()]
    r = any_client.put("/api/tabs", json={"tabs": tabs, "active": "a", "rev": 0})
    assert r.status_code == 422


def test_put_active_not_in_tabs(any_client):
    r = any_client.put("/api/tabs", json={"tabs": [_valid_tab()], "active": "b", "rev": 0})
    assert r.status_code == 422


def test_failed_put_leaves_rev(any_client):
    tab = _valid_tab()
    any_client.put("/api/tabs", json={"tabs": [tab], "active": "a", "rev": 0})
    r = any_client.put("/api/tabs", json={"tabs": [tab], "active": "a", "rev": 0})
    assert r.status_code == 409
    r2 = any_client.get("/api/tabs")
    assert r2.json()["rev"] == 1


def test_real_persists_across_clients(tmp_path):
    c1 = real_client(tmp_path)
    tab = _valid_tab()
    c1.put("/api/tabs", json={"tabs": [tab], "active": "a", "rev": 0})
    c2 = real_client(tmp_path)
    r = c2.get("/api/tabs")
    assert r.status_code == 200
    body = r.json()
    assert body["rev"] == 1
    assert body["active"] == "a"
    assert body["tabs"] == [tab]
