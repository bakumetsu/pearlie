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
