"""Real web-source media proxy: URL pick, throttle, headers, streaming, guards."""

import httpx
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.sources.base import Post
from app.sources.danbooru import Danbooru
from app.sources.nhentai import NHentai
from app.sources.throttle import Throttle
from tests.test_media_stash_real import stream_response

IMG = b"\xff\xd8\xffJPEGDATA"


def _post(**kw) -> dict:
    d = {
        "id": 7,
        "md5": "a" * 32,
        "file_url": "https://cdn.donmai.us/original/7.jpg",
        "large_file_url": "https://cdn.donmai.us/sample/7.jpg",
        "preview_file_url": "https://cdn.donmai.us/180x180/7.jpg",
        "image_width": 10,
        "image_height": 10,
        "rating": "g",
        "tag_string_general": "x",
    }
    d.update(kw)
    return d


def _app(tmp_path, handler, **creds):
    app = create_app(
        Settings(
            mode="real",
            real="search,media_web",
            db_path=tmp_path / "p.db",
            static_dir=tmp_path / "nostatic",
            _env_file=None,  # pyright: ignore[reportCallIssue]
        )
    )
    app.state.sources["danbooru"] = Danbooru(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        throttle=Throttle(0.0),
        credentials=lambda: {"login": "me", "api_key": "SECRETKEY"},
    )
    return app


def _handler(seen: list[httpx.Request], cdn_status: int = 200, ctype: str = "image/jpeg"):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.host == "cdn.donmai.us":
            return stream_response(cdn_status, IMG, {"content-type": ctype})
        return httpx.Response(200, json=_post() if "/posts/7" in request.url.path else [_post()])

    return handler


def test_thumb_streams_sample_with_safe_headers(tmp_path):
    seen: list[httpx.Request] = []
    client = TestClient(_app(tmp_path, _handler(seen)))
    client.get("/api/search", params={"q": "x", "sources": "danbooru"})
    r = client.get("/api/media/web/danbooru/7/thumb")
    assert r.status_code == 200
    assert r.content == IMG
    assert r.headers["content-type"] == "image/jpeg"
    cdn = [q for q in seen if q.url.host == "cdn.donmai.us"]
    assert [str(q.url) for q in cdn] == ["https://cdn.donmai.us/sample/7.jpg"]
    assert cdn[0].headers["referer"] == "https://danbooru.donmai.us/"
    assert "authorization" not in cdn[0].headers
    assert "cookie" not in cdn[0].headers
    assert "SECRETKEY" not in r.text and "SECRETKEY" not in str(r.headers)


def test_full_uses_original_and_forwards_range(tmp_path):
    seen: list[httpx.Request] = []
    client = TestClient(_app(tmp_path, _handler(seen)))
    r = client.get("/api/media/web/danbooru/7/full", headers={"Range": "bytes=0-3"})
    assert r.status_code == 200
    cdn = [q for q in seen if q.url.host == "cdn.donmai.us"]
    assert str(cdn[0].url) == "https://cdn.donmai.us/original/7.jpg"
    assert cdn[0].headers["range"] == "bytes=0-3"


def test_cold_post_falls_back_to_get_post(tmp_path):
    seen: list[httpx.Request] = []
    client = TestClient(_app(tmp_path, _handler(seen)))
    r = client.get("/api/media/web/danbooru/7/preview")
    assert r.status_code == 200
    assert any("/posts/7" in q.url.path for q in seen)


def test_guards(tmp_path):
    client = TestClient(_app(tmp_path, _handler([])))
    assert client.get("/api/media/web/nope/7/thumb").status_code == 404
    assert client.get("/api/media/web/danbooru/7/bogus").status_code == 404
    assert client.get("/api/media/web/danbooru/abc/thumb").status_code == 404


def test_foreign_host_is_refused(tmp_path):
    seen: list[httpx.Request] = []
    app = _app(tmp_path, _handler(seen))
    client = TestClient(app)
    from app.api.media_web_real import remember

    remember(app, [Post(source="danbooru", post_id="9", sample_url="https://evil.example/x.jpg")])
    assert client.get("/api/media/web/danbooru/9/thumb").status_code == 404
    assert seen == []


def test_upstream_html_or_error_is_502(tmp_path):
    for status, ctype in ((200, "text/html"), (403, "image/jpeg")):
        client = TestClient(_app(tmp_path, _handler([], status, ctype)))
        r = client.get("/api/media/web/danbooru/7/thumb")
        assert r.status_code == 502, (status, ctype)


def test_upstream_429_backs_off_throttle(tmp_path):
    app = _app(tmp_path, _handler([], 429))
    client = TestClient(app)
    r = client.get("/api/media/web/danbooru/7/thumb")
    assert r.status_code == 503 and r.json()["code"] == "rate_limited"
    assert r.headers["retry-after"]
    assert app.state.sources["danbooru"]._throttle.backing_off
    full = client.get("/api/media/web/danbooru/7/full")
    assert full.status_code == 429 and full.json()["code"] == "rate_limited"
    assert full.headers["retry-after"]
    lim = app.state.image_slots.limiter("danbooru", "i")
    assert lim.slots == 6 and lim.in_flight == 0


def test_nhentai_cover_thumb_and_cookie_not_sent(tmp_path):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return stream_response(200, IMG, {"content-type": "image/webp"})

    app = _app(tmp_path, handler)
    app.state.sources["nhentai"] = NHentai(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        throttle=Throttle(0.0),
        credentials=lambda: {"cookie": "sid=SECRETCOOKIE", "user_agent": "UA/1"},
    )
    from app.api.media_web_real import remember

    remember(
        app,
        [
            Post(
                source="nhentai",
                post_id="901",
                preview_url="https://t.nhentai.net/galleries/901/thumb.webp",
                sample_url="https://t.nhentai.net/galleries/901/thumb.webp",
            )
        ],
    )
    r = TestClient(app).get("/api/media/web/nhentai/901/thumb")
    assert r.status_code == 200
    assert "cookie" not in seen[0].headers
    assert seen[0].headers["referer"] == "https://nhentai.net/"


def test_media_kind_follows_preview_extension():
    from app.api.media_web_real import media_kind

    def post(**kw):
        return Post(source="rule34", post_id="1", tags={}, width=1, height=1, **kw)

    assert media_kind(post(file_url="https://x/a.mp4?v=1")) == "video"
    assert media_kind(post(file_url="https://x/a.WEBM")) == "video"
    assert media_kind(post(file_url="https://x/a.gif")) == "image"
    assert media_kind(post(preview_url="https://x/t.jpg")) == "image"


def test_retry_after_ignores_non_finite_and_negative() -> None:
    from app.api.media_web_real import _retry_after

    for raw in ("inf", "nan", "-5"):
        assert _retry_after(httpx.Response(429, headers={"Retry-After": raw})) is None
    assert _retry_after(httpx.Response(429, headers={"Retry-After": "7"})) == 7.0


def test_images_per_site_setting_sets_slots_and_503_falls_back(tmp_path):
    app = _app(tmp_path, _handler([], 503))
    client = TestClient(app)
    assert client.get("/api/options").json()["images_per_site"] == 10
    assert client.put("/api/options", json={"images_per_site": 8}).json()["images_per_site"] == 8
    assert client.put("/api/options", json={"images_per_site": 17}).status_code == 422
    assert client.put("/api/options", json={"images_per_site": 0}).status_code == 422
    r = client.get("/api/media/web/danbooru/7/preview")
    assert r.status_code == 502
    lim = app.state.image_slots.limiter("danbooru", "i")
    assert lim.ceiling == 8 and lim.slots == 6 and lim.in_flight == 0


def test_preview_stream_frees_slot(tmp_path):
    app = _app(tmp_path, _handler([]))
    client = TestClient(app)
    assert client.get("/api/media/web/danbooru/7/preview").content == IMG
    assert app.state.image_slots.limiter("danbooru", "i").in_flight == 0


def test_preview_and_full_apply_rules_to_cold_post(tmp_path):
    from app.filters.rules import RuleSet, load_rules, save_rules

    seen: list[httpx.Request] = []
    app = _app(tmp_path, _handler(seen))
    client = TestClient(app)
    db = app.state.settings.db_path
    version = load_rules(db).version
    save_rules(db, version, RuleSet(version=version, reject=["x"], warn=[], require=[], mapping=[]))
    for kind in ("preview", "full", "thumb"):
        assert client.get(f"/api/media/web/danbooru/7/{kind}").status_code == 404, kind
    assert [q for q in seen if q.url.host == "cdn.donmai.us"] == []


def test_rules_version_is_read_once_per_ttl_and_refreshed_on_save(tmp_path, monkeypatch):
    from app.api import media_web_real as mw
    from app.filters.rules import RuleSet, load_rules, save_rules

    app = _app(tmp_path, _handler([]))
    client = TestClient(app)
    client.get("/api/search", params={"q": "x", "sources": "danbooru"})
    mw._version_cache.clear()
    calls = []
    orig = mw.connect
    monkeypatch.setattr(mw, "connect", lambda p: calls.append(p) or orig(p))
    for _ in range(5):
        assert client.get("/api/media/web/danbooru/7/thumb").status_code == 200
    assert len(calls) == 1
    rules = load_rules(tmp_path / "p.db")
    save_rules(
        tmp_path / "p.db",
        rules.version,
        RuleSet(rules.version, ["x"], [], [], []),
    )
    client.get("/api/media/web/danbooru/7/thumb")
    assert len(calls) == 2
