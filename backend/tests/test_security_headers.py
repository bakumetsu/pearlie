"""Security headers on responses; relayed SVG cannot run script."""

from __future__ import annotations

from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'


def _client(tmp_path: Path, **kw) -> TestClient:
    settings = Settings(
        mode="fixture",
        db_path=tmp_path / "p.db",
        static_dir=kw.pop("static_dir", tmp_path / "nostatic"),
        _env_file=None,  # pyright: ignore[reportCallIssue]
    )
    return TestClient(create_app(settings))


def test_api_response_has_sandbox_csp_and_nosniff(tmp_path: Path) -> None:
    r = _client(tmp_path).get("/api/health")
    csp = r.headers["content-security-policy"]
    assert "sandbox" in csp and "default-src 'none'" in csp
    assert r.headers["x-content-type-options"] == "nosniff"


def test_relayed_svg_is_sandboxed(tmp_path: Path) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=SVG, headers={"content-type": "image/svg+xml"})

    app = create_app(
        Settings(
            mode="real",
            real="search",
            db_path=tmp_path / "p.db",
            static_dir=tmp_path / "nostatic",
            _env_file=None,  # pyright: ignore[reportCallIssue]
        )
    )
    app.state.site_icon_client = httpx.Client(transport=httpx.MockTransport(handler))
    r = TestClient(app).get("/api/site-icons/gelbooru")
    assert "sandbox" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"


def _static(tmp_path: Path) -> TestClient:
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<!doctype html><div id=app></div>")
    (static / "assets" / "app-abc123.js").write_text("console.log(1)")
    return _client(tmp_path, static_dir=static)


def test_app_pages_get_full_security_headers(tmp_path: Path) -> None:
    r = _static(tmp_path).get("/")
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "no-referrer"
    csp = r.headers["content-security-policy"]
    assert "script-src 'self'" in csp and "frame-ancestors 'none'" in csp
    assert "unsafe-eval" not in csp
    # the build needs inline styles, images, blobs: none of that may be blocked
    assert "style-src 'self' 'unsafe-inline'" in csp and "img-src 'self' data: blob:" in csp


def test_cache_control_assets_immutable_index_revalidated(tmp_path: Path) -> None:
    c = _static(tmp_path)
    assert c.get("/").headers["cache-control"] == "no-cache"
    r = c.get("/assets/app-abc123.js")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "public, max-age=31536000, immutable"
    # API responses keep the cache policy their route sets
    assert c.get("/api/health").headers.get("cache-control") != "no-cache"
