"""relay() closes the upstream on end, on error and on client abort; web seek answers."""

import asyncio

import httpx
from fastapi.testclient import TestClient

from app.api.relay import relay
from tests.test_media_stash_real import stream_response
from tests.test_media_web_real import IMG, _app, _post


class _Chunks:
    def __init__(self, n: int) -> None:
        self._it = iter([b"x"] * n)
        self.closed = False

    def __iter__(self):
        return self

    def __next__(self) -> bytes:
        return next(self._it)

    def close(self) -> None:
        self.closed = True


def test_relay_passes_all_chunks_and_closes() -> None:
    chunks, closed = _Chunks(3), []

    async def run() -> list[bytes]:
        return [c async for c in relay(chunks, lambda: closed.append(1))]

    assert asyncio.run(run()) == [b"x"] * 3
    assert chunks.closed and closed == [1]


def test_relay_closes_upstream_when_client_aborts() -> None:
    chunks, closed = _Chunks(100), []

    async def run() -> None:
        gen = relay(chunks, lambda: closed.append(1))
        await gen.__anext__()
        await gen.aclose()  # what a cancelled response does after a seek

    asyncio.run(run())
    assert chunks.closed and closed == [1]


def test_range_past_end_passes_416_through(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "cdn.donmai.us":
            return stream_response(
                416, b"", {"content-type": "text/html", "content-range": "bytes */11"}
            )
        return httpx.Response(200, json=_post() if "/posts/7" in request.url.path else [_post()])

    app = _app(tmp_path, handler)
    r = TestClient(app).get("/api/media/web/danbooru/7/preview", headers={"Range": "bytes=99-"})
    assert r.status_code == 416
    assert r.headers["content-range"] == "bytes */11"
    assert app.state.image_slots.limiter("danbooru", "i").in_flight == 0


def test_video_206_relays_range_headers(tmp_path) -> None:
    hdr = {"content-type": "video/mp4", "content-range": "bytes 2-5/11", "accept-ranges": "bytes"}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "cdn.donmai.us":
            return stream_response(206, IMG, hdr)
        return httpx.Response(200, json=_post() if "/posts/7" in request.url.path else [_post()])

    app = _app(tmp_path, handler)
    r = TestClient(app).get("/api/media/web/danbooru/7/preview", headers={"Range": "bytes=2-5"})
    assert r.status_code == 206
    assert r.headers["content-range"] == "bytes 2-5/11"
    assert r.content == IMG
    assert app.state.image_slots.limiter("danbooru", "i").in_flight == 0
