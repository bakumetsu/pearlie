"""Stream edges: slot heartbeat, video idle limit, 429, Komga type, Stash manifest cap."""

import asyncio

import httpx
from fastapi.testclient import TestClient

from app.api.image_slots import STALE_GRANT_S, Limiter, SlotBody
from tests.test_komga_media_ids import make_client as komga_client
from tests.test_media_stash_real import make_client as stash_client
from tests.test_media_stash_real import stream_response
from tests.test_media_web_real import _app, _handler


def test_slot_touch_keeps_stream_alive(tmp_path):
    t = [0.0]
    lim = Limiter("i", ceiling=1, clock=lambda: t[0])
    lim.slots = 1

    async def never():
        return False

    async def run():
        held = await lim.acquire("focus", never)
        t[0] = STALE_GRANT_S - 1
        held.touch()
        t[0] = STALE_GRANT_S + 5
        lim._dispatch()
        assert held.done is False
        t[0] = STALE_GRANT_S * 3
        lim._dispatch()
        assert held.done is True

    asyncio.run(run())


def test_slotbody_video_past_wall_clock_is_not_cut(tmp_path):
    class FakeResp:
        status_code = 200

        def __init__(self, clock):
            self._clock = clock
            self._chunks = [b"a", b"a", b"a"]

        def iter_raw(self, *a):
            for c in self._chunks:
                self._clock[0] += 100
                yield c

        def close(self):
            pass

    class FakeSlot:
        def __init__(self):
            self.touches = 0
            self.status = None

        def touch(self):
            self.touches += 1

        def finish(self, status=None):
            self.status = status

    clock = [0.0]
    slot = FakeSlot()
    body = SlotBody(
        FakeResp(clock),
        slot,  # pyright: ignore[reportArgumentType]
        time_limit=1.0,
        wall_clock=False,
        clock=lambda: clock[0],
    )
    assert b"".join(iter(body)) == b"aaa"
    assert slot.touches == 3

    clock2 = [0.0]
    body2 = SlotBody(
        FakeResp(clock2),
        FakeSlot(),  # pyright: ignore[reportArgumentType]
        time_limit=1.0, wall_clock=True, clock=lambda: clock2[0]
    )
    assert b"".join(iter(body2)) == b"a"


def test_web_429_is_429_with_retry_after(tmp_path):
    app = _app(tmp_path, _handler([], 429))
    r = TestClient(app).get("/api/media/web/danbooru/7/full")
    assert r.status_code == 429
    assert r.json()["code"] == "rate_limited"
    assert r.headers["retry-after"].isdigit()


def test_komga_non_image_is_502(tmp_path):
    def h(request):
        return httpx.Response(200, content=b"<html>", headers={"content-type": "text/html"})

    r = komga_client(tmp_path, h).get("/api/media/komga/books/abc/pages/1")
    assert r.status_code == 502
    assert r.json()["code"] == "upstream_error"


def test_stash_manifest_over_cap_is_502(tmp_path):
    def h(request):
        return stream_response(200, b"#EXTM3U\n" + b"x" * 1_100_000, {})

    r = stash_client(tmp_path, h).get("/api/media/stash/videos/5/s/stream.m3u8")
    assert r.status_code == 502
