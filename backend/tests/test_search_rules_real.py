"""Tests for rules applied to real search results."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.db import init_db
from app.filters.baselist import BASE_LIST
from app.main import create_app
from app.sources.base import Post, SearchPage


class FakeSource:
    """In-memory source returning fixed posts for any query."""

    def __init__(self, posts: list[Post]) -> None:
        self.posts = posts

    def search(self, tags, page, page_size):
        return SearchPage(posts=self.posts, page=1, total=len(self.posts), pages=1)


def _post(pid: int, tags: dict[str, list[str]]) -> Post:
    return Post(
        source="danbooru",
        post_id=str(pid),
        preview_url="t",
        file_url="f",
        tags=tags,
    )


def _client(tmp_path: Path, posts: list[Post]) -> TestClient:
    db_path = tmp_path / "p.db"
    init_db(db_path)
    app = create_app(
        Settings(
            mode="real",
            real="search,rules",
            db_path=db_path,
            static_dir=tmp_path / "nostatic",
            worker_enabled=False,
            _env_file=None,  # pyright: ignore[reportCallIssue]
        )
    )
    app.state.sources["danbooru"] = FakeSource(posts)
    return TestClient(app)


def _section(r, name: str) -> dict:
    for s in r.json()["sections"]:
        if s["id"] == name:
            return s
    raise KeyError(f"section {name} not found")


def _put_rules(client: TestClient, **lists) -> None:
    client.put(
        "/api/rules",
        json={
            "version": 1,
            "reject": [],
            "warn": [],
            "require": [],
            "mapping": [],
            **lists,
        },
    )


def test_no_rules_all_shown(tmp_path: Path) -> None:
    """With no rules all posts are shown, hidden is 0, no blur."""
    posts = [
        _post(1, {"general": ["a"]}),
        _post(2, {"general": ["b"]}),
        _post(3, {"general": ["c"]}),
    ]
    client = _client(tmp_path, posts)
    r = client.get("/api/search?q=a&sources=danbooru")
    assert r.status_code == 200
    sec = _section(r, "danbooru")
    assert len(sec["items"]) == 3
    assert sec["hidden"] == 0
    for item in sec["items"]:
        assert item["blur"] is None


def test_reject_drops_matching_post(tmp_path: Path) -> None:
    """A reject rule drops the matching post; hidden is 1 and total unchanged."""
    posts = [
        _post(1, {"general": ["good"]}),
        _post(2, {"general": ["bad_tag"]}),
        _post(3, {"general": ["good2"]}),
    ]
    client = _client(tmp_path, posts)
    _put_rules(client, reject=["bad_tag"])
    r = client.get("/api/search?q=bad_tag&sources=danbooru")
    assert r.status_code == 200
    sec = _section(r, "danbooru")
    assert sec["hidden"] == 1
    assert len(sec["items"]) == 2
    assert sec["total"] == 3
    ids = {item["post_id"] for item in sec["items"]}
    assert "2" not in ids


def test_base_list_hides_without_rules(tmp_path: Path) -> None:
    """A post tagged with a base_list tag is hidden even with no rules set."""
    base_tag = sorted(BASE_LIST)[0]
    posts = [
        _post(1, {"general": [base_tag]}),
    ]
    client = _client(tmp_path, posts)
    r = client.get("/api/search?q=test&sources=danbooru")
    assert r.status_code == 200
    sec = _section(r, "danbooru")
    assert sec["hidden"] == 1
    assert len(sec["items"]) == 0


def test_warn_blurs_item(tmp_path: Path) -> None:
    """A warn rule keeps the item but sets blur; other items have no blur."""
    posts = [
        _post(1, {"general": ["spoiler"]}),
        _post(2, {"general": ["clean"]}),
    ]
    client = _client(tmp_path, posts)
    _put_rules(client, warn=["spoiler"])
    r = client.get("/api/search?q=spoiler&sources=danbooru")
    assert r.status_code == 200
    sec = _section(r, "danbooru")
    assert sec["hidden"] == 0
    assert len(sec["items"]) == 2
    by_id = {item["post_id"]: item for item in sec["items"]}
    assert by_id["1"]["blur"] == {"tag": "spoiler"}
    assert by_id["2"]["blur"] is None


def test_require_hides_unmatched(tmp_path: Path) -> None:
    """Posts lacking a required tag are hidden; the matching post is shown."""
    posts = [
        _post(1, {"general": ["wanted"]}),
        _post(2, {"general": ["other"]}),
        _post(3, {"general": ["other2"]}),
    ]
    client = _client(tmp_path, posts)
    _put_rules(client, require=["wanted"])
    r = client.get("/api/search?q=wanted&sources=danbooru")
    assert r.status_code == 200
    sec = _section(r, "danbooru")
    assert sec["hidden"] == 2
    assert len(sec["items"]) == 1
    assert sec["items"][0]["post_id"] == "1"


def test_reject_normalization_space_to_underscore(tmp_path: Path) -> None:
    """Reject rule 'bad tag' (space) hides a post tagged 'bad_tag' (underscore)."""
    posts = [
        _post(1, {"general": ["bad_tag"]}),
    ]
    client = _client(tmp_path, posts)
    _put_rules(client, reject=["bad tag"])
    r = client.get("/api/search?q=bad&sources=danbooru")
    assert r.status_code == 200
    sec = _section(r, "danbooru")
    assert sec["hidden"] == 1
    assert len(sec["items"]) == 0


def test_reject_beats_warn(tmp_path: Path) -> None:
    """A post matching both reject and warn is hidden (reject wins)."""
    posts = [
        _post(1, {"general": ["bad", "spoiler"]}),
    ]
    client = _client(tmp_path, posts)
    _put_rules(client, reject=["bad"], warn=["spoiler"])
    r = client.get("/api/search?q=bad&sources=danbooru")
    assert r.status_code == 200
    sec = _section(r, "danbooru")
    assert sec["hidden"] == 1
    assert len(sec["items"]) == 0


def test_multi_source_unconfigured_error(tmp_path: Path) -> None:
    """With multiple sources, unconfigured ones get not_configured; danbooru still filters."""
    posts = [
        _post(1, {"general": ["bad_tag"]}),
        _post(2, {"general": ["clean"]}),
    ]
    client = _client(tmp_path, posts)
    _put_rules(client, reject=["bad_tag"])
    r = client.get("/api/search?q=bad&sources=danbooru,gelbooru")
    assert r.status_code == 200
    danbooru = _section(r, "danbooru")
    assert danbooru["hidden"] == 1
    assert len(danbooru["items"]) == 1
    gelbooru = _section(r, "gelbooru")
    assert gelbooru["error"]["code"] == "not_configured"
    assert gelbooru["hidden"] == 0
