"""nhentai book and page routes: meta cache, error map, limiter, fixture mode (all mocked)."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import image_slots
from app.api.image_slots import Busy, Gone, Limiter
from app.api.media_web_pages import image_urls
from app.config import Settings
from app.main import create_app
from app.sources.nhentai import NHentai
from app.sources.throttle import Throttle
from app.sources.title import parse_title
from tests.test_media_stash_real import stream_response

IMG = b"\xff\xd8\xffJPEGDATA"
RAW_TITLES = json.loads(
    (Path(__file__).parent / "fixtures" / "nhentai_titles.json").read_text(encoding="utf-8")
)


def _gallery(pages: int = 3) -> dict:
    return {
        "id": 7,
        "media_id": "4242",
        "title": {
            "english": "[Circle (Artist)] Romaji - English Name [English]",
            "japanese": "JP title",
            "pretty": "English Name",
        },
        "pages": [{"path": f"galleries/4242/{n}.jpg"} for n in range(1, pages + 1)],
        "cover": {"path": "galleries/4242/cover.jpg", "width": 3, "height": 4},
        "tags": [{"type": "tag", "name": "x"}, {"type": "language", "name": "english"}],
        "num_pages": pages,
    }


class Rig:
    def __init__(self, tmp_path: Path, cdn_status=200, ctype="image/jpeg", retry=None):
        self.seen: list[httpx.Request] = []
        self.cdn_status, self.ctype, self.retry = cdn_status, ctype, retry

        def handler(request: httpx.Request) -> httpx.Response:
            self.seen.append(request)
            if request.url.host == "nhentai.net":
                if request.url.path == "/api/v2/galleries/7":
                    return httpx.Response(200, json=_gallery())
                return httpx.Response(404, json={})
            headers = {"content-type": self.ctype}
            if self.retry:
                headers["retry-after"] = str(self.retry)
            return stream_response(self.cdn_status, IMG, headers)

        self.app = create_app(
            Settings(
                mode="real",
                db_path=tmp_path / "p.db",
                static_dir=tmp_path / "nostatic",
                _env_file=None,  # pyright: ignore[reportCallIssue]
            )
        )
        self.app.state.sources["nhentai"] = NHentai(
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            throttle=Throttle(0.0),
            credentials=lambda: {"cookie": "SECRETCOOKIE", "user_agent": "UA"},
        )
        self.client = TestClient(self.app)

    def cdn(self) -> list[httpx.Request]:
        return [r for r in self.seen if r.url.host != "nhentai.net"]


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path)


@pytest.mark.parametrize("k", range(9))
def test_parse_title_cases(k):
    p = parse_title(RAW_TITLES[k], "JP title" if k == 8 else None)
    assert p.title_main and "nhentai-" not in p.title_main and "[" not in p.title_main
    if k == 8:
        assert (p.title_main, p.title_sub, p.language) == (
            "Moonlit Tea Room Diary",
            "JP title",
            "English",
        )
    if k == 6:
        assert (p.event, p.translator, p.language) == ("COMIC Anthurium 2021-03", "Nisor", "English")
        assert p.title_sub == "Otonashi Ookami"
    if k == 0:
        assert p.language == "English" and p.translator is None  # cut-off "[Coffed" dropped


def test_book_meta_and_cache(rig):
    r = rig.client.get("/api/media/web/nhentai/7/book")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    body = r.json()
    assert body["page_count"] == 3 and body["page_url"].endswith("/pages/{n}")
    assert body["title_main"] == "English Name" and body["language"] == "English"
    assert body["item"]["post_id"] == "7"
    rig.client.get("/api/media/web/nhentai/7/pages/1")
    rig.client.get("/api/media/web/nhentai/7/pages/2/thumb")
    api = [r for r in rig.seen if r.url.host == "nhentai.net"]
    assert len(api) == 1  # one API call per gallery


def test_page_and_thumb_stream_without_cookie(rig):
    r = rig.client.get("/api/media/web/nhentai/7/pages/2")
    assert r.status_code == 200 and r.content == IMG
    assert r.headers["cache-control"] == "private, max-age=3600"
    t = rig.client.get("/api/media/web/nhentai/7/pages/3/thumb")
    assert t.status_code == 200
    urls = [str(x.url) for x in rig.cdn()]
    assert urls[0].endswith("/galleries/4242/2.jpg") and urls[1].endswith("/3t.jpg")
    assert urls[0].startswith("https://i") and urls[1].startswith("https://t")
    assert all("cookie" not in x.headers for x in rig.cdn())
    assert all("SECRETCOOKIE" not in str(x.url) for x in rig.seen)


def test_shard_stable():
    first = image_urls("4242", 1, "jpg", False)
    assert first[0].startswith("https://i3.nhentai.net/")
    assert image_urls("4242", 9, "png", False)[0].startswith("https://i3.nhentai.net/")
    assert first[1].startswith("https://i.nhentai.net/")  # plain-host fallback


@pytest.mark.parametrize("path", ["pages/0", "pages/4", "pages/4/thumb", "pages/x"])
def test_bad_page_numbers(rig, path):
    r = rig.client.get(f"/api/media/web/nhentai/7/{path}")
    assert r.status_code in (404, 422)
    if r.status_code == 404:
        assert r.json()["code"] == "not_found"


def test_unknown_gallery_404(rig):
    assert rig.client.get("/api/media/web/nhentai/99/book").status_code == 404
    assert rig.client.get("/api/media/web/nhentai/abc/book").status_code == 404


def test_content_type_guard(tmp_path):
    r = Rig(tmp_path, ctype="text/html").client.get("/api/media/web/nhentai/7/pages/1")
    assert r.status_code == 502 and r.json()["code"] == "upstream_error"


def test_429_maps_with_retry_after(tmp_path):
    rig = Rig(tmp_path, cdn_status=429, retry=7)
    r = rig.client.get("/api/media/web/nhentai/7/pages/1")
    assert r.status_code == 429 and r.headers["retry-after"] == "7"
    lim = rig.app.state.image_slots.limiter("nhentai", "i")
    assert lim.slots == 1 and lim.in_flight == 0


def test_prio_unknown_falls_back(rig):
    assert rig.client.get("/api/media/web/nhentai/7/pages/1?prio=bogus").status_code == 200
    assert rig.client.get("/api/media/web/nhentai/7/pages/1?prio=prefetch").status_code == 200
    assert image_slots.parse_prio("bogus", "focus") == "focus"
    assert image_slots.parse_prio("cover", "focus") == "cover"


def test_slot_free_after_request(rig):
    rig.client.get("/api/media/web/nhentai/7/pages/1")
    assert rig.app.state.image_slots.limiter("nhentai", "i").in_flight == 0


# ---- limiter ----


class Clock:
    t = 1000.0

    def __call__(self) -> float:
        return self.t


async def _never() -> bool:
    return False


async def _always() -> bool:
    return True


def test_ramp_and_ceiling():
    c = Clock()
    lim = Limiter("i", ceiling=4, clock=c)
    assert lim.slots == 2
    for _ in range(40):
        lim._record(200, None, 1.0)
    assert lim.slots == 4  # never above the ceiling
    assert Limiter("t", clock=c).slots == 4


def test_backoff_slow_and_recover():
    c = Clock()
    lim = Limiter("t", clock=c)
    lim._record(429, 5.0, 1.0)
    assert lim.slots == 1 and lim._pause_until == c.t + 5.0
    for _ in range(30):
        lim._record(200, None, 1.0)
    assert lim.slots == 2  # +1 per 30 clean after a back-off
    for _ in range(3):
        lim._record(200, None, 9.0)
    assert lim.slots == 1  # slow spell


def test_setting_cap_applies():
    assert Limiter("i", ceiling=1).slots == 1


def test_slot_limit_priority_and_release():
    async def go():
        lim = Limiter("i", ceiling=2)
        a = await lim.acquire("focus", _never)
        b = await lim.acquire("focus", _never)
        assert lim.in_flight == 2
        order: list[str] = []

        async def want(name, prio):
            s = await lim.acquire(prio, _never)
            order.append(name)
            s.finish(200)

        tasks = [
            asyncio.create_task(want("prefetch", "prefetch")),
            asyncio.create_task(want("cover", "cover")),
            asyncio.create_task(want("focus", "focus")),
        ]
        await asyncio.sleep(0.05)
        assert lim.in_flight == 2 and not order
        a.finish(200)
        b.finish(200)
        await asyncio.gather(*tasks)
        assert order[0] == "focus"
        assert lim.in_flight == 0

    asyncio.run(go())


def test_disconnect_while_queued_and_busy():
    async def go():
        lim = Limiter("i", ceiling=1)
        held = await lim.acquire("focus", _never)
        with pytest.raises(Gone):
            await lim.acquire("focus", _always)
        with pytest.raises(Busy):
            await lim.acquire("focus", _never, wait_cap=0.3)
        held.finish(None)
        assert lim.in_flight == 0
        s = await lim.acquire("focus", _never)  # the abandoned entries took no slot
        assert lim.in_flight == 1
        s.finish(None)

    asyncio.run(go())


def test_stale_grant_reclaimed():
    c = Clock()
    lim = Limiter("i", ceiling=1, clock=c)

    async def go():
        await lim.acquire("focus", _never)
        c.t += image_slots.STALE_GRANT_S + 1
        s = await lim.acquire("focus", _never)
        assert lim.in_flight == 1
        s.finish(None)

    asyncio.run(go())


# ---- fixture mode ----


def test_fixture_routes(tmp_path):
    app = create_app(
        Settings(
            mode="fixture",
            db_path=tmp_path / "p.db",
            static_dir=tmp_path / "nostatic",
            _env_file=None,  # pyright: ignore[reportCallIssue]
        )
    )
    c = TestClient(app)
    s = c.get("/api/search?q=&sources=nhentai").json()
    gid = s["sections"][0]["items"][0]["post_id"]
    b = c.get(f"/api/media/web/nhentai/{gid}/book")
    assert b.status_code == 200
    n = b.json()["page_count"]
    assert c.get(f"/api/media/web/nhentai/{gid}/pages/1").status_code == 200
    assert c.get(f"/api/media/web/nhentai/{gid}/pages/1/thumb").status_code == 200
    assert c.get(f"/api/media/web/nhentai/{gid}/pages/{n + 1}").status_code == 404
    assert c.get("/api/media/web/nhentai/nope/book").status_code == 404
