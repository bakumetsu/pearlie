"""Tests for the nhentai adapter and its search wiring (mocked, no network)."""

from __future__ import annotations

import json
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


FIX = Path(__file__).parent / "fixtures" / "nhentai_v2"


def fixture(name: str) -> dict:
    return json.loads((FIX / f"{name}.json").read_text(encoding="utf8"))


def gallery(i: int, tags: list[dict] | None = None) -> dict:
    """A full v2 gallery (single-gallery shape)."""
    return {
        "id": i,
        "media_id": f"90{i}",
        "title": {"english": f"Eng {i}", "pretty": f"Pretty {i}"},
        "cover": {"path": f"galleries/90{i}/cover.jpg", "width": 350, "height": 500},
        "thumbnail": {"path": f"galleries/90{i}/thumb.jpg", "width": 250, "height": 350},
        "pages": [
            {"number": 1, "path": f"galleries/90{i}/1.jpg", "width": 1, "height": 1},
            {"number": 2, "path": f"galleries/90{i}/2.png", "width": 1, "height": 1},
        ],
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


def row(i: int) -> dict:
    """A v2 list/search row: tag ids only, no pages, thumbnail instead of cover."""
    return {
        "id": i,
        "media_id": f"90{i}",
        "english_title": f"Row {i}",
        "japanese_title": "",
        "thumbnail": f"galleries/90{i}/thumb.webp",
        "thumbnail_width": 250,
        "thumbnail_height": 354,
        "num_pages": 7,
        "tag_ids": [1, 2],
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
            200, json={"result": [row(1), row(2)], "num_pages": 4, "per_page": 25, "total": 100}
        )

    page = make(handler).search(["artist:foo_bar"], page=2)
    assert seen["url"].path == "/api/v2/search"
    assert seen["url"].params["query"] == 'artist:"foo bar"'
    assert seen["url"].params["page"] == "2"
    assert seen["headers"]["cookie"] == "sessionid=SECRET"
    assert seen["headers"]["user-agent"] == "UA/1"
    assert (page.page, page.next_page, page.pages, page.total) == (2, 3, 4, 100)
    p = page.posts[0]
    assert p.post_id == "1" and p.title == "Row 1" and p.page_count == 7
    assert p.preview_url == "https://t.nhentai.net/galleries/901/thumb.webp"
    assert p.source_url == "https://nhentai.net/g/1/"
    assert p.tags == {}
    assert (p.width, p.height) == (250, 354)


def test_real_search_and_list_samples() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        name = "search" if req.url.path == "/api/v2/search" else "list"
        return httpx.Response(200, json=fixture(name))

    src = make(handler)
    page = src.search(["english"])
    assert len(page.posts) == 3 and page.pages == 6036 and page.next_page == 2
    assert page.posts[0].post_id == "696389"
    assert page.posts[0].title is not None and page.posts[0].page_count == 47
    listing = src.search([], page=20)
    assert len(listing.posts) == 3 and listing.pages == 20 and listing.next_page is None


def test_real_gallery_sample() -> None:
    seen: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["path"] = req.url.path
        return httpx.Response(200, json=fixture("gallery"))

    src = make(handler)
    p = src.get_post("694670")
    assert seen["path"] == "/api/v2/galleries/694670"
    assert p.title and p.title.startswith("Making a Harem")
    assert p.page_count == 197
    assert p.tags["category"] == ["doujinshi"] and p.tags["language"] == ["translated"]
    assert p.tags["general"] == ["big breasts", "sole male"]
    assert p.preview_url == "https://t.nhentai.net/galleries/4302773/cover.webp.webp"
    assert (p.width, p.height) == (350, 495)
    assert p.extra == {"media_id": "4302773", "page_exts": ["webp", "webp", "webp"]}
    assert src.page_urls(p) == [
        f"https://i.nhentai.net/galleries/4302773/{n}.webp" for n in (1, 2, 3)
    ]


def test_gallery_fields_and_page_urls() -> None:
    src = make(lambda r: httpx.Response(200, json=gallery(1)))
    p = src.get_post("1")
    assert p.title == "Pretty 1" and p.page_count == 2
    assert p.preview_url == "https://t.nhentai.net/galleries/901/cover.jpg"
    assert p.tags["general"] == ["big breasts", "x"]
    assert p.tags["artist"] == ["some artist"] and p.tags["parody"] == ["original"]
    assert p.extra == {"media_id": "901", "page_exts": ["jpg", "png"]}
    assert src.page_urls(p) == [
        "https://i.nhentai.net/galleries/901/1.jpg",
        "https://i.nhentai.net/galleries/901/2.png",
    ]


def test_bad_row_is_skipped_not_fatal() -> None:
    odd = row(2)
    odd["thumbnail_width"] = "wide"
    odd["thumbnail_height"] = None
    worse = row(3)
    worse["num_pages"] = "x"
    worse["thumbnail"] = {"nope": 1}

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "result": ["junk", {"no": "id"}, row(1), odd, worse, row(4)],
                "num_pages": 1,
                "per_page": 25,
            },
        )

    posts = make(handler).search([]).posts
    assert [p.post_id for p in posts] == ["1", "2", "3", "4"]
    assert posts[1].width == 0
    assert posts[2].preview_url is None


def test_cover_path_must_stay_in_galleries() -> None:
    g = gallery(1)
    g["cover"] = {"path": "../evil.jpg", "width": 1, "height": 1}
    assert make(lambda r: httpx.Response(200, json=g)).get_post("1").preview_url is None


def test_empty_query_lists_all_and_last_page() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/api/v2/galleries"
        return httpx.Response(200, json={"result": [], "num_pages": 1, "per_page": 25})

    page = make(handler).search([], page=1)
    assert page.posts == [] and page.next_page is None


def test_get_post_and_errors() -> None:
    codes = {5: 404, 6: 429, 7: 403, 8: 503, 9: 500}

    def handler(req: httpx.Request) -> httpx.Response:
        pid = int(req.url.path.rsplit("/", 1)[1])
        if pid in codes:
            return httpx.Response(codes[pid])
        return httpx.Response(200, json=gallery(4))

    src = make(handler)
    assert src.get_post("4").post_id == "4"
    expected = {5: "not_found", 6: "rate_limited", 7: "upstream_error"}
    for pid, status in codes.items():
        with pytest.raises(SourceError) as e:
            src.get_post(str(pid))
        assert e.value.code == expected.get(pid, "upstream_error")
        assert e.value.status == status
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
            "version": 1,
            "reject": ["bad", "artist:blocked artist"],
            "warn": [],
            "require": [],
            "mapping": [],
        },
    )
    sec = c.get("/api/search?q=x&sources=nhentai").json()["sections"][0]
    assert sec["id"] == "nhentai" and sec["hidden"] == 2
    item = sec["items"][0]
    assert item["target"] == "komga" and item["saveable"] is True
    assert item["title"] == "Pretty 1" and item["page_count"] == 2


def test_save_unavailable_until_komga_target(tmp_path: Path) -> None:
    c = _client(tmp_path, lambda r: httpx.Response(200, json=gallery(1)))
    r = c.post("/api/save", json={"source": "nhentai", "post_id": "1"})
    assert r.status_code == 422
    assert r.json()["code"] == "no_target"
