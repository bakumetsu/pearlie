"""Site icon fetch/cache and the hidden-sites option."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import site_icons
from app.config import Settings
from app.main import create_app

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 40


def real_client(tmp_path, handler):
    seen: list[httpx.Request] = []

    def wrapped(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return handler(req)

    app = create_app(
        Settings(
            mode="real",
            real="search",
            db_path=tmp_path / "p.db",
            static_dir=tmp_path / "nostatic",
            _env_file=None,  # pyright: ignore[reportCallIssue]
        )
    )
    app.state.site_icon_client = httpx.Client(transport=httpx.MockTransport(wrapped))
    return TestClient(app), seen


def ok(_req: httpx.Request) -> httpx.Response:
    return httpx.Response(200, content=PNG, headers={"content-type": "image/png"})


def test_success_cached(tmp_path):
    c, seen = real_client(tmp_path, ok)
    r = c.get("/api/site-icons/gelbooru")
    assert r.status_code == 200
    assert r.content == PNG
    assert r.headers["content-type"] == "image/png"
    assert c.get("/api/site-icons/gelbooru").content == PNG
    assert len(seen) == 1


def test_only_configured_host_and_no_cookie(tmp_path):
    c, seen = real_client(tmp_path, ok)
    c.get("/api/site-icons/nhentai", headers={"Cookie": "sid=secret"})
    assert [r.url.host for r in seen] == ["nhentai.net"]
    assert str(seen[0].url) == "https://nhentai.net/favicon.ico"
    assert "cookie" not in seen[0].headers
    assert "authorization" not in seen[0].headers


def test_404_is_cached_as_miss(tmp_path):
    c, seen = real_client(tmp_path, lambda _r: httpx.Response(404))
    assert c.get("/api/site-icons/danbooru").status_code == 404
    assert c.get("/api/site-icons/danbooru").status_code == 404
    assert len(seen) == 1


def test_non_image_rejected(tmp_path):
    c, _ = real_client(
        tmp_path,
        lambda _r: httpx.Response(200, content=b"<html>", headers={"content-type": "text/html"}),
    )
    assert c.get("/api/site-icons/danbooru").status_code == 404


def test_oversized_rejected(tmp_path):
    big = b"0" * (site_icons.MAX_ICON_BYTES + 1)
    c, _ = real_client(
        tmp_path,
        lambda _r: httpx.Response(200, content=big, headers={"content-type": "image/png"}),
    )
    assert c.get("/api/site-icons/danbooru").status_code == 404


def test_redirect_not_followed(tmp_path):
    c, seen = real_client(
        tmp_path,
        lambda _r: httpx.Response(302, headers={"location": "https://evil.example/x.png"}),
    )
    assert c.get("/api/site-icons/danbooru").status_code == 404
    assert [r.url.host for r in seen] == ["danbooru.donmai.us"]


def test_unknown_site(client: TestClient):
    assert client.get("/api/site-icons/nope").status_code == 422


def test_fixture_mode_no_icon(client: TestClient):
    assert client.get("/api/site-icons/danbooru").status_code == 404


@pytest.mark.parametrize("mode", ["fixture", "real"])
def test_hidden_sites(mode, client, tmp_path):
    c = client if mode == "fixture" else real_client(tmp_path, ok)[0]
    assert c.get("/api/options").json()["hidden_sites"] == []
    r = c.put("/api/options", json={"hidden_sites": ["rule34", "gelbooru"]})
    assert r.status_code == 200
    assert r.json()["hidden_sites"] == ["gelbooru", "rule34"]
    assert c.get("/api/options").json()["hidden_sites"] == ["gelbooru", "rule34"]
    assert c.put("/api/options", json={"hidden_sites": ["bogus"]}).status_code == 422
    assert c.put("/api/options", json={"hidden_sites": []}).json()["hidden_sites"] == []
