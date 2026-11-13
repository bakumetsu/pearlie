"""Tests for the Rule34 and Gelbooru dapi adapters (mocked, no network)."""
from __future__ import annotations

import logging
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import init_db
from app.jobs.store import JobStore
from app.main import create_app
from app.sources.base import SourceError
from app.sources.dapi import Gelbooru, Rule34
from app.sources.throttle import Throttle


def r34_post(i: int, rating: str = "explicit", tags: str = "a b") -> dict:
    return {
        "id": i, "hash": f"{i:032x}", "file_url": f"https://img.rule34.xxx/images/1/{i}.jpg",
        "preview_url": f"https://wimg.rule34.xxx/thumbnails/1/t_{i}.jpg",
        "sample_url": f"https://img.rule34.xxx/samples/1/s_{i}.jpg",
        "width": 100, "height": 200, "rating": rating, "tags": tags,
    }


def make(cls, handler, **kw):
    return cls(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        throttle=Throttle(0.0),
        **kw,
    )


def test_search_parse_and_paging():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen.update(req.url.params)
        assert req.url.host == "api.rule34.xxx"
        return httpx.Response(200, json=[r34_post(1), r34_post(2)])

    res = make(Rule34, handler).search(["cat", "-dog"], page=3, page_size=2)
    assert seen["page"] == "dapi" and seen["json"] == "1"
    assert seen["pid"] == "2" and seen["limit"] == "2"
    assert seen["tags"] == "cat -dog"
    p = res.posts[0]
    assert p.source == "rule34" and p.post_id == "1" and p.md5 == f"{1:032x}"
    assert (p.file_url or "").endswith("/1.jpg") and p.rating == "explicit"
    assert p.tags == {"general": ["a", "b"]}
    assert res.next_page == 4


def test_empty_body_and_short_page():
    res = make(Rule34, lambda r: httpx.Response(200, content=b"")).search(["x"])
    assert res.posts == [] and res.next_page is None
    res = make(Rule34, lambda r: httpx.Response(200, json=[r34_post(1)])).search(["x"])
    assert len(res.posts) == 1 and res.next_page is None


def test_rating_filter_local():
    data = [r34_post(1, "explicit"), r34_post(2, "safe"), r34_post(3, "questionable")]
    sent = {}

    def handler(req: httpx.Request) -> httpx.Response:
        sent.update(req.url.params)
        return httpx.Response(200, json=data)

    d = make(Rule34, handler)
    assert [p.post_id for p in d.search(["rating:safe"]).posts] == ["2"]
    assert sent["tags"] == ""
    assert [p.post_id for p in d.search(["-rating:explicit", "cat"]).posts] == ["2", "3"]
    assert sent["tags"] == "cat"


def test_auth_params_sent_and_not_logged(caplog):
    sent = {}

    def handler(req: httpx.Request) -> httpx.Response:
        sent.update(req.url.params)
        return httpx.Response(200, json=[r34_post(1)])

    creds = {"user_id": "42", "api_key": "SECRETKEY"}
    caplog.set_level(logging.DEBUG)
    make(Rule34, handler, credentials=lambda: creds).search(["x"])
    assert sent["user_id"] == "42" and sent["api_key"] == "SECRETKEY"
    assert "SECRETKEY" not in caplog.text

    sent.clear()
    make(Rule34, handler, credentials=lambda: {"user_id": "42"}).search(["x"])
    assert "api_key" not in sent and "user_id" not in sent

    def boom(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("fail", request=req)

    with pytest.raises(SourceError) as e:
        make(Rule34, boom, credentials=lambda: creds).search(["x"])
    assert "SECRETKEY" not in e.value.message


def test_errors():
    with pytest.raises(SourceError) as e:
        make(Rule34, lambda r: httpx.Response(429)).search(["x"])
    assert e.value.code == "rate_limited"
    with pytest.raises(SourceError):
        make(Rule34, lambda r: httpx.Response(200, content=b"<html>")).search(["x"])


def test_get_post():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.params["id"] == "7"
        return httpx.Response(200, json=[r34_post(7)])

    d = make(Rule34, handler)
    assert d.get_post("7").post_id == "7"
    with pytest.raises(SourceError) as e:
        d.get_post("abc")
    assert e.value.status == 404
    with pytest.raises(SourceError) as e:
        make(Rule34, lambda r: httpx.Response(200, content=b"")).get_post("7")
    assert e.value.status == 404


def test_gelbooru_variant():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.host == "gelbooru.com"
        return httpx.Response(200, json={
            "@attributes": {"limit": 100, "offset": 0, "count": 1},
            "post": [{
                "id": 5, "md5": "ab" * 16, "file_url": "https://img3.gelbooru.com/images/x.png",
                "preview_url": "https://img3.gelbooru.com/thumbnails/t.jpg",
                "width": 10, "height": 20, "rating": "general", "tags": "t1 t2",
            }],
        })

    g = make(Gelbooru, handler)
    res = g.search(["t1"])
    assert res.posts[0].source == "gelbooru" and res.posts[0].md5 == "ab" * 16
    assert res.posts[0].rating == "general"
    assert "img3.gelbooru.com" in g.file_hosts
    empty = make(Gelbooru, lambda r: httpx.Response(200, json={"@attributes": {"count": 0}}))
    assert empty.search(["t1"]).posts == []


def test_registered_and_save_queues_rule34_post(tmp_path: Path) -> None:
    """The app registers both sources; saving a Rule34 post queues a job for the stash."""
    db_path = tmp_path / "p.db"
    init_db(db_path)
    settings = Settings(
        mode="real", real="jobs", db_path=db_path, static_dir=tmp_path / "nostatic",
        stash_url="http://stash.invalid", worker_enabled=False,
        _env_file=None,  # pyright: ignore[reportCallIssue]
    )
    app = create_app(settings)
    assert {"danbooru", "rule34", "gelbooru"} <= set(app.state.sources)
    assert "img.rule34.xxx" in app.state.sources["rule34"].file_hosts
    app.state.sources["rule34"] = make(
        Rule34, lambda r: httpx.Response(200, json=[r34_post(9)])
    )
    resp = TestClient(app).post("/api/save", json={"source": "rule34", "post_id": "9"})
    assert resp.status_code == 202
    job = JobStore(db_path).list(None)[0]
    assert job.source == "rule34" and job.target == "stash"
