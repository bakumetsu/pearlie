"""Tests for require and warn rules at save time."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from test_jobs_real import _make_post, make_client  # noqa: F401

from app.db import connect
from app.filters.baselist import BASE_LIST
from app.sources.base import Post


def _client(
    tmp_path: Path,
    tags: dict[str, list[str]],
    rules: list[tuple[str, str]],
) -> TestClient:
    client, sources, db_path = make_client(tmp_path)
    sources["danbooru"].posts["1"] = Post(
        source="danbooru",
        post_id="1",
        md5="1" * 32,
        file_url="https://x/y.jpg",
        preview_url="https://x/t.jpg",
        tags=tags,
    )
    if rules:
        conn = connect(db_path)
        for list_name, entry in rules:
            if ":" in entry:
                scope, pattern = entry.split(":", 1)
            else:
                scope, pattern = "", entry
            conn.execute(
                "INSERT INTO rules (list, pattern, scope) VALUES (?, ?, ?)",
                (list_name, pattern, scope),
            )
        conn.commit()
        conn.close()
    return client


def test_require_blocks_when_missing(tmp_path: Path) -> None:
    """Require rule blocks a post that lacks the required tag."""
    client = _client(tmp_path, {"general": ["a_b"]}, rules=[("require", "wanted")])
    resp = client.post("/api/save", json={"source": "danbooru", "post_id": "1"})
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "rejected_by_rule"
    assert body["layer"] == "require"
    assert body["rule"] == "wanted"
    assert client.get("/api/jobs").json()["items"] == []


def test_require_allows_when_present(tmp_path: Path) -> None:
    """Require rule allows a post that has the required tag."""
    client = _client(tmp_path, {"general": ["wanted"]}, rules=[("require", "wanted")])
    resp = client.post("/api/save", json={"source": "danbooru", "post_id": "1"})
    assert resp.status_code == 202


def test_warn_saves_normally(tmp_path: Path) -> None:
    """Warn rule does not block the save."""
    client = _client(tmp_path, {"general": ["spoiler"]}, rules=[("warn", "spoiler")])
    resp = client.post("/api/save", json={"source": "danbooru", "post_id": "1"})
    assert resp.status_code == 202


def test_reject_beats_require(tmp_path: Path) -> None:
    """Reject layer takes priority over require."""
    client = _client(
        tmp_path,
        {"general": ["my_reject"]},
        rules=[("require", "wanted"), ("reject", "my_reject")],
    )
    resp = client.post("/api/save", json={"source": "danbooru", "post_id": "1"})
    assert resp.status_code == 422
    assert resp.json()["layer"] == "reject"


def test_base_beats_everything(tmp_path: Path) -> None:
    """Base list beats all other rule layers."""
    base_tag = next(iter(BASE_LIST))
    client = _client(
        tmp_path,
        {"general": [base_tag, "spoiler"]},
        rules=[("warn", "spoiler")],
    )
    resp = client.post("/api/save", json={"source": "danbooru", "post_id": "1"})
    assert resp.status_code == 422
    assert resp.json()["layer"] == "base"
