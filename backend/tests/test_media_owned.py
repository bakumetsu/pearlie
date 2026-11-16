"""Owned web posts load from Stash (D-28); any library failure falls back to the site."""

from __future__ import annotations

import logging

import httpx
from fastapi.testclient import TestClient

from app.api import media_owned
from app.api.media_owned import is_owned
from app.db import connect, init_db
from app.komga import Komga
from app.models import SavedRef
from app.targets.stash_client import StashClient
from tests.test_media_stash_real import KEY, URL, stream_response
from tests.test_media_web_real import IMG, _app, _handler, _post

STASH_IMG = b"\x89PNGSTASH"


def _save(app, post_id="7", target="stash", image_id="42", kind="image", md5="a" * 32) -> None:
    init_db(app.state.settings.db_path)
    conn = connect(app.state.settings.db_path)
    try:
        conn.execute(
            "INSERT INTO saved_items (source, post_id, md5, target, image_id, kind) "
            "VALUES ('danbooru', ?, ?, ?, ?, ?)",
            (post_id, md5, target, image_id, kind),
        )
        conn.commit()
    finally:
        conn.close()


def _stash(app, handler) -> None:
    app.state.stash = StashClient(
        URL,
        KEY,
        client=httpx.Client(
            base_url=URL, headers={"ApiKey": KEY}, transport=httpx.MockTransport(handler)
        ),
    )


def _setup(tmp_path, stash_handler, **save):
    site: list[httpx.Request] = []
    app = _app(tmp_path, _handler(site))
    _save(app, **save)
    stash: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        stash.append(request)
        return stash_handler(request)

    _stash(app, wrapped)
    return app, TestClient(app), site, stash


def _ok(request: httpx.Request) -> httpx.Response:
    return stream_response(200, STASH_IMG, {"content-type": "image/png"})


def _gone(request: httpx.Request) -> httpx.Response:
    return stream_response(404, b"", {})


def _cdn(site):
    return [q for q in site if q.url.host == "cdn.donmai.us"]


def test_owned_image_streams_from_stash_without_site_call(tmp_path):
    app, client, site, stash = _setup(tmp_path, _ok)
    r = client.get("/api/media/web/danbooru/7/full")
    assert r.status_code == 200 and r.content == STASH_IMG
    assert str(stash[0].url) == f"{URL}/image/42/image"
    assert _cdn(site) == []
    assert getattr(app.state, "image_slots", None) is None  # no limiter slot was taken
    assert KEY not in str(r.headers) and "stash.test" not in str(r.headers)


def test_range_passes_through_to_stash(tmp_path):
    def h(request):
        return stream_response(
            206, b"ab", {"content-type": "image/png", "content-range": "bytes 0-1/9"}
        )

    _, client, _, stash = _setup(tmp_path, h)
    r = client.get("/api/media/web/danbooru/7/full", headers={"Range": "bytes=0-1"})
    assert r.status_code == 206 and r.headers["content-range"] == "bytes 0-1/9"
    assert stash[0].headers["range"] == "bytes=0-1"


def test_stash_404_falls_back_and_second_request_skips_stash(tmp_path, caplog):
    _, client, site, stash = _setup(tmp_path, _gone)
    with caplog.at_level(logging.INFO, logger="pearlie.media_owned"):
        r1 = client.get("/api/media/web/danbooru/7/full")
        r2 = client.get("/api/media/web/danbooru/7/preview")
    assert r1.status_code == 200 and r1.content == IMG
    assert r2.status_code == 200 and r2.content == IMG
    assert len(stash) == 1  # failure remembered
    assert len(_cdn(site)) == 2
    assert "OWNED route=site" in caplog.text
    assert KEY not in caplog.text and "stash.test" not in caplog.text


def test_stash_unreachable_and_bad_type_fall_back(tmp_path):
    def boom(request):
        raise httpx.ConnectError("down")

    _, client, _, _ = _setup(tmp_path, boom)
    assert client.get("/api/media/web/danbooru/7/full").content == IMG

    def html(request):
        return stream_response(200, b"<html>", {"content-type": "text/html"})

    _, client, _, _ = _setup(tmp_path / "b", html)
    assert client.get("/api/media/web/danbooru/7/full").content == IMG


def test_failure_memory_expires(tmp_path, monkeypatch):
    _, client, _, stash = _setup(tmp_path, _gone)
    client.get("/api/media/web/danbooru/7/full")
    monkeypatch.setattr(media_owned.time, "monotonic", lambda: 10**9)
    client.get("/api/media/web/danbooru/7/full")
    assert len(stash) == 2


def test_many_failures_switch_the_route_off(tmp_path):
    app, client, _, stash = _setup(tmp_path, _ok)
    for i in range(media_owned.OFF_AFTER):
        media_owned._note_failure(app, ("danbooru", f"x{i}"))
    assert client.get("/api/media/web/danbooru/7/full").content == IMG
    assert stash == []


def test_thumb_never_calls_stash(tmp_path):
    _, client, _, stash = _setup(tmp_path, _ok)
    assert client.get("/api/media/web/danbooru/7/thumb").content == IMG
    assert stash == []


def test_komga_row_empty_id_and_bad_id_are_site(tmp_path):
    for i, save in enumerate(
        ({"target": "komga", "image_id": ""}, {"image_id": ""}, {"image_id": "../x"})
    ):
        _, client, _, stash = _setup(tmp_path / str(i), _ok, **save)
        assert client.get("/api/media/web/danbooru/7/full").content == IMG
        assert stash == []


def test_row_kind_must_match_post_kind(tmp_path):
    _, client, _, stash = _setup(tmp_path, _ok, kind="video")  # the post is an image
    assert client.get("/api/media/web/danbooru/7/full").content == IMG
    assert stash == []


def test_md5_match_from_another_post_routes_to_stash(tmp_path):
    _, client, _, stash = _setup(tmp_path, _ok, post_id="999")
    assert client.get("/api/media/web/danbooru/7/full").content == STASH_IMG
    assert len(stash) == 1


def test_no_stash_configured_uses_site(tmp_path):
    app = _app(tmp_path, _handler([]))
    _save(app)
    if hasattr(app.state, "stash"):
        del app.state.stash
    assert TestClient(app).get("/api/media/web/danbooru/7/full").content == IMG


def test_is_owned_flag():
    assert is_owned(SavedRef(kind="image", id="1"))
    assert is_owned(SavedRef(kind="video", id="1"))
    assert not is_owned(SavedRef(kind="book", id=""))
    assert not is_owned(SavedRef(kind="image", id=""))
    assert not is_owned(None)


def test_search_sets_owned_for_a_stash_row(tmp_path):
    _, client, _, _ = _setup(tmp_path, _ok)
    body = client.get("/api/search", params={"q": "x", "sources": "danbooru"}).json()
    flat = [i for s in body["sections"] for i in s["items"]]
    assert flat and flat[0]["owned"] is True


def test_video_full_streams_scene_and_preview_uses_scene_preview(tmp_path):
    site: list[httpx.Request] = []
    vid = {
        "file_url": "https://cdn.donmai.us/original/7.mp4",
        "preview_file_url": "https://cdn.donmai.us/180x180/7.mp4",
    }

    def site_handler(request):
        site.append(request)
        return httpx.Response(200, json=_post(**vid))

    app = _app(tmp_path, site_handler)
    _save(app, kind="video")
    seen: list[httpx.Request] = []

    def h(request):
        seen.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={"data": {"findScene": {"paths": {"preview": None}}}})
        return stream_response(
            206, b"vv", {"content-type": "video/mp4", "content-range": "bytes 0-1/9"}
        )

    _stash(app, h)
    client = TestClient(app)
    r = client.get("/api/media/web/danbooru/7/full", headers={"Range": "bytes=0-1"})
    assert r.status_code == 206 and r.content == b"vv"
    p = client.get("/api/media/web/danbooru/7/preview")
    assert p.status_code == 206
    assert [q.url.path for q in seen if q.method == "GET"] == [
        "/scene/42/stream",
        "/scene/42/preview",
    ]
    assert _cdn(site) == []


def test_cold_post_get_post_failure_is_asked_once(tmp_path):
    calls: list[httpx.Request] = []

    def site(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(502, json={})

    app = _app(tmp_path, site)
    _save(app)
    _stash(app, _ok)
    r = TestClient(app).get("/api/media/web/danbooru/7/full")
    assert r.status_code >= 400
    assert len(calls) == 1


BOOK = "0ABC123DEF456"
KOMGA_URL = "http://komga.test"


def _komga(app, handler) -> list[httpx.Request]:
    seen: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    app.state.komga = Komga(
        KOMGA_URL,
        "k",
        client=httpx.Client(base_url=KOMGA_URL, transport=httpx.MockTransport(wrapped)),
    )
    return seen


def _komga_row(app, post_id="7", library_id=BOOK, md5="b" * 32, source="danbooru") -> None:
    init_db(app.state.settings.db_path)
    conn = connect(app.state.settings.db_path)
    try:
        conn.execute(
            "INSERT INTO saved_items (source, post_id, md5, target, image_id, library_id) "
            "VALUES (?, ?, ?, 'komga', '', ?)",
            (source, post_id, md5, library_id),
        )
        conn.commit()
    finally:
        conn.close()


def _page(request: httpx.Request) -> httpx.Response:
    return stream_response(200, b"\xff\xd8KOMGA", {"content-type": "image/jpeg"})


def test_owned_komga_post_streams_page_one_from_komga(tmp_path):
    site: list[httpx.Request] = []
    app = _app(tmp_path, _handler(site))
    _komga_row(app)
    seen = _komga(app, _page)
    r = TestClient(app).get("/api/media/web/danbooru/7/full")
    assert r.status_code == 200 and r.content == b"\xff\xd8KOMGA"
    assert seen[0].url.path == f"/api/v1/books/{BOOK}/pages/1"
    assert _cdn(site) == []
    assert "komga.test" not in str(r.headers)


def test_komga_failure_falls_back_to_site_once(tmp_path):
    site: list[httpx.Request] = []
    app = _app(tmp_path, _handler(site))
    _komga_row(app)
    seen = _komga(app, lambda r: stream_response(404, b"", {}))
    client = TestClient(app)
    assert client.get("/api/media/web/danbooru/7/full").content == IMG
    assert client.get("/api/media/web/danbooru/7/preview").content == IMG
    assert len(seen) == 1  # failure remembered


def test_old_komga_row_is_backfilled_with_one_search(tmp_path):
    app = _app(tmp_path, _handler([]))
    _komga_row(app, library_id=None)  # type: ignore[arg-type]

    def handler(request):
        if request.url.path == "/api/v1/books/list":
            book = {"id": BOOK, "url": "/data/x [7].cbz", "metadata": {}}
            return httpx.Response(200, json={"content": [book]})
        return _page(request)

    seen = _komga(app, handler)
    client = TestClient(app)
    assert client.get("/api/media/web/danbooru/7/full").content == b"\xff\xd8KOMGA"
    conn = connect(app.state.settings.db_path)
    try:
        row = conn.execute("SELECT library_id FROM saved_items").fetchone()
    finally:
        conn.close()
    assert row["library_id"] == BOOK
    searches = [q for q in seen if q.url.path.endswith("/books/list")]
    client.get("/api/media/web/danbooru/7/full")
    assert len([q for q in seen if q.url.path.endswith("/books/list")]) == len(searches)


def test_bad_book_id_uses_site(tmp_path):
    app = _app(tmp_path, _handler([]))
    _komga_row(app, library_id="../x")
    seen = _komga(app, _page)
    assert TestClient(app).get("/api/media/web/danbooru/7/full").content == IMG
    assert seen == []


def test_is_owned_book_needs_an_id():
    assert is_owned(SavedRef(kind="book", id=BOOK))


def test_nhentai_reader_page_comes_from_komga(tmp_path):
    from tests.test_media_web_pages import Rig

    rig = Rig(tmp_path)
    _komga_row(rig.app, post_id="7", source="nhentai")
    seen = _komga(rig.app, _page)
    r = rig.client.get("/api/media/web/nhentai/7/pages/2")
    assert r.content == b"\xff\xd8KOMGA" and rig.cdn() == []
    assert seen[0].url.path == f"/api/v1/books/{BOOK}/pages/2"
    t = rig.client.get("/api/media/web/nhentai/7/pages/3/thumb")
    assert t.status_code == 200 and seen[1].url.path == f"/api/v1/books/{BOOK}/pages/3/thumbnail"
    book = rig.client.get("/api/media/web/nhentai/7/book").json()
    assert book["item"]["owned"] is True
