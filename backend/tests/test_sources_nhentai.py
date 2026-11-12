"""Tests for the nhentai adapter and its search wiring (mocked, no network)."""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.sources.base import SourceError
from app.sources.nhentai import CDN_HOST, NHentai, build_query
from app.sources.throttle import Throttle

CREDS = {"cookie": "sessionid=SECRET", "user_agent": "UA/1"}


def gallery(i: int, tags: list[dict] | None = None) -> dict:
    return {
        "id": i,
        "media_id": f"90{i}",
        "title": {"english": f"Eng {i}", "pretty": f"Pretty {i}"},
        "images": {
            "pages": [{"t": "j", "w": 1, "h": 1}, {"t": "p", "w": 1, "h": 1}],
            "cover": {"t": "j", "w": 350, "h": 500},
        },
        "tags": tags
        or [
            {"type": "tag", "name": "big breasts"},
            {"type": "artist", "name": "some artist"},
            {"type": "parody", "name": "original"},
            {"type": "language", "name": "english"},
            {"type": "weird", "name": "x"},
        ],
        "num_pages": 2,
    }


def make(handler, **kw) -> NHentai:
    return NHentai(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        throttle=Throttle(0.0),
        credentials=lambda: CREDS,
        **kw,
    )


def test_build_query() -> None:
    assert build_query(["artist:foo_bar", "big_breasts", "-tag:x", "  "]) == (
        'artist:"foo bar" "big breasts" -tag:"x"'
    )
    assert build_query([]) == ""


def test_search_parse_and_paging() -> None:
    seen: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = req.url
        seen["headers"] = req.headers
        return httpx.Response(
            200, json={"result": [gallery(1), gallery(2)], "num_pages": 4, "per_page": 25}
        )

    page = make(handler).search(["artist:foo_bar"], page=2)
    assert seen["url"].path == "/api/galleries/search"
    assert seen["url"].params["query"] == 'artist:"foo bar"'
    assert seen["url"].params["page"] == "2"
    assert seen["headers"]["cookie"] == "sessionid=SECRET"
    assert seen["headers"]["user-agent"] == "UA/1"
    assert (page.page, page.next_page, page.pages, page.total) == (2, 3, 4, 100)
    p = page.posts[0]
    assert p.post_id == "1" and p.title == "Pretty 1" and p.page_count == 2
    assert p.preview_url == "https://t.nhentai.net/galleries/901/cover.jpg"
    assert p.source_url == "https://nhentai.net/g/1/"
    assert p.tags["general"] == ["big breasts", "x"]
    assert p.tags["artist"] == ["some artist"]
    assert p.tags["parody"] == ["original"]
    assert p.extra == {"media_id": "901", "page_exts": ["jpg", "png"]}
    assert (p.width, p.height) == (350, 500)


def test_empty_query_lists_all_and_last_page() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/api/galleries/all"
        return httpx.Response(200, json={"result": [], "num_pages": 1, "per_page": 25})

    page = make(handler).search([], page=1)
    assert page.posts == [] and page.next_page is None


def test_get_post_and_errors() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        code = {"/api/gallery/5": 404, "/api/gallery/6": 429, "/api/gallery/7": 403}
        if req.url.path in code:
            return httpx.Response(code[req.url.path])
        return httpx.Response(200, json=gallery(4))

    src = make(handler)
    assert src.get_post("4").post_id == "4"
    for pid, err in (("5", "not_found"), ("6", "rate_limited"), ("7", "upstream_error")):
        with pytest.raises(SourceError) as e:
            src.get_post(pid)
        assert e.value.code == err
    with pytest.raises(SourceError) as e:
        src.get_post("abc")
    assert e.value.code == "not_found"


def test_unreachable_and_bad_json() -> None:
    def boom(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("x")

    with pytest.raises(SourceError) as e:
        make(boom).search(["a"])
    assert e.value.code == "upstream_error"
    with pytest.raises(SourceError):
        make(lambda r: httpx.Response(200, json=[1])).search(["a"])


def test_cdn_host_pattern_and_file_hosts() -> None:
    for ok in ("i.nhentai.net", "i3.nhentai.net", "t.nhentai.net", "t9.nhentai.net"):
        assert CDN_HOST.match(ok)
    for bad in ("nhentai.net", "evil.nhentai.net", "i.nhentai.net.evil.com", "ii.nhentai.net"):
        assert not CDN_HOST.match(bad)
    assert make(lambda r: httpx.Response(200)).file_hosts[0] == "nhentai.net"


def test_cover_post_has_no_cookie(caplog: pytest.LogCaptureFixture) -> None:
    """The cookie never lands in a Post or in the logs."""
    p = make(lambda r: httpx.Response(200, json=gallery(3))).get_post("3")
    assert "SECRET" not in p.model_dump_json()
    assert "SECRET" not in caplog.text


def _client(tmp_path: Path, handler) -> TestClient:
    app = create_app(
        Settings(
            mode="real",
            real="search,jobs",
            stash_url="http://stash.invalid",
            db_path=tmp_path / "p.db",
            static_dir=tmp_path / "nostatic",
            worker_enabled=False,
            _env_file=None,  # pyright: ignore[reportCallIssue]
        )
    )
    app.state.sources["nhentai"] = make(handler)
    return TestClient(app)


def test_search_section_and_filters(tmp_path: Path) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        rows = [
            gallery(1),
            gallery(2, [{"type": "tag", "name": "bad"}]),
            gallery(3, [{"type": "artist", "name": "blocked artist"}]),
        ]
        return httpx.Response(200, json={"result": rows, "num_pages": 1, "per_page": 25})

    c = _client(tmp_path, handler)
    c.put(
        "/api/rules",
        json={
            "version": 1, "reject": ["bad", "artist:blocked artist"], "warn": [],
            "require": [], "mapping": [],
        },
    )
    sec = c.get("/api/search?q=x&sources=nhentai").json()["sections"][0]
    assert sec["id"] == "nhentai" and sec["hidden"] == 2
    item = sec["items"][0]
    assert item["target"] == "komga" and item["saveable"] is False
    assert item["title"] == "Pretty 1" and item["page_count"] == 2


def test_save_unavailable_until_komga_target(tmp_path: Path) -> None:
    c = _client(tmp_path, lambda r: httpx.Response(200, json=gallery(1)))
    r = c.post("/api/save", json={"source": "nhentai", "post_id": "1"})
    assert r.status_code == 422
    assert r.json()["code"] == "no_target"
