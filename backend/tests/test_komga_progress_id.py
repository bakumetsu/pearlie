"""Tests for the Komga progress route id check (404 on bad id, no upstream call)."""

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.komga import Komga
from app.main import create_app

URL = "http://komga.local"

BAD_IDS = ["1%3F", "..", "%2e%2e", "a%2Fb", "x" * 65]


def make_client(tmp_path, handler):
    app = create_app(
        Settings(
            mode="real",
            real="library_komga",
            komga_url=URL,
            db_path=tmp_path / "p.db",
            static_dir=tmp_path / "nostatic",
            _env_file=None,  # pyright: ignore[reportCallIssue]
        )
    )
    app.state.komga = Komga(
        URL, "k", client=httpx.Client(base_url=URL, transport=httpx.MockTransport(handler))
    )
    return TestClient(app)


@pytest.mark.parametrize("bad_id", BAD_IDS, ids=BAD_IDS)
def test_progress_bad_id_404_no_upstream(bad_id, tmp_path):
    calls: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={})

    client = make_client(tmp_path, handler)
    r = client.post(f"/api/library/komga/books/{bad_id}/progress", json={"page": 1})
    assert r.status_code == 404
    assert r.json()["code"] == "not_found"
    assert calls == []
