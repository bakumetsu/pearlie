"""Tests for the Danbooru source adapter."""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.sources.base import SourceError
from app.sources.danbooru import Danbooru
from app.sources.throttle import Throttle

FIX = Path(__file__).parent / "fixtures" / "danbooru"


def load(name: str):
    """Return parsed JSON fixture."""
    return json.loads((FIX / f"{name}.json").read_text())


def make(handler, **kw):
    """Build a Danbooru backed by a MockTransport."""
    return Danbooru(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        throttle=Throttle(0.0),
        **kw,
    )


class FakeClock:
    """A controllable clock for throttle tests."""

    def __init__(self) -> None:
        self.t: float = 0.0
        self.sleeps: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.sleeps.append(s)
        self.t += s


def test_search_maps_posts():
    """search maps danbooru posts to the Post model with correct fields."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/posts.json"
        assert request.url.params["tags"] == "1girl solo"
        assert request.url.params["page"] == "2"
        assert request.url.params["limit"] == "60"
        return httpx.Response(200, json=load("search"))

    d = make(handler)
    result = d.search(["1girl", "solo"], 2)

    assert len(result.posts) == 3
    p = result.posts[0]
    assert p.post_id == "101"
    assert p.source == "danbooru"
    assert p.md5 == "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"
    assert p.file_url is not None
    assert p.width == 1280
    assert p.height == 853
    assert p.rating == "general"
    assert p.tags["artist"] == ["artist_a"]
    assert p.tags["general"] == ["1girl", "solo", "smile"]
    assert p.source_url == "https://danbooru.donmai.us/posts/101"

    assert result.posts[1].rating == "explicit"
    assert result.posts[2].file_url is None
    assert result.posts[2].rating == "sensitive"


def test_tag_cap_filters_locally():
    """Tags beyond tag_limit are applied as local post-filters."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["tags"] == "1girl solo"
        return httpx.Response(200, json=load("search"))

    d = make(handler)
    result = d.search(["1girl", "solo", "-blue_hair", "scenery"])
    assert [p.post_id for p in result.posts] == ["103"]


def test_ignores_meta_tags_locally():
    """Non-rating metatags (containing a colon) are skipped during local filtering."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=load("search"))

    d = make(handler)
    result = d.search(["a", "b", "order:score"])
    assert len(result.posts) == 3


def test_next_page():
    """next_page equals page+1 when count == page_size, else None."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=load("search"))

    d = make(handler, page_size=3)
    result = d.search(["1girl"], 1)
    assert result.next_page == 2

    d2 = make(handler)
    result2 = d2.search(["1girl"], 1)
    assert result2.next_page is None


def test_get_post():
    """get_post fetches and maps a single post by numeric id."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/posts/101.json"
        return httpx.Response(200, json=load("post"))

    d = make(handler)
    p = d.get_post("101")
    assert p.post_id == "101"
    assert p.source == "danbooru"
    assert p.md5 == "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"
    assert p.width == 1280
    assert p.height == 853
    assert p.rating == "general"
    assert p.tags["artist"] == ["artist_a"]
    assert p.source_url == "https://danbooru.donmai.us/posts/101"


def test_get_post_missing():
    """get_post raises SourceError(not_found) on a 404 response."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json=load("not_found"))

    d = make(handler)
    with pytest.raises(SourceError) as exc:
        d.get_post("999")
    assert exc.value.code == "not_found"


def test_get_post_bad_id_makes_no_request():
    """A non-numeric id raises not_found without issuing any HTTP request."""
    requests_made: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_made.append(str(request.url))
        return httpx.Response(200, json=load("post"))

    d = make(handler)
    with pytest.raises(SourceError) as exc:
        d.get_post("abc")
    assert exc.value.code == "not_found"
    assert requests_made == []


@pytest.mark.parametrize(
    "status,code",
    [(500, "upstream_error"), (503, "upstream_error"), (429, "rate_limited"), (422, "bad_request")],
)
def test_http_errors(status, code):
    """HTTP error statuses map to the correct SourceError code."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status)

    d = make(handler)
    with pytest.raises(SourceError) as exc:
        d.search(["test"], 1)
    assert exc.value.code == code
    assert "http" not in str(exc.value).lower()


def test_network_error():
    """A ConnectError from the transport maps to upstream_error."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    d = make(handler)
    with pytest.raises(SourceError) as exc:
        d.search(["test"], 1)
    assert exc.value.code == "upstream_error"


def test_invalid_json():
    """Non-JSON or wrong-shape response bodies raise upstream_error."""

    def handler_html(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>")

    d = make(handler_html)
    with pytest.raises(SourceError) as exc:
        d.search(["test"], 1)
    assert exc.value.code == "upstream_error"

    def handler_dict(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": True})

    d2 = make(handler_dict)
    with pytest.raises(SourceError) as exc2:
        d2.search(["test"], 1)
    assert exc2.value.code == "upstream_error"


def test_throttle_fake_clock():
    """Throttle.wait sleeps only when elapsed time is below min_interval."""
    c = FakeClock()
    th = Throttle(1.0, clock=c.now, sleep=c.sleep)
    th.wait()
    assert c.sleeps == []
    th.wait()
    assert c.sleeps == [1.0]
    c.t += 5
    th.wait()
    assert c.sleeps == [1.0]


def test_source_waits_between_requests():
    """Danbooru throttles between consecutive requests including get_post."""
    c = FakeClock()

    def handler(request: httpx.Request) -> httpx.Response:
        if "/posts.json" in request.url.path:
            return httpx.Response(200, json=load("search"))
        return httpx.Response(200, json=load("post"))

    d = Danbooru(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        throttle=Throttle(1.0, clock=c.now, sleep=c.sleep),
    )
    d.search(["test"], 1)
    d.search(["test"], 1)
    assert c.sleeps == [1.0]
    d.get_post("101")
    assert c.sleeps == [1.0, 1.0]


def _all_posts(request):
    return httpx.Response(200, json=load("search"))


def test_rating_filter_local():
    d = make(_all_posts)

    result = d.search(["a", "b", "rating:e"], page=1)
    assert [p.post_id for p in result.posts] == ["102"]
    assert result.dropped == []

    result = d.search(["a", "b", "-rating:e"], page=1)
    assert [p.post_id for p in result.posts] == ["101", "103"]
    assert result.dropped == []

    result = d.search(["a", "b", "rating:q,e"], page=1)
    assert [p.post_id for p in result.posts] == ["102"]
    assert result.dropped == []

    result = d.search(["a", "b", "rating:g,s"], page=1)
    assert [p.post_id for p in result.posts] == ["101", "103"]
    assert result.dropped == []

    result = d.search(["a", "b", "rating:explicit"], page=1)
    assert [p.post_id for p in result.posts] == ["102"]
    assert result.dropped == []


def test_other_metatag_reported():
    d = make(_all_posts)

    result = d.search(["a", "b", "order:score"], page=1)
    assert len(result.posts) == 3
    assert result.dropped == ["order:score"]

    result = d.search(["a", "b", "-user:foo", "rating:e"], page=1)
    assert [p.post_id for p in result.posts] == ["102"]
    assert result.dropped == ["-user:foo"]

    result = d.search(["a", "b", "rating:zzz"], page=1)
    assert result.dropped == ["rating:zzz"]


def test_metatag_inside_cap_not_dropped():
    d = make(_all_posts)

    result = d.search(["rating:e", "b"], page=1)
    assert result.dropped == []
