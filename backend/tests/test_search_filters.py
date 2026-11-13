"""Order and rating filters on /api/search and the /api/search/filters capability list."""
from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.sources.danbooru import Danbooru
from app.sources.dapi import Gelbooru, Rule34
from app.sources.filters import danbooru_plan, dapi_filter_tags
from app.sources.throttle import Throttle


def _mock(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def _danbooru(handler) -> Danbooru:
    return Danbooru(client=_mock(handler), throttle=Throttle(0.0))


def _real_client(tmp_path, **sources) -> TestClient:
    app = create_app(
        Settings(
            mode="real",
            real="search",
            db_path=tmp_path / "p.db",
            static_dir=tmp_path / "nostatic",
            _env_file=None,  # pyright: ignore[reportCallIssue]
        )
    )
    app.state.sources.update(sources)
    return TestClient(app)


def _dan_post(i: int, rating: str) -> dict:
    return {"id": i, "rating": rating, "md5": f"{i:032x}", "tag_string_general": "a"}


# --- slot planning -------------------------------------------------------------------------


def test_plan_order_and_rating_take_free_slots():
    server, local, notes = danbooru_plan([], "score", ["g", "s"], 2)
    assert server == ["order:score", "rating:g,s"]
    assert local == [] and notes == []


def test_plan_one_free_slot_order_wins_rating_local():
    server, local, notes = danbooru_plan(["cat"], "score", ["g"], 2)
    assert server == ["cat", "order:score"]
    assert local == ["rating:g"]
    assert notes == ["Rating filtered on this page only"]


def test_plan_chips_fill_cap_order_blocked():
    server, local, notes = danbooru_plan(["a", "b"], "score", ["e"], 2)
    assert server == ["a", "b"]
    assert local == ["rating:e"]
    assert len(notes) == 2 and "Order" in notes[0]


def test_plan_all_ratings_is_no_filter_and_chips_past_cap_stay_local():
    server, local, notes = danbooru_plan(["a", "b", "c"], None, ["g", "s", "q", "e"], 2)
    assert server == ["a", "b"] and local == ["c"] and notes == []


def test_dapi_tag_mapping():
    assert dapi_filter_tags("gelbooru", "score", ["e"]) == (
        ["sort:score:desc", "rating:explicit"],
        [],
    )
    tags, _ = dapi_filter_tags("gelbooru", None, ["g", "s"])
    assert tags == ["-rating:questionable", "-rating:explicit"]
    assert dapi_filter_tags("rule34", None, ["g"])[0] == ["rating:safe"]
    # rule34 has no sensitive: only that value asked -> dropped with a notice
    tags, notes = dapi_filter_tags("rule34", None, ["s"])
    assert tags == [] and notes
    # every supported value = no filter
    assert dapi_filter_tags("rule34", None, ["g", "s", "q", "e"])[0] == []


# --- real mode, mocked sites -----------------------------------------------------------------


def test_danbooru_sends_order_and_rating_in_one_request(tmp_path):
    urls: list[httpx.URL] = []

    def handler(req: httpx.Request) -> httpx.Response:
        urls.append(req.url)
        return httpx.Response(200, json=[_dan_post(1, "g")])

    client = _real_client(tmp_path, danbooru=_danbooru(handler))
    r = client.get("/api/search?sources=danbooru&order=score&rating=g,s")
    assert r.status_code == 200
    assert len(urls) == 1
    assert urls[0].params["tags"] == "order:score rating:g,s"
    assert r.json()["sections"][0]["notice"] is None


def test_danbooru_one_slot_rating_filtered_locally_with_notice(tmp_path):
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.params["tags"] == "cat order:score"
        return httpx.Response(200, json=[_dan_post(1, "g"), _dan_post(2, "e")])

    client = _real_client(tmp_path, danbooru=_danbooru(handler))
    url = "/api/search?q=cat&sources=danbooru&order=score&rating=g"
    sec = client.get(url).json()["sections"][0]
    assert [i["post_id"] for i in sec["items"]] == ["1"]
    assert sec["notice"]["message"] == "Rating filtered on this page only"


def test_dapi_rating_sent_server_side(tmp_path):
    seen: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["tags"] = req.url.params["tags"]
        return httpx.Response(200, json={"post": [{"id": 5, "rating": "explicit", "tags": "x"}]})

    gel = Gelbooru(client=_mock(handler), throttle=Throttle(0.0))
    client = _real_client(tmp_path, gelbooru=gel)
    sec = client.get("/api/search?q=x&sources=gelbooru&order=score&rating=e").json()["sections"][0]
    assert seen["tags"] == "x sort:score:desc rating:explicit"
    assert len(sec["items"]) == 1


def test_rule34_sends_safe_tag(tmp_path):
    seen: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["tags"] = req.url.params["tags"]
        return httpx.Response(200, json=[])

    r34 = Rule34(client=_mock(handler), throttle=Throttle(0.0))
    client = _real_client(tmp_path, rule34=r34)
    client.get("/api/search?sources=rule34&rating=g")
    assert seen["tags"] == "rating:safe"


def test_bad_values_are_422(client: TestClient):
    assert client.get("/api/search?order=random").status_code == 422
    assert client.get("/api/search?rating=g,x").status_code == 422


# --- fixture mode ------------------------------------------------------------------------------


def test_fixture_rating_filters_items(client: TestClient):
    sec = client.get("/api/search?sources=gelbooru&rating=e&page_size=100").json()["sections"][0]
    assert sec["items"] and sec["notice"] is None
    all_sec = client.get("/api/search?sources=gelbooru&page_size=100").json()["sections"][0]
    assert sec["total"] < all_sec["total"]


def test_fixture_order_score_changes_order(client: TestClient):
    plain = client.get("/api/search?sources=gelbooru").json()["sections"][0]["items"]
    scored = client.get("/api/search?sources=gelbooru&order=score").json()["sections"][0]["items"]
    assert [i["post_id"] for i in plain] != [i["post_id"] for i in scored]


def test_fixture_danbooru_order_blocked_notice(client: TestClient):
    sec = client.get("/api/search?q=a b&sources=danbooru&order=score").json()["sections"][0]
    assert sec["notice"] and "Order" in sec["notice"]["message"]


def test_fixture_nhentai_drops_filters_with_notice(client: TestClient):
    sec = client.get("/api/search?sources=nhentai&order=score&rating=g").json()["sections"][0]
    assert "not available" in sec["notice"]["message"]
    assert sec["total"] > 0


# --- capability list ---------------------------------------------------------------------------


def test_filters_capability_list(client: TestClient):
    src = client.get("/api/search/filters").json()["sources"]
    assert src["danbooru"]["order"] == ["newest", "score"]
    assert src["danbooru"]["rating"] == ["g", "s", "q", "e"]
    assert src["danbooru"]["order_blocked_when"] == 2
    assert src["rule34"]["rating"] == ["g", "q", "e"]
    assert src["nhentai"]["order"] == [] and src["nhentai"]["per_page_max"] == 25
    assert src["stash_images"]["sort"] == ["newest", "rating", "random"]
    assert src["stash_images"]["favorite"] is True
    assert src["gelbooru"]["per_page_max"] == 100
