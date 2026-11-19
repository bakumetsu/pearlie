"""Title chip: nhentai query, Stump q, skip notes, capability flags, rules guards (mocked)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import init_db
from app.main import create_app
from app.sources.danbooru import Danbooru
from app.sources.nhentai import NHentai, build_query
from app.sources.throttle import Throttle

CREDS = {"cookie": "sessionid=SECRET", "user_agent": "UA/1"}


@pytest.mark.parametrize(
    ("tags", "query"),
    [
        (['title:"big dragon"'], '"big dragon"'),
        (["-title:x"], '-"x" pages:>0'),
        (['title:"a b"', "artist:foo_bar"], '"a b" artist:"foo bar"'),
        (["title:foo_bar"], '"foo bar"'),
        (['title:a"b'], '"a b"'),
        (["title:", "title:  "], ""),
        (["-title:x", "-tag:y"], '-"x" -tag:"y" pages:>0'),
        (["-title:x", "title:y"], '-"x" "y"'),
        (["title:" + "a" * 300], '"' + "a" * 200 + '"'),
    ],
)
def test_build_query_title(tags: list[str], query: str) -> None:
    assert build_query(tags) == query


def _row(i: int) -> dict:
    return {
        "id": i,
        "media_id": f"90{i}",
        "english_title": f"Row {i}",
        "thumbnail": f"galleries/90{i}/thumb.webp",
        "thumbnail_width": 250,
        "thumbnail_height": 354,
        "num_pages": 7,
        "tag_ids": [],
    }


def _app(tmp_path: Path, nh_handler=None, stump_handler=None, real="search") -> TestClient:
    from app.stump import Stump

    db_path = tmp_path / "p.db"
    init_db(db_path)
    app = create_app(
        Settings(
            mode="real",
            real=real,
            db_path=db_path,
            static_dir=tmp_path / "nostatic",
            worker_enabled=False,
            _env_file=None,  # pyright: ignore[reportCallIssue]
        )
    )
    if nh_handler:
        app.state.sources["nhentai"] = NHentai(
            client=httpx.Client(transport=httpx.MockTransport(nh_handler)),
            throttle=Throttle(0.0),
            credentials=lambda: CREDS,
        )
    app.state.stash = None
    app.state.stump = (
        Stump(
            "http://stump.test",
            "k",
            client=httpx.Client(
                base_url="http://stump.test", transport=httpx.MockTransport(stump_handler)
            ),
        )
        if stump_handler
        else None
    )
    return TestClient(app)


def _nh_ok(seen: list):
    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json={"result": [_row(1)], "num_pages": 1, "total": 1})

    return handler


def _stump_ok(seen: list):
    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json={"content": [], "last": True, "totalElements": 0})

    return handler


def test_nhentai_title_chip_sends_quoted_term(tmp_path) -> None:
    seen: list = []
    client = _app(tmp_path, nh_handler=_nh_ok(seen))
    r = client.get(
        "/api/search", params={"q": 'title:"big dragon" artist:x', "sources": "nhentai"}
    )
    assert len(r.json()["sections"][0]["items"]) == 1
    assert len(seen) == 1
    assert seen[0].url.params["query"] == 'artist:"x" "big dragon"'


def test_bare_quoted_words_are_one_term(tmp_path) -> None:
    seen: list = []
    client = _app(tmp_path, nh_handler=_nh_ok(seen))
    client.get("/api/search", params={"q": '"big dragon"', "sources": "nhentai"})
    assert seen[0].url.params["query"] == '"big dragon"'


def test_unsupported_source_skipped_without_request(tmp_path) -> None:
    seen: list = []
    dan_seen: list = []
    client = _app(tmp_path, nh_handler=_nh_ok(seen))

    def dan(req: httpx.Request) -> httpx.Response:
        dan_seen.append(req)
        return httpx.Response(200, json=[])

    client.app.state.sources["danbooru"] = Danbooru(  # type: ignore[attr-defined]
        client=httpx.Client(transport=httpx.MockTransport(dan)), throttle=Throttle(0.0)
    )
    r = client.get(
        "/api/search", params={"q": 'title:"x y"', "sources": "danbooru,stash_images,nhentai"}
    )
    secs = {s["id"]: s for s in r.json()["sections"]}
    for sid in ("danbooru", "stash_images"):
        assert secs[sid]["items"] == []
        assert secs[sid]["total"] == 0
        assert secs[sid]["notice"]["message"] == "Title search not available on this site"
    assert dan_seen == []
    assert len(seen) == 1


def test_stump_title_sends_only_title_text(tmp_path) -> None:
    seen: list = []
    client = _app(tmp_path, stump_handler=_stump_ok(seen))
    r = client.get(
        "/api/search",
        params={"q": 'cat title:"big dragon" "two"', "sources": "stump_books"},
    )
    assert len(seen) == 1
    assert json.loads(seen[0].content)["fullTextSearch"] == "big dragon two"
    notice = r.json()["sections"][0]["notice"]
    assert notice["message"] == "Tag chips do not narrow Stump results"


def test_stump_title_without_tags_has_no_notice(tmp_path) -> None:
    seen: list = []
    client = _app(tmp_path, stump_handler=_stump_ok(seen))
    r = client.get("/api/search", params={"q": 'title:"a"', "sources": "stump_books"})
    assert json.loads(seen[0].content)["fullTextSearch"] == "a"
    assert r.json()["sections"][0]["notice"] is None


def test_stump_without_title_keeps_q(tmp_path) -> None:
    seen: list = []
    client = _app(tmp_path, stump_handler=_stump_ok(seen))
    client.get("/api/search", params={"q": "cat dog", "sources": "stump_books"})
    assert json.loads(seen[0].content)["fullTextSearch"] == "cat dog"


def test_stump_excluded_title_skipped(tmp_path) -> None:
    seen: list = []
    client = _app(tmp_path, stump_handler=_stump_ok(seen))
    r = client.get("/api/search", params={"q": '-title:"x"', "sources": "stump_books"})
    assert seen == []
    sec = r.json()["sections"][0]
    assert sec["notice"]["message"] == "Title exclusion not available on this site"
    assert sec["items"] == []


def test_filters_flags(tmp_path) -> None:
    client = _app(tmp_path)
    srcs = client.get("/api/search/filters").json()["sources"]
    assert srcs["nhentai"]["title_search"] and srcs["nhentai"]["title_exclude"]
    assert srcs["stump_books"]["title_search"] and not srcs["stump_books"]["title_exclude"]
    for sid in ("stash_images", "stash_videos", "danbooru", "gelbooru", "rule34"):
        assert not srcs[sid]["title_search"]
        assert not srcs[sid]["title_exclude"]


def test_title_never_reaches_rules(tmp_path, monkeypatch) -> None:
    """A title chip is not a tag: the rule check sees post tags only."""
    import app.api.search_real as sr

    calls: list = []
    real_eval = sr.evaluate

    def spy(tags, rules):
        calls.append(tags)
        return real_eval(tags, rules)

    monkeypatch.setattr(sr, "evaluate", spy)
    client = _app(tmp_path, nh_handler=_nh_ok([]), real="search,rules")
    r = client.get("/api/search", params={"q": 'title:"row"', "sources": "nhentai"})
    assert len(r.json()["sections"][0]["items"]) == 1
    assert calls == [{}]


@pytest.mark.parametrize("mode", ["fixture", "real"])
def test_rules_refuse_reserved_prefix(tmp_path, mode) -> None:
    db_path = tmp_path / "p.db"
    init_db(db_path)
    extra = {"real": "rules"} if mode == "real" else {}
    client = TestClient(
        create_app(
            Settings(
                mode=mode,  # pyright: ignore[reportArgumentType]
                db_path=db_path,
                static_dir=tmp_path / "nostatic",
                worker_enabled=False,
                _env_file=None,  # pyright: ignore[reportCallIssue]
                **extra,
            )
        )
    )
    version = client.get("/api/rules").json()["version"]
    for field in ("reject", "warn", "require"):
        body = {"version": version, "reject": [], "warn": [], "require": [], "mapping": []}
        body[field] = ["title:x"]
        r = client.put("/api/rules", json=body)
        assert r.status_code == 422
        assert r.json()["field"] == field
    assert client.post("/api/rules/test", json={"tags": ["id:5"]}).status_code == 422
    assert client.post("/api/rules/reject", json={"tag": "-title:x"}).status_code == 422
    assert client.post("/api/rules/test", json={"tags": ["artist:x"]}).status_code == 200
