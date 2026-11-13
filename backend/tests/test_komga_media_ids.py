"""Tests for /api/media/komga route id validation (404 on bad id, no upstream call)."""

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.komga import Komga
from app.main import create_app

URL = "http://komga.local"
KEY = "k-secret-123"


def make_client(tmp_path, handler):
    """Build a TestClient wired to a mock Komga transport."""
    app = create_app(
        Settings(
            mode="real",
            real="library_komga,media_komga",
            komga_url=URL,
            db_path=tmp_path / "p.db",
            static_dir=tmp_path / "nostatic",
            _env_file=None,
        )
    )  # pyright: ignore[reportCallIssue]
    app.state.komga = Komga(
        URL, KEY, client=httpx.Client(base_url=URL, transport=httpx.MockTransport(handler))
    )
    return TestClient(app)


ROUTES = [
    ("/api/media/komga/series/{id}/thumb", "/api/v1/series/{id}/thumbnail"),
    ("/api/media/komga/books/{id}/thumb", "/api/v1/books/{id}/thumbnail"),
    ("/api/media/komga/books/{id}/pages/1", "/api/v1/books/{id}/pages/1"),
    ("/api/media/komga/books/{id}/pages/1/thumb", "/api/v1/books/{id}/pages/1/thumbnail"),
]

BAD_IDS = ["1%3F", "..", "%2e%2e", "a%2Fb", "x" * 65]


def _handler(calls):
    def h(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, content=b"img", headers={"content-type": "image/jpeg"})

    return h


@pytest.mark.parametrize("route,upstream", ROUTES, ids=[r[0] for r in ROUTES])
@pytest.mark.parametrize("bad_id", BAD_IDS, ids=BAD_IDS)
def test_bad_id_404_no_upstream(route, upstream, bad_id, tmp_path):
    """Bad id returns 404 not_found before any upstream request."""
    calls: list = []
    client = make_client(tmp_path, _handler(calls))
    r = client.get(route.format(id=bad_id))
    assert r.status_code == 404
    assert r.json()["code"] == "not_found"
    assert calls == []


def test_empty_id_404_no_upstream(tmp_path):
    """Empty id segment yields 404 with no upstream call."""
    calls: list = []
    client = make_client(tmp_path, _handler(calls))
    r = client.get("/api/media/komga/books//thumb")
    assert r.status_code == 404
    assert calls == []


@pytest.mark.parametrize("route,upstream", ROUTES, ids=[r[0] for r in ROUTES])
def test_valid_id_200_upstream_called_once(route, upstream, tmp_path):
    """Valid id 'b1' returns 200 and the upstream path is correct."""
    calls: list = []
    client = make_client(tmp_path, _handler(calls))
    r = client.get(route.format(id="b1"))
    assert r.status_code == 200
    assert len(calls) == 1
    assert calls[0].url.path == upstream.format(id="b1")
