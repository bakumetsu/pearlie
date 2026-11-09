# Tests for the Stash scene preview proxy and the video-card fields (T-36)
from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.targets import stash_library
from tests.test_media_stash_real import KEY, URL, make_client, stream_response
from tests.test_stash_library import scene_dto


def test_preview_ranged_request_returns_206(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> Any:
        seen.append(request)
        return stream_response(
            206,
            b"abc",
            {
                "Content-Type": "video/mp4",
                "Content-Range": "bytes 0-2/10",
                "Accept-Ranges": "bytes",
            },
        )

    client = make_client(tmp_path, handler)
    r = client.get("/api/media/stash/scene/7/preview", headers={"Range": "bytes=0-2"})

    assert r.status_code == 206
    assert r.content == b"abc"
    assert r.headers["content-range"] == "bytes 0-2/10"
    assert r.headers["accept-ranges"] == "bytes"
    assert str(seen[0].url) == f"{URL}/scene/7/preview"
    assert seen[0].headers["range"] == "bytes=0-2"


def test_preview_full_request_returns_200(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> Any:
        seen.append(request)
        return stream_response(
            200,
            b"0123456789",
            {
                "Content-Type": "video/mp4",
                "Accept-Ranges": "bytes",
            },
        )

    client = make_client(tmp_path, handler)
    r = client.get("/api/media/stash/scene/7/preview")

    assert r.status_code == 200
    assert r.content == b"0123456789"
    assert "range" not in seen[0].headers


def test_preview_never_leaks_key(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> Any:
        seen.append(request)
        return stream_response(200, b"payload", {"Content-Type": "video/mp4"})

    client = make_client(tmp_path, handler)

    # ranged request
    r = client.get("/api/media/stash/scene/7/preview", headers={"Range": "bytes=0-2"})
    assert KEY not in r.text
    assert KEY not in str(r.headers)
    assert "apikey" not in str(seen[0].url).lower()
    assert seen[0].headers["apikey"] == KEY
    assert URL not in str(r.headers)

    # full request
    r = client.get("/api/media/stash/scene/7/preview")
    assert KEY not in r.text
    assert KEY not in str(r.headers)
    assert "apikey" not in str(seen[1].url).lower()
    assert seen[1].headers["apikey"] == KEY
    assert URL not in str(r.headers)


def test_preview_bad_id_is_404(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> Any:
        seen.append(request)
        return stream_response(200, b"", {"Content-Type": "video/mp4"})

    client = make_client(tmp_path, handler)
    r = client.get("/api/media/stash/scene/x!/preview")

    assert r.status_code == 404
    assert seen == []


def test_video_item_maps_card_fields() -> None:
    dto = scene_dto(
        "5",
        date="2026-03-04",
        studio={"name": "Studio X"},
        files=[{
            "basename": "a.mp4",
            "width": 1920,
            "height": 1080,
            "duration": 12.5,
            "video_codec": "h264",
            "size": 777,
        }],
    )
    item = stash_library.video_item(dto)

    assert item.preview_url == "/api/media/stash/scene/5/preview"
    assert item.studio == "Studio X"
    assert item.date == "2026-03-04"
    assert item.size_bytes == 777

    # no studio, no date
    dto_bare = scene_dto("5")
    item_bare = stash_library.video_item(dto_bare)
    assert item_bare.studio is None
    assert item_bare.date is None

    # video_detail gets the same preview_url
    detail = stash_library.video_detail(dto)
    assert detail.preview_url == "/api/media/stash/scene/5/preview"


def test_fixture_preview_serves_range(client: TestClient) -> None:
    r = client.get("/api/media/stash/scene/1/preview", headers={"Range": "bytes=0-9"})
    if r.status_code == 404:
        pytest.skip("ffmpeg unavailable; fixture media not generated")
    assert r.status_code == 206
    assert r.headers["content-range"].startswith("bytes 0-9/")
    assert len(r.content) == 10

    r_full = client.get("/api/media/stash/scene/1/preview")
    if r_full.status_code == 404:
        pytest.skip("ffmpeg unavailable; fixture media not generated")
    assert r_full.status_code == 200


def test_fixture_items_carry_card_fields(client: TestClient) -> None:
    r = client.get("/api/library/stash/videos", params={"page_size": 5})
    items = r.json()["items"]
    first = items[0]
    assert first["preview_url"].startswith("/api/media/stash/scene/")
    assert first["studio"] is not None
    assert first["date"] is not None


def test_preview_upstream_404_is_404(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> Any:
        return stream_response(404, b"", {"Content-Type": "text/plain"})

    client = make_client(tmp_path, handler)
    r = client.get("/api/media/stash/scene/7/preview")

    assert r.status_code == 404
