"""Tests for the real-mode Stash media proxy endpoints."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.targets.stash_client import StashClient

KEY = "s-secret-456"
URL = "http://stash.test"


class _Body(httpx.SyncByteStream):
    """A real stream, so the response is not pre-read like mock content."""

    def __init__(self, data: bytes) -> None:
        self._data = data

    def __iter__(self):
        yield self._data


def stream_response(status: int, body: bytes, headers: dict[str, str]) -> httpx.Response:
    """Build a streamed mock response the way a live Stash answers."""
    return httpx.Response(status, headers=headers, stream=_Body(body))


def make_client(
    tmp_path: Path, handler: Callable[[httpx.Request], httpx.Response]
) -> TestClient:
    """Build a TestClient with a mock-backed Stash client."""
    app = create_app(
        Settings(
            mode="real",
            real="media_stash",
            stash_url=URL,
            db_path=tmp_path / "p.db",
            static_dir=tmp_path / "nostatic",
            _env_file=None,  # pyright: ignore[reportCallIssue]
        )
    )
    app.state.stash = StashClient(
        URL,
        KEY,
        client=httpx.Client(
            base_url=URL, headers={"ApiKey": KEY}, transport=httpx.MockTransport(handler)
        ),
    )
    return TestClient(app)


# --- 1. thumb/full/poster map to correct upstream; body & Content-Type relayed ---


def test_media_paths_and_relay(tmp_path: Path) -> None:
    recorded: list[tuple[str, dict[str, str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        recorded.append((str(request.url), dict(request.headers)))
        return stream_response(200, b"pixels", {"Content-Type": "image/png"})

    client = make_client(tmp_path, handler)

    # /stash/images/1/thumb → /image/1/thumbnail
    r = client.get("/api/media/stash/images/1/thumb")
    assert r.status_code == 200
    assert r.content == b"pixels"
    assert r.headers["content-type"] == "image/png"
    assert r.headers["cache-control"] == "private, max-age=3600"
    assert recorded[-1][0] == f"{URL}/image/1/thumbnail"

    # /stash/images/42/full → /image/42/image
    r = client.get("/api/media/stash/images/42/full")
    assert r.status_code == 200
    assert r.content == b"pixels"
    assert r.headers["content-type"] == "image/png"
    assert r.headers["cache-control"] == "private, max-age=3600"
    assert recorded[-1][0] == f"{URL}/image/42/image"

    # /stash/videos/7/poster → /scene/7/screenshot
    r = client.get("/api/media/stash/videos/7/poster")
    assert r.status_code == 200
    assert r.content == b"pixels"
    assert r.headers["content-type"] == "image/png"
    assert r.headers["cache-control"] == "private, max-age=3600"
    assert recorded[-1][0] == f"{URL}/scene/7/screenshot"


# --- 2. ApiKey header sent; no apikey in query; KEY & URL never leaked ---


def test_apikey_header_and_no_leak(tmp_path: Path) -> None:
    recorded: list[tuple[str, dict[str, str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        recorded.append((str(request.url), dict(request.headers)))
        return stream_response(200, b"ok", {"Content-Type": "image/jpeg"})

    client = make_client(tmp_path, handler)

    r = client.get("/api/media/stash/images/1/thumb")
    assert r.status_code == 200

    url, headers = recorded[-1]
    # Upstream request carries ApiKey header
    assert headers.get("apikey") == KEY
    # No apikey parameter anywhere in the upstream URL
    assert "apikey=" not in url.lower()

    # Client-facing response must not contain KEY or the stash URL
    body = r.content.decode()
    assert KEY not in body
    assert URL not in body
    for v in r.headers.values():
        assert KEY not in v
        assert URL not in v


# --- 3. Invalid id → 404 not_found, no upstream request ---


@pytest.mark.parametrize("bad_id", ["abc", "1x"])
def test_invalid_id_404(tmp_path: Path, bad_id: str) -> None:
    recorded: list[tuple[str, dict[str, str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        recorded.append((str(request.url), dict(request.headers)))
        return httpx.Response(200, content=b"unreachable", headers={"Content-Type": "image/jpeg"})

    client = make_client(tmp_path, handler)

    r = client.get(f"/api/media/stash/images/{bad_id}/thumb")
    assert r.status_code == 404
    assert r.json()["code"] == "not_found"
    assert recorded == []


# --- 5. Upstream status mapping: 404→404, 500→502, 401→502 ---


@pytest.mark.parametrize(
    ("upstream_status", "expected_status"),
    [(404, 404), (500, 502), (401, 502)],
)
def test_upstream_error_mapping(
    tmp_path: Path, upstream_status: int, expected_status: int
) -> None:
    recorded: list[tuple[str, dict[str, str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        recorded.append((str(request.url), dict(request.headers)))
        return httpx.Response(
            upstream_status, content=b"err", headers={"Content-Type": "text/plain"}
        )

    client = make_client(tmp_path, handler)

    r = client.get("/api/media/stash/images/1/thumb")
    assert r.status_code == expected_status

# --- 4. Range header relay + Cookie stripped ---


def test_range_cookie(tmp_path: Path) -> None:
    calls: list[tuple[str, dict[str, str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((str(request.url), dict(request.headers)))
        if request.headers.get("range") == "bytes=999-":
            return stream_response(416, b"", {})
        return stream_response(
            206, b"0123456789", {"Content-Range": "bytes 0-9/100"}
        )

    client = make_client(tmp_path, handler)

    r = client.get(
        "/api/media/stash/videos/5/stream",
        headers={"Range": "bytes=0-9", "Cookie": "x=1"},
    )
    assert r.status_code == 206
    assert r.headers.get("content-range") == "bytes 0-9/100"
    assert calls[0][1].get("range") == "bytes=0-9"
    assert "cookie" not in calls[0][1]

    r = client.get(
        "/api/media/stash/videos/5/stream",
        headers={"Range": "bytes=999-"},
    )
    assert r.status_code == 416


# --- 6. Segment name allowlist ---


@pytest.mark.parametrize(
    ("segment", "expected"),
    [
        ("stream.m3u8", 200),
        ("0.ts", 200),
        ("12.ts", 200),
        ("evil.ts", 404),
        ("stream.exe", 404),
        ("a.ts", 404),
        ("x.m3u8", 404),
    ],
)
def test_segment_names(tmp_path: Path, segment: str, expected: int) -> None:
    calls: list[tuple[str, dict[str, str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((str(request.url), dict(request.headers)))
        return stream_response(200, b"seg", {})

    client = make_client(tmp_path, handler)
    r = client.get(f"/api/media/stash/videos/5/s/{segment}")
    assert r.status_code == expected
    if expected == 404:
        assert not calls


# --- 7. Query param filtering on segment requests ---


def test_segment_query_filtering(tmp_path: Path) -> None:
    calls: list[tuple[str, dict[str, str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((str(request.url), dict(request.headers)))
        return stream_response(200, b"seg", {})

    client = make_client(tmp_path, handler)

    r = client.get(
        "/api/media/stash/videos/5/s/0.ts",
        params={"resolution": "ORIGINAL", "apikey": "abc", "foo": "1"},
    )
    assert r.status_code == 200
    assert dict(httpx.URL(calls[0][0]).params) == {"resolution": "ORIGINAL"}

    calls.clear()
    r = client.get(
        "/api/media/stash/videos/5/s/0.ts",
        params={"resolution": "bad value!"},
    )
    assert r.status_code == 200
    assert len(httpx.URL(calls[0][0]).params) == 0


# --- 8. HLS m3u8 rewrite ---

_M3U8_UPSTREAM = (
    "#EXTM3U\n"
    "#EXT-X-VERSION:3\n"
    "#EXTINF:2.0,\n"
    "0.ts?resolution=ORIGINAL\n"
    "#EXTINF:2.0,\n"
    "http://stash.test/scene/5/12.ts?apikey=zzz&resolution=ORIGINAL\n"
    "#EXTINF:2.0,\n"
    "/scene/5/13.ts?apikey=zzz\n"
    '#EXT-X-MAP:URI="http://stash.test/scene/5/init.mp4?apikey=zzz"\n'
)


def test_hls_rewrite(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return stream_response(
            200,
            _M3U8_UPSTREAM.encode(),
            {"Content-Type": "application/vnd.apple.mpegurl"},
        )

    client = make_client(tmp_path, handler)
    r = client.get("/api/media/stash/videos/5/s/stream.m3u8")
    assert r.status_code == 200
    assert (
        r.headers.get("content-type") == "application/vnd.apple.mpegurl"
    )
    text = r.text
    assert "apikey" not in text
    assert "stash.test" not in text
    assert "http://" not in text
    lines = text.splitlines()
    assert "0.ts?resolution=ORIGINAL" in lines
    assert "12.ts?resolution=ORIGINAL" in lines
    assert "13.ts" in lines


def test_rewrite_m3u8_comments() -> None:
    from app.api.media_stash_real import rewrite_m3u8

    src = "#EXTM3U\n#EXT-X-VERSION:3\n#EXTINF:2.0,\n0.ts\n"
    assert rewrite_m3u8(src).splitlines() == src.splitlines()
