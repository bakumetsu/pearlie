"""Tests for the real /api/rules router."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from app.config import Settings
from app.db import init_db
from app.filters.baselist import BASE_LIST
from app.main import create_app


def _client(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "p.db"
    init_db(db_path)
    settings = Settings(
        mode="real",
        real="rules",
        db_path=db_path,
        static_dir=tmp_path / "nostatic",
        worker_enabled=False,
        _env_file=None,  # pyright: ignore[reportCallIssue]
    )
    return TestClient(create_app(settings))


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    """Real-mode client with an empty rules store."""
    return _client(tmp_path)


def _put(client: TestClient, version: int, **lists: object) -> Response:
    return client.put(
        "/api/rules",
        json={
            "version": version,
            "reject": [],
            "warn": [],
            "require": [],
            "mapping": [],
            **lists,
        },
    )


def test_get_default(client: TestClient) -> None:
    """Default rules return version 1 with empty lists and canonical base_list."""
    r = client.get("/api/rules")
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == 1
    assert body["reject"] == []
    assert body["warn"] == []
    assert body["require"] == []
    assert body["mapping"] == []
    assert body["base_list"]["read_only"] is True
    assert body["base_list"]["tags"] == sorted(BASE_LIST)
    assert len(body["base_list"]["tags"]) > 0


def test_put_roundtrip(client: TestClient) -> None:
    """PUT persists and GET echoes the same state."""
    r = _put(
        client,
        1,
        reject=["bad"],
        warn=["w"],
        require=["r"],
        mapping=[{"pattern": "artist:*", "to": "stash_tag"}],
    )
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == 2
    assert body["reject"] == ["bad"]
    assert body["warn"] == ["w"]
    assert body["require"] == ["r"]
    assert body["mapping"] == [{"pattern": "artist:*", "to": "stash_tag"}]
    assert client.get("/api/rules").json() == body


def test_put_stale_version(client: TestClient) -> None:
    """Reusing an old version returns 409 stale_version."""
    _put(client, 1, reject=["a"])
    r = _put(client, 1, reject=["b"])
    assert r.status_code == 409
    assert r.json()["code"] == "stale_version"
    body = client.get("/api/rules").json()
    assert body["version"] == 2
    assert body["reject"] == ["a"]


def test_two_puts_same_version_second_conflicts(client: TestClient) -> None:
    """Second PUT with the same version is rejected; first content is kept."""
    r1 = _put(client, 1, reject=["first"])
    assert r1.status_code == 200
    r2 = _put(client, 1, reject=["second"])
    assert r2.status_code == 409
    assert client.get("/api/rules").json()["reject"] == ["first"]


def test_put_ignores_base_list(client: TestClient) -> None:
    """base_list sent in PUT body is ignored; server keeps canonical tags."""
    body = client.get("/api/rules").json()
    body["reject"] = ["new_reject"]
    body["base_list"]["tags"].append("zzz_not_real")
    r = client.put("/api/rules", json=body)
    assert r.status_code == 200
    after = client.get("/api/rules").json()
    assert after["base_list"]["tags"] == sorted(BASE_LIST)
    assert "zzz_not_real" not in after["base_list"]["tags"]


def test_put_invalid(client: TestClient) -> None:
    """Invalid entries produce 422 with appropriate code and field."""
    long_entry = "a" * 65
    r = _put(client, 1, reject=[long_entry])
    assert r.status_code == 422
    assert r.json()["code"] == "invalid"
    assert r.json()["field"] == "reject"

    r = _put(client, 1, warn=[""])
    assert r.status_code == 422

    r = client.put(
        "/api/rules",
        json={
            "version": 1,
            "reject": [],
            "warn": [],
            "require": [],
            "mapping": [{"pattern": "", "to": "stash_tag"}],
        },
    )
    assert r.status_code == 422
    assert r.json()["field"] == "mapping"

    assert client.get("/api/rules").json()["version"] == 1


def test_post_test_allow_and_layers(client: TestClient) -> None:
    """POST /test returns the correct decision per evaluation layer."""
    _put(client, 1, reject=["bad"], warn=["w"], require=["r"])

    r = client.post("/api/rules/test", json={"tags": ["r"]})
    assert r.json()["decision"] == "allow"

    r = client.post("/api/rules/test", json={"tags": ["r", "w"]})
    assert r.json()["decision"] == "warn"
    assert r.json()["layer"] == "warn"
    assert r.json()["rule"] == "w"

    r = client.post("/api/rules/test", json={"tags": ["r", "bad", "w"]})
    assert r.json()["decision"] == "reject"
    assert r.json()["layer"] == "reject"
    assert r.json()["rule"] == "bad"
    assert r.json()["tag"] == "bad"

    r = client.post("/api/rules/test", json={"tags": ["x"]})
    assert r.json()["decision"] == "require_missing"
    assert r.json()["layer"] == "require"
    assert r.json()["rule"] == "r"


def test_post_test_base_list_and_alias(client: TestClient) -> None:
    """base_list tags and their aliases trigger layer 'base'."""
    base_tag, alias = next((t, a[0]) for t, a in BASE_LIST.items() if a)

    r = client.post("/api/rules/test", json={"tags": [base_tag]})
    assert r.json()["decision"] == "reject"
    assert r.json()["layer"] == "base"
    assert r.json()["rule"] == base_tag

    r = client.post("/api/rules/test", json={"tags": [alias]})
    assert r.json()["layer"] == "base"
    assert r.json()["alias"] == alias


def test_post_test_normalization_and_scope(client: TestClient) -> None:
    """Tags are normalised (case, spaces) and matched per scope."""
    _put(client, 1, reject=["Blue Sky", "artist:foo bar"])

    r = client.post("/api/rules/test", json={"tags": ["blue-sky"]})
    assert r.json()["decision"] == "reject"

    r = client.post("/api/rules/test", json={"tags": ["artist:foo_bar"]})
    assert r.json()["decision"] == "reject"

    r = client.post("/api/rules/test", json={"tags": ["general:foo_bar"]})
    assert r.json()["decision"] == "allow"


def test_base_list_not_removable(client: TestClient) -> None:
    """PUT with empty lists does not clear the base_list."""
    before = client.get("/api/rules").json()["base_list"]
    _put(client, 1)
    after = client.get("/api/rules").json()["base_list"]
    assert after == before
    assert len(after["tags"]) > 0
