"""Tests for the tag filter / reject rules."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_jobs_real import _make_post, make_client  # noqa: F401

from app.db import connect
from app.filters.baselist import BASE_LIST, BaseListError, load_base_list
from app.filters.rules import check
from app.sources.base import Post

_tag = next(iter(BASE_LIST))
_base_tag, _alias = next(((t, a[0]) for t, a in BASE_LIST.items() if a))


def _client_with_tags(
    tmp_path: Path, tags: dict[str, list[str]], reject: tuple[str, ...] = (), name: str = "c1"
) -> TestClient:
    client, sources, db_path = make_client(tmp_path / name)
    sources["danbooru"].posts["1"] = Post(
        source="danbooru",
        post_id="1",
        md5="1" * 32,
        file_url="https://x/y.jpg",
        preview_url="https://x/t.jpg",
        tags=tags,
    )
    if reject:
        conn = connect(db_path)
        for entry in reject:
            if ":" in entry:
                scope, pattern = entry.split(":", 1)
            else:
                scope, pattern = "", entry
            conn.execute(
                "INSERT INTO rules (list, pattern, scope) VALUES ('reject', ?, ?)",
                (pattern, scope),
            )
        conn.commit()
        conn.close()
    return client


def test_base_tag_blocks(tmp_path: Path) -> None:
    client = _client_with_tags(tmp_path, {"general": [_tag]})
    resp = client.post("/api/save", json={"source": "danbooru", "post_id": "1"})
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "rejected_by_rule"
    assert body["layer"] == "base"
    assert body["rule"] == _tag
    assert body["tag"] == _tag
    assert body["alias"] is None
    jobs = client.get("/api/jobs").json()["items"]
    assert jobs == []


def test_alias_blocks(tmp_path: Path) -> None:
    client = _client_with_tags(tmp_path, {"general": [_alias]})
    resp = client.post("/api/save", json={"source": "danbooru", "post_id": "1"})
    assert resp.status_code == 422
    body = resp.json()
    assert body["layer"] == "base"
    assert body["rule"] == _base_tag
    assert body["alias"] == _alias
    assert body["tag"] == _alias


def test_reject_tag_blocks(tmp_path: Path) -> None:
    client = _client_with_tags(tmp_path, {"general": ["my_reject"]}, reject=("my_reject",))
    resp = client.post("/api/save", json={"source": "danbooru", "post_id": "1"})
    assert resp.status_code == 422
    body = resp.json()
    assert body["layer"] == "reject"
    assert body["rule"] == "my_reject"
    assert body["tag"] == "my_reject"


def test_normalization(tmp_path: Path) -> None:
    client = _client_with_tags(tmp_path, {"general": ["My Reject-Tag"]}, reject=("my_reject_tag",))
    resp = client.post("/api/save", json={"source": "danbooru", "post_id": "1"})
    assert resp.status_code == 422
    assert resp.json()["layer"] == "reject"

    client2 = _client_with_tags(tmp_path, {"general": [_tag.upper().replace("_", " ")]}, name="c2")
    resp2 = client2.post("/api/save", json={"source": "danbooru", "post_id": "1"})
    assert resp2.status_code == 422
    assert resp2.json()["layer"] == "base"


def test_base_before_reject(tmp_path: Path) -> None:
    tags = {"general": [_tag, "some_reject"]}
    client = _client_with_tags(tmp_path, tags, reject=("some_reject",))
    resp = client.post("/api/save", json={"source": "danbooru", "post_id": "1"})
    assert resp.status_code == 422
    assert resp.json()["layer"] == "base"


def test_first_match_in_base() -> None:
    keys = list(BASE_LIST.keys())
    assert len(keys) >= 2
    tag_a, tag_b = keys[0], keys[1]
    result = check({"general": [tag_a, tag_b]}, ())
    assert result is not None
    assert result.rule == tag_a


def test_scoped_tag_blocks(tmp_path: Path) -> None:
    client = _client_with_tags(tmp_path, {"female": [_tag]})
    resp = client.post("/api/save", json={"source": "danbooru", "post_id": "1"})
    assert resp.status_code == 422
    assert resp.json()["layer"] == "base"

    client2 = _client_with_tags(tmp_path, {"artist": ["bad"]}, reject=("artist:bad",), name="c2")
    resp2 = client2.post("/api/save", json={"source": "danbooru", "post_id": "1"})
    assert resp2.status_code == 422
    assert resp2.json()["layer"] == "reject"

    client3 = _client_with_tags(tmp_path, {"general": ["bad"]}, reject=("artist:bad",), name="c3")
    resp3 = client3.post("/api/save", json={"source": "danbooru", "post_id": "1"})
    assert resp3.status_code == 202


def test_base_list_immutable_via_api(tmp_path: Path) -> None:
    base_copy = dict(BASE_LIST)
    client, _, _ = make_client(tmp_path)
    resp = client.put("/api/rules", json={"version": 1, "reject": [], "base_list": {"tags": []}})
    assert resp.status_code in (404, 405)
    assert BASE_LIST == base_copy


def test_unblocked_post_saves(tmp_path: Path) -> None:
    client = _client_with_tags(tmp_path, {"general": ["a_b"]})
    resp = client.post("/api/save", json={"source": "danbooru", "post_id": "1"})
    assert resp.status_code == 202


def test_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(BaseListError):
        load_base_list(tmp_path / "missing.txt")

    p = tmp_path / "comments_only.txt"
    p.write_text("# just a comment\n# another\n")
    with pytest.raises(BaseListError):
        load_base_list(p)


def test_secrecy_in_logs(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    post_tags = {"general": [_tag, "zzz_unrelated"]}
    client = _client_with_tags(tmp_path, post_tags)
    with caplog.at_level("INFO", logger="pearlie"):
        resp = client.post("/api/save", json={"source": "danbooru", "post_id": "1"})
    assert resp.status_code == 422
    assert _tag in caplog.text
    assert "zzz_unrelated" not in caplog.text
