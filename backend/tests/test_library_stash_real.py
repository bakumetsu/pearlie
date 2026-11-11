"""Tests for the real-mode Stash library endpoints."""

from __future__ import annotations

import json
from typing import Any

import httpx
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.targets.stash_client import StashClient

KEY = "s-secret-456"
URL = "http://stash.test"


def make_client(tmp_path, handler):
    """Build a TestClient with a mock-backed Stash client."""
    app = create_app(
        Settings(
            mode="real",
            real="library_stash",
            stash_url=URL,
            db_path=tmp_path / "p.db",
            static_dir=tmp_path / "nostatic",
            _env_file=None,  # pyright: ignore[reportCallIssue]
        )
    )
    app.state.stash = StashClient(
        URL,
        KEY,
        client=httpx.Client(base_url=URL, transport=httpx.MockTransport(handler)),
    )
    return TestClient(app)


def image_dto(id="1", **over):
    """Return a minimal valid Stash image DTO."""
    d = {
        "id": id,
        "title": "Test Image",
        "rating100": 80,
        "created_at": "2024-01-01T00:00:00Z",
        "urls": ["https://example.com/src.jpg"],
        "tags": [{"name": "tag_b"}, {"name": "tag_a"}],
        "visual_files": [
            {"basename": "photo.jpg", "width": 1920, "height": 1080, "size": 1234},
        ],
    }
    d.update(over)
    return d


def scene_dto(id="2", **over):
    """Return a minimal valid Stash scene (video) DTO."""
    d = {
        "id": id,
        "title": "Test Scene",
        "rating100": 60,
        "created_at": "2024-02-01T00:00:00Z",
        "urls": ["https://example.com/scene.mp4"],
        "tags": [{"name": "tag_b"}, {"name": "tag_a"}],
        "files": [
            {
                "basename": "clip.mp4",
                "width": 1920,
                "height": 1080,
                "duration": 120.0,
                "video_codec": "h264",
                "size": 5678,
            },
        ],
    }
    d.update(over)
    return d


# ---------------------------------------------------------------------------
# 1 – images list: mapping, pagination, GraphQL variables
# ---------------------------------------------------------------------------


def test_images_list_mapping_and_pagination(tmp_path):
    """Items mapped, total == count, next_page set only when page*page_size < count."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "data": {
                "findImages": {
                    "count": 10,
                    "images": [image_dto("a"), image_dto("b")],
                }
            }
        })

    client = make_client(tmp_path, handler)

    # 1*60=60 >= 10 → next_page None
    r = client.get("/api/library/stash/images?page=1&page_size=60")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 10
    assert body["next_page"] is None
    assert len(body["items"]) == 2

    # 1*2=2 < 10 → next_page 2
    r = client.get("/api/library/stash/images?page=1&page_size=2")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 10
    assert body["next_page"] == 2


def test_images_list_graphql_variables(tmp_path):
    """GraphQL variables carry page (1-based), per_page, q."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "data": {"findImages": {"count": 100, "images": [image_dto()]}}
        })

    client = make_client(tmp_path, handler)
    client.get("/api/library/stash/images?page=3&page_size=25&q=hello")

    v = captured["body"].get("variables", {})
    f = v.get("f", v)
    assert f["page"] == 3
    assert f["per_page"] == 25
    assert f["q"] == "hello"


# ---------------------------------------------------------------------------
# 2 – videos list: sort=random, favorite=true
# ---------------------------------------------------------------------------


def test_images_stats_and_pages(tmp_path):
    """List response carries stats and correct pagination metadata."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "data": {
                "findImages": {
                    "count": 101,
                    "megapixels": 5149.0,
                    "filesize": 3000,
                    "images": [image_dto()],
                }
            }
        })

    client = make_client(tmp_path, handler)
    r = client.get("/api/library/stash/images?page=1&page_size=20")
    assert r.status_code == 200
    body = r.json()
    assert body["pages"] == 6
    assert body["stats"] == {"megapixels": 5149.0, "size_bytes": 3000}
    assert body["page"] == 1
    assert body["page_size"] == 20


def test_images_page_clamped_to_last(tmp_path):
    """Out-of-range page is clamped; both the original and clamped page are sent to Stash."""
    pages: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        pages.append(body["variables"]["f"]["page"])
        return httpx.Response(200, json={
            "data": {
                "findImages": {
                    "count": 101,
                    "images": [image_dto()],
                }
            }
        })

    client = make_client(tmp_path, handler)
    r = client.get("/api/library/stash/images?page=99&page_size=20")
    assert r.status_code == 200
    body = r.json()
    assert body["page"] == 6
    assert body["next_page"] is None
    assert pages == [99, 6]


def test_images_page_size_capped(tmp_path):
    """page_size=200 is the Stash max; no cap below 200 applies."""
    recorded: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        recorded.append(body["variables"]["f"]["per_page"])
        return httpx.Response(200, json={
            "data": {
                "findImages": {
                    "count": 1,
                    "images": [image_dto()],
                }
            }
        })

    client = make_client(tmp_path, handler)
    r = client.get("/api/library/stash/images?page_size=200")
    assert r.status_code == 200
    assert r.json()["page_size"] == 200
    assert recorded == [200]


def test_videos_stats_size_only(tmp_path):
    """Videos list stats have megapixels None and size_bytes from filesize."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "data": {
                "findScenes": {
                    "count": 3,
                    "filesize": 777,
                    "scenes": [scene_dto()],
                }
            }
        })

    client = make_client(tmp_path, handler)
    r = client.get("/api/library/stash/videos")
    assert r.status_code == 200
    body = r.json()
    assert body["stats"] == {"megapixels": None, "size_bytes": 777}
    assert body["pages"] == 1


def test_empty_library_pages_zero_serves_page_one(tmp_path):
    """Empty library: total 0, pages 0, items empty; page clamped to 1."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "data": {
                "findImages": {
                    "count": 0,
                    "images": [],
                }
            }
        })

    client = make_client(tmp_path, handler)
    r = client.get("/api/library/stash/images?page=5")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 0
    assert body["pages"] == 0
    assert body["items"] == []
    assert body["page"] == 1


def test_videos_list_basic(tmp_path):
    """Videos list returns mapped items."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "data": {"findScenes": {"count": 1, "scenes": [scene_dto()]}}
        })

    client = make_client(tmp_path, handler)
    r = client.get("/api/library/stash/videos")
    assert r.status_code == 200
    assert r.json()["items"][0]["id"] == "2"


def test_videos_sort_random_seed(tmp_path):
    """sort=random yields a stable seed; page 2 reuses it; newest has null seed."""

    captured: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.read())
        captured.append(body)
        return httpx.Response(200, json={
            "data": {"findScenes": {"count": 2, "scenes": [scene_dto()]}}
        })

    client = make_client(tmp_path, handler)

    # Page 1, sort=random, no seed → server generates one
    r1 = client.get("/api/library/stash/videos?sort=random")
    assert r1.status_code == 200
    seed1 = r1.json()["seed"]
    assert isinstance(seed1, int)
    sort_field = captured[-1]["variables"]["f"]["sort"]
    assert sort_field == f"random_{seed1}"

    # Page 2, sort=random with same seed → same sort variable, same seed
    r2 = client.get(f"/api/library/stash/videos?sort=random&seed={seed1}&page=2")
    assert r2.status_code == 200
    assert r2.json()["seed"] == seed1
    sort_field2 = captured[-1]["variables"]["f"]["sort"]
    assert sort_field2 == f"random_{seed1}"

    # sort=newest → seed is null
    r3 = client.get("/api/library/stash/videos?sort=newest")
    assert r3.status_code == 200
    assert r3.json()["seed"] is None


def test_videos_favorite_notice(tmp_path):
    """favorite=true produces notice code option_ignored."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "data": {"findScenes": {"count": 1, "scenes": [scene_dto()]}}
        })

    client = make_client(tmp_path, handler)
    r = client.get("/api/library/stash/videos?favorite=true")
    assert r.status_code == 200
    assert r.json()["notice"]["code"] == "option_ignored"


# ---------------------------------------------------------------------------
# 3 – unreadable dto filtered out
# ---------------------------------------------------------------------------


def test_unreadable_dto_excluded(tmp_path):
    """A dto with no id is dropped; notice code items_unreadable."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "data": {
                "findImages": {
                    "count": 2,
                    "images": [image_dto("3"), {"title": "no id"}],
                }
            }
        })

    client = make_client(tmp_path, handler)
    r = client.get("/api/library/stash/images")
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["id"] == "3"
    assert body["notice"]["code"] == "items_unreadable"
    assert "unknown" in body["notice"]["message"]


# ---------------------------------------------------------------------------
# 4 – detail endpoints
# ---------------------------------------------------------------------------


def test_image_detail_ok(tmp_path):
    """Valid id → 200 with the item id."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"findImage": image_dto("42")}})

    client = make_client(tmp_path, handler)
    r = client.get("/api/library/images/42")
    assert r.status_code == 200
    assert r.json()["id"] == "42"


def test_video_detail_ok(tmp_path):
    """Valid id → 200 with the item id."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"findScene": scene_dto("42")}})

    client = make_client(tmp_path, handler)
    r = client.get("/api/library/videos/42")
    assert r.status_code == 200
    assert r.json()["id"] == "42"


def test_detail_invalid_id_no_graphql(tmp_path):
    """id 'abc' fails valid_id → 404 not_found, no GraphQL call made."""
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={"data": {"findImage": None}})

    client = make_client(tmp_path, handler)
    r = client.get("/api/library/images/abc")
    assert r.status_code == 404
    assert r.json()["code"] == "not_found"
    assert not called


def test_detail_not_found_none(tmp_path):
    """GraphQL returns null → 404 not_found."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"findImage": None}})

    client = make_client(tmp_path, handler)
    r = client.get("/api/library/images/999")
    assert r.status_code == 404
    assert r.json()["code"] == "not_found"


# ---------------------------------------------------------------------------
# 5 – DELETE not supported
# ---------------------------------------------------------------------------


def test_delete_not_supported(tmp_path):
    """DELETE on images and videos → 501 not_supported."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("should not reach upstream")

    client = make_client(tmp_path, handler)
    r = client.delete("/api/library/images/1")
    assert r.status_code == 501
    assert r.json()["code"] == "not_supported"

    r = client.delete("/api/library/videos/1")
    assert r.status_code == 501
    assert r.json()["code"] == "not_supported"


# ---------------------------------------------------------------------------
# 6 – StashError → upstream_error
# ---------------------------------------------------------------------------


def test_stash_error_upstream(tmp_path):
    """Mock returns 500 → StashError → 502 upstream_error."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal error")

    client = make_client(tmp_path, handler)
    r = client.get("/api/library/stash/images")
    assert r.status_code == 502
    assert r.json()["code"] == "upstream_error"


# ---------------------------------------------------------------------------
# 7 – ConfigError on empty stash_url
# ---------------------------------------------------------------------------


def test_empty_stash_url_answers_503(tmp_path):
    """Empty stash_url: app starts, stash routes answer 503 not_configured."""
    app = create_app(
        Settings(
            mode="real",
            real="library_stash",
            stash_url="",
            db_path=tmp_path / "p.db",
            static_dir=tmp_path / "nostatic",
            _env_file=None,  # pyright: ignore[reportCallIssue]
        )
    )
    r = TestClient(app).get("/api/library/stash/images")
    assert r.status_code == 503
    assert r.json()["code"] == "not_configured"


# ---------------------------------------------------------------------------
# 8 – secret leak
# ---------------------------------------------------------------------------


def test_no_secret_leak_list(tmp_path):
    """API key and stash URL never appear in a list response body."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "data": {"findImages": {"count": 1, "images": [image_dto()]}}
        })

    client = make_client(tmp_path, handler)
    r = client.get("/api/library/stash/images")
    assert r.status_code == 200
    body_str = r.text
    assert KEY not in body_str
    assert URL not in body_str


def test_no_secret_leak_detail(tmp_path):
    """API key and stash URL never appear in a detail response body."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"findImage": image_dto()}})

    client = make_client(tmp_path, handler)
    r = client.get("/api/library/images/1")
    assert r.status_code == 200
    data = r.json()
    assert data["stash_link"] == f"{URL}/images/1"
    data["stash_link"] = ""
    body_str = json.dumps(data)
    assert KEY not in body_str
    assert URL not in body_str


def _scene_client(tmp_path, **over):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"findScene": scene_dto("7", **over)}})

    return make_client(tmp_path, handler)


def test_video_detail_fallback_streams(tmp_path):
    streams = [
        {
            "url": f"{URL}/scene/7/stream.mp4?apikey={KEY}&resolution=ORIGINAL",
            "mime_type": "video/mp4",
            "label": "Direct stream",
        },
        {
            "url": f"{URL}/scene/7/stream.m3u8?apikey={KEY}",
            "mime_type": "application/vnd.apple.mpegurl",
            "label": "HLS",
        },
        {"url": f"{URL}/scene/7/evil.exe", "mime_type": "x", "label": "bad"},
    ]
    r = _scene_client(tmp_path, sceneStreams=streams).get("/api/library/videos/7")
    assert r.status_code == 200
    data = r.json()
    assert [s["url"] for s in data["fallback_streams"]] == [
        "/api/media/stash/videos/7/s/stream.mp4?resolution=ORIGINAL",
        "/api/media/stash/videos/7/s/stream.m3u8",
    ]
    assert [s["label"] for s in data["fallback_streams"]] == ["Direct stream", "HLS"]
    assert data["stash_link"] == f"{URL}/scenes/7"
    data["stash_link"] = ""
    body_str = json.dumps(data)
    assert KEY not in body_str
    assert URL not in body_str
    assert "apikey" not in body_str


def test_video_detail_public_url(tmp_path):
    client = _scene_client(tmp_path)
    app: Any = client.app
    app.state.settings.stash_public_url = "https://pub.example/"
    r = client.get("/api/library/videos/7")
    assert r.json()["stash_link"] == "https://pub.example/scenes/7"


def test_video_detail_no_streams(tmp_path):
    r = _scene_client(tmp_path).get("/api/library/videos/7")
    assert r.json()["fallback_streams"] == []


def test_detail_path_matches_frontend_client(tmp_path):
    """The item view calls /api/library/<kind>/<id>; the old /stash/ prefix is not routed."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"findImage": image_dto("42")}})

    client = make_client(tmp_path, handler)
    assert client.get("/api/library/images/42").status_code == 200
    assert client.get("/api/library/stash/images/42").status_code == 404
