"""Thumb route with the D-17 cache: hit/miss, lane, refusals, redirects, hidden posts."""

import asyncio
import logging
import pathlib

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import media_web_real as mw
from app.filters.rules import RuleSet, save_rules
from app.sources.base import Post
from app.sources.throttle import Throttle
from tests.test_media_stash_real import stream_response
from tests.test_media_web_real import IMG, _app, _post

CDN = "cdn.donmai.us"
SAMPLE = f"https://{CDN}/sample/7.jpg"
JPEG = {"content-type": "image/jpeg"}


def _site(seen, respond=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == CDN:
            seen.append(request)
            if respond is not None:
                return respond(request)
            return stream_response(200, IMG, JPEG)
        return httpx.Response(200, json=_post() if "/posts/7" in request.url.path else [_post()])

    return handler


def _client(tmp_path, respond=None):
    seen: list[httpx.Request] = []
    app = _app(tmp_path, _site(seen, respond))
    return app, TestClient(app), seen


def _warm(client):
    client.get("/api/search", params={"q": "x", "sources": "danbooru"})


def _cached_files(tmp_path):
    return list((tmp_path / "thumbcache").rglob("*.img"))


def test_miss_fetches_once_stores_and_hit_makes_no_call(tmp_path):
    _app_, client, seen = _client(tmp_path)
    _warm(client)
    r = client.get("/api/media/web/danbooru/7/thumb")
    assert r.status_code == 200 and r.content == IMG
    assert r.headers["cache-control"] == "private, max-age=86400"
    assert len(seen) == 1 and len(_cached_files(tmp_path)) == 1
    again = client.get("/api/media/web/danbooru/7/thumb")
    assert again.content == IMG and len(seen) == 1
    cond = client.get(
        "/api/media/web/danbooru/7/thumb", headers={"If-None-Match": r.headers["etag"]}
    )
    assert cond.status_code == 304 and len(seen) == 1


def test_parallel_requests_make_one_fetch(tmp_path):
    app, warm_client, seen = _client(tmp_path)
    _warm(warm_client)

    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as c:
            return await asyncio.gather(
                *[c.get("/api/media/web/danbooru/7/thumb") for _ in range(4)]
            )

    results = asyncio.run(run())
    assert [r.status_code for r in results] == [200] * 4
    assert len(seen) == 1


def _timeout(_request):
    raise httpx.ConnectTimeout("slow")


@pytest.mark.parametrize(
    ("respond", "status"),
    [
        (lambda r: stream_response(404, b"", JPEG), 404),
        (lambda r: stream_response(410, b"", JPEG), 404),
        (lambda r: stream_response(200, b"<html>", {"content-type": "text/html"}), 502),
        (lambda r: stream_response(200, b"<svg/>", {"content-type": "image/svg+xml"}), 502),
        (lambda r: stream_response(200, b"not an image", JPEG), 502),
        (lambda r: stream_response(200, IMG + b"0" * mw.MAX_THUMB_BYTES, JPEG), 502),
        (_timeout, 502),
    ],
)
def test_refusals_store_nothing_and_repeat_is_remembered(tmp_path, respond, status):
    _app_, client, seen = _client(tmp_path, respond)
    _warm(client)
    r = client.get("/api/media/web/danbooru/7/thumb")
    assert r.status_code == status
    assert _cached_files(tmp_path) == []
    client.get("/api/media/web/danbooru/7/thumb")
    assert len(seen) == 1  # 60 s failure set: no re-request loop


def test_429_gives_503_retry_after_and_reports_to_both_throttles(tmp_path):
    def respond(request):
        return stream_response(429, b"", {**JPEG, "retry-after": "7"})

    app, client, _seen = _client(tmp_path, respond)
    _warm(client)
    r = client.get("/api/media/web/danbooru/7/thumb")
    assert r.status_code == 503 and r.headers["retry-after"] == "7"
    assert app.state.web_thumb_lanes["danbooru"].throttle.backing_off
    assert app.state.sources["danbooru"]._throttle.backing_off
    assert _cached_files(tmp_path) == []


@pytest.mark.parametrize(("hops", "status"), [(1, 200), (2, 200), (3, 502)])
def test_redirect_limit(tmp_path, hops, status):
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/final.jpg":
            return stream_response(200, IMG, JPEG)
        n = int(request.url.path.removeprefix("/hop").removesuffix(".jpg") or 0) if (
            request.url.path.startswith("/hop")
        ) else 0
        nxt = "/final.jpg" if n + 1 >= hops else f"/hop{n + 1}.jpg"
        return httpx.Response(302, headers={"location": f"https://{CDN}{nxt}"})

    _app_, client, _seen = _client(tmp_path, respond)
    _warm(client)
    assert client.get("/api/media/web/danbooru/7/thumb").status_code == status


@pytest.mark.parametrize("location", [f"http://{CDN}/x.jpg", "https://evil.example/x.jpg"])
def test_redirect_to_bad_target_is_refused(tmp_path, location):
    def respond(request):
        return httpx.Response(302, headers={"location": location})

    _app_, client, seen = _client(tmp_path, respond)
    _warm(client)
    assert client.get("/api/media/web/danbooru/7/thumb").status_code == 502
    assert len(seen) == 1
    assert _cached_files(tmp_path) == []


def test_lane_never_waits_on_main_throttle_and_misses_only(tmp_path):
    waits: list[int] = []

    class Counting(Throttle):
        def wait(self):
            waits.append(1)
            super().wait()

    app, client, seen = _client(tmp_path)
    app.state.sources["danbooru"]._throttle = Counting(0.0)
    _warm(client)
    base = len(waits)  # the search call
    client.get("/api/media/web/danbooru/7/thumb")
    client.get("/api/media/web/danbooru/7/thumb")
    assert len(waits) == base and len(seen) == 1
    assert app.state.web_thumb_lanes["danbooru"].throttle.interval == mw.THUMB_PACE


def test_abandoned_miss_does_not_fetch(tmp_path):
    app, client, seen = _client(tmp_path)
    _warm(client)
    src = app.state.sources["danbooru"]
    flight = mw._Flight(waiters=0)
    out = asyncio.run(
        mw._run_miss(app, src, ("danbooru", "7"), SAMPLE, app.state.thumb_cache, flight)
    )
    assert out is None and seen == []


def test_one_waiter_leaving_keeps_the_shared_fetch(tmp_path):
    app, client, seen = _client(tmp_path)
    _warm(client)
    src = app.state.sources["danbooru"]
    flight = mw._Flight(waiters=2)

    async def run():
        task = asyncio.create_task(
            mw._run_miss(app, src, ("danbooru", "7"), SAMPLE, app.state.thumb_cache, flight)
        )
        flight.waiters -= 1  # one waiter disconnects
        return await task

    out = asyncio.run(run())
    assert isinstance(out, mw._Thumb) and len(seen) == 1


def test_hidden_by_a_new_rule_is_404_even_when_cached(tmp_path):
    app, client, seen = _client(tmp_path)
    _warm(client)
    assert client.get("/api/media/web/danbooru/7/thumb").status_code == 200
    assert len(_cached_files(tmp_path)) == 1
    save_rules(app.state.settings.db_path, 1, RuleSet(1, ["x"], [], [], []))
    r = client.get("/api/media/web/danbooru/7/thumb")
    assert r.status_code == 404 and len(seen) == 1


def test_cached_without_map_entry_needs_get_post_and_evaluate(tmp_path):
    app, client, seen = _client(tmp_path)
    _warm(client)
    client.get("/api/media/web/danbooru/7/thumb")
    app2 = _app(tmp_path, _site(seen))  # restart: empty origin map
    asked: list[str] = []
    src = app2.state.sources["danbooru"]
    real = src.get_post

    def spy(pid):
        asked.append(pid)
        return real(pid)

    src.get_post = spy
    r = TestClient(app2).get("/api/media/web/danbooru/7/thumb")
    assert r.status_code == 200 and asked == ["7"] and len(seen) == 1


def test_rules_change_empties_the_origin_map(tmp_path):
    app, client, _seen = _client(tmp_path)
    _warm(client)
    mem = mw._memory(app)
    mem.sync_rules(1)
    assert mem.get("danbooru", "7") is not None
    mem.sync_rules(99)
    assert mem.get("danbooru", "7") is None


def test_hidden_posts_are_not_remembered(tmp_path):
    app, client, _seen = _client(tmp_path)
    save_rules(app.state.settings.db_path, 1, RuleSet(1, ["x"], [], [], []))
    _warm(client)
    assert mw._memory(app).get("danbooru", "7") is None


def test_disk_full_still_serves(tmp_path, monkeypatch):
    _app_, client, _seen = _client(tmp_path)
    _warm(client)
    real = pathlib.Path.write_bytes

    def boom(self, data):
        if self.name.endswith(".part"):
            raise OSError("disk full")
        return real(self, data)

    monkeypatch.setattr(pathlib.Path, "write_bytes", boom)
    r = client.get("/api/media/web/danbooru/7/thumb")
    assert r.status_code == 200 and r.content == IMG
    assert _cached_files(tmp_path) == []


def test_guards_and_no_secrets_in_logs(tmp_path, caplog):
    _app_, client, _seen = _client(tmp_path)
    _warm(client)
    for bad in ("a" * 33, "7.x", "7%20"):
        assert client.get(f"/api/media/web/danbooru/{bad}/thumb").status_code == 404
    with caplog.at_level(logging.DEBUG):
        client.get("/api/media/web/danbooru/7/thumb")
        client.get("/api/media/web/danbooru/7/thumb")
    text = caplog.text
    assert "site=danbooru post=7" in text
    assert CDN not in text and "SECRETKEY" not in text and "sample/7.jpg" not in text


def test_foreign_host_still_refused(tmp_path):
    app, client, seen = _client(tmp_path)
    post = Post(source="danbooru", post_id="9", sample_url="https://evil.example/x.jpg")
    mw.remember(app, [post])
    assert client.get("/api/media/web/danbooru/9/thumb").status_code == 404
    assert seen == []
