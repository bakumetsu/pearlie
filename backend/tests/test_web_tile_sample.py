from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from app.api.search_real import _web_thumb
from app.config import Settings
from app.main import create_app
from app.sources.base import Post
from app.sources.danbooru import Danbooru
from app.sources.dapi import Gelbooru, Rule34
from app.sources.throttle import Throttle


def _noop_handler(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=[])


def _make_danbooru() -> Danbooru:
    return Danbooru(
        client=httpx.Client(transport=httpx.MockTransport(_noop_handler)),
        throttle=Throttle(0.0),
    )


def _make_rule34() -> Rule34:
    return Rule34(
        client=httpx.Client(transport=httpx.MockTransport(_noop_handler)),
        throttle=Throttle(0.0),
    )


def _make_gelbooru() -> Gelbooru:
    return Gelbooru(
        client=httpx.Client(transport=httpx.MockTransport(_noop_handler)),
        throttle=Throttle(0.0),
    )


def test_danbooru_to_post_sample_url():
    """large_file_url maps to sample_url; preview_file_url to preview_url."""
    db = _make_danbooru()
    post = db._to_post(
        {
            "id": 1,
            "large_file_url": "https://cdn.donmai.us/sample/x.jpg",
            "preview_file_url": "https://cdn.donmai.us/180x180/x.jpg",
            "file_url": "https://cdn.donmai.us/original/x.jpg",
        }
    )
    assert post.sample_url == "https://cdn.donmai.us/sample/x.jpg"
    assert post.preview_url == "https://cdn.donmai.us/180x180/x.jpg"


def test_danbooru_to_post_no_large_file_url():
    """Absence of large_file_url yields sample_url is None."""
    db = _make_danbooru()
    post = db._to_post(
        {
            "id": 1,
            "preview_file_url": "https://cdn.donmai.us/180x180/x.jpg",
            "file_url": "https://cdn.donmai.us/original/x.jpg",
        }
    )
    assert post.sample_url is None


def test_rule34_to_post_sample_url():
    """Rule34 sample_url passes through unchanged."""
    r34 = _make_rule34()
    post = r34._to_post(
        {
            "id": 2,
            "hash": "a" * 32,
            "file_url": "https://r34.example/2.jpg",
            "preview_url": "https://r34.example/t_2.jpg",
            "sample_url": "https://r34.example/s_2.jpg",
            "tags": "a b",
            "rating": "explicit",
        }
    )
    assert post.sample_url == "https://r34.example/s_2.jpg"


def test_gelbooru_to_post_sample_url():
    """Gelbooru uses md5 key; sample_url passes through unchanged."""
    gel = _make_gelbooru()
    post = gel._to_post(
        {
            "id": 2,
            "md5": "a" * 32,
            "file_url": "https://gelbooru.example/2.jpg",
            "preview_url": "https://gelbooru.example/t_2.jpg",
            "sample_url": "https://gelbooru.example/s_2.jpg",
            "tags": "a b",
            "rating": "explicit",
        }
    )
    assert post.sample_url == "https://gelbooru.example/s_2.jpg"


def test_web_thumb_prefers_sample():
    """_web_thumb returns sample_url when it is a non-video image."""
    post = Post(
        source="danbooru",
        post_id="1",
        sample_url="https://x/s.jpg",
        preview_url="https://x/p.jpg",
    )
    assert _web_thumb(post) == "https://x/s.jpg"


def test_web_thumb_falls_back_to_preview():
    """_web_thumb returns preview_url when sample_url is absent."""
    post = Post(
        source="danbooru",
        post_id="1",
        sample_url=None,
        preview_url="https://x/p.jpg",
    )
    assert _web_thumb(post) == "https://x/p.jpg"


def test_web_thumb_empty():
    """_web_thumb returns empty string when neither sample nor preview exist."""
    post = Post(
        source="danbooru",
        post_id="1",
        sample_url=None,
        preview_url=None,
    )
    assert _web_thumb(post) == ""


def test_web_thumb_video_fallback():
    """_web_thumb skips video sample_url and returns preview."""
    post_mp4 = Post(
        source="danbooru",
        post_id="1",
        sample_url="https://x/s.mp4",
        preview_url="https://x/p.jpg",
    )
    assert _web_thumb(post_mp4) == "https://x/p.jpg"

    post_webm = Post(
        source="danbooru",
        post_id="1",
        sample_url="https://x/s.WEBM?x=1",
        preview_url="https://x/p.jpg",
    )
    assert _web_thumb(post_webm) == "https://x/p.jpg"


def test_end_to_end_thumb_url(tmp_path):
    """Full request: search returns thumb_url from large_file_url."""
    sample_url = "https://cdn.donmai.us/sample/7.jpg"
    preview_url = "https://cdn.donmai.us/180x180/7.jpg"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "id": 7,
                    "md5": "a" * 32,
                    "file_url": "https://cdn.donmai.us/original/7.jpg",
                    "large_file_url": sample_url,
                    "preview_file_url": preview_url,
                    "image_width": 10,
                    "image_height": 10,
                    "rating": "g",
                    "tag_string_general": "x",
                }
            ],
        )

    app = create_app(
        Settings(
            mode="real",
            real="search",
            db_path=tmp_path / "p.db",
            static_dir=tmp_path / "nostatic",
            _env_file=None,  # pyright: ignore[reportCallIssue]
        )
    )
    app.state.sources["danbooru"] = Danbooru(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        throttle=Throttle(0.0),
    )
    client = TestClient(app)
    resp = client.get("/api/search", params={"q": "x", "sources": "danbooru"})
    assert resp.status_code == 200
    items = resp.json()["sections"][0]["items"]
    assert items[0]["thumb_url"] == sample_url
