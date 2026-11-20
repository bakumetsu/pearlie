"""Host allowlist on /api (DNS rebinding defence)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def _client(tmp_path: Path, allowed: str = "") -> TestClient:
    settings = Settings(
        mode="fixture",
        db_path=tmp_path / "p.db",
        static_dir=tmp_path / "nostatic",
        allowed_hosts=allowed,
        _env_file=None,  # pyright: ignore[reportCallIssue]
    )
    return TestClient(create_app(settings))


def test_rebinding_name_is_refused_even_with_matching_origin(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    tc = _client(tmp_path)
    host = "rebind.evil.example:8000"
    with caplog.at_level("WARNING", logger="app.api.guard"):
        get = tc.get("/api/logs/settings", headers={"Host": host})
        put = tc.put(
            "/api/logs/settings",
            json={},
            headers={"Host": host, "Origin": f"http://{host}"},
        )
    for resp in (get, put):
        assert resp.status_code == 403
        assert resp.json() == {
            "code": "host_not_allowed",
            "message": "host not allowed: add rebind.evil.example to PEARLIE_ALLOWED_HOSTS",
        }
    assert "rebind.evil.example" in caplog.text


def test_unprintable_host_is_not_echoed(tmp_path: Path) -> None:
    resp = _client(tmp_path).get("/api/logs/settings", headers={"X-Forwarded-Host": "a<b>.example"})
    assert resp.status_code == 403
    assert resp.json()["message"] == "host not allowed: add this host to PEARLIE_ALLOWED_HOSTS"


@pytest.mark.parametrize(
    "host",
    ["127.0.0.1:8000", "10.1.2.3", "[::1]:8000", "localhost:5173", "box.tail1234.ts.net"],
)
def test_ip_localhost_and_tailnet_hosts_pass(tmp_path: Path, host: str) -> None:
    resp = _client(tmp_path).get("/api/logs/settings", headers={"Host": host})
    assert resp.status_code != 403, resp.text


def test_listed_name_passes_and_is_case_insensitive(tmp_path: Path) -> None:
    tc = _client(tmp_path, allowed=" pearlie.home , Other.lan")
    assert tc.get("/api/logs/settings", headers={"Host": "pearlie.home"}).status_code != 403
    assert tc.get("/api/logs/settings", headers={"Host": "OTHER.lan:443"}).status_code != 403
    assert tc.get("/api/logs/settings", headers={"Host": "x.pearlie.home"}).status_code == 403


def test_forwarded_host_is_checked(tmp_path: Path) -> None:
    tc = _client(tmp_path)
    resp = tc.get("/api/logs/settings", headers={"X-Forwarded-Host": "evil.example"})
    assert resp.status_code == 403


def _static_client(tmp_path: Path) -> TestClient:
    static = tmp_path / "dist"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<html>ok</html>")
    (static / "assets" / "a.js").write_text("1")
    settings = Settings(
        mode="fixture",
        db_path=tmp_path / "p.db",
        static_dir=static,
        _env_file=None,  # pyright: ignore[reportCallIssue]
    )
    return TestClient(create_app(settings))


@pytest.mark.parametrize("path", ["/", "/library/some/spa/route", "/assets/a.js"])
def test_web_ui_paths_refuse_unlisted_host_with_html_page(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, path: str
) -> None:
    tc = _static_client(tmp_path)
    with caplog.at_level("WARNING", logger="app.api.guard"):
        resp = tc.get(path, headers={"Host": "evil<b>.example"})
    assert resp.status_code == 403
    assert resp.headers["content-type"].startswith("text/html")
    assert "PEARLIE_ALLOWED_HOSTS" in resp.text
    assert "evil&lt;b&gt;.example" in resp.text
    assert "<b>" not in resp.text
    assert "evil" in caplog.text


def test_web_ui_passes_for_allowed_host(tmp_path: Path) -> None:
    tc = _static_client(tmp_path)
    assert tc.get("/", headers={"Host": "localhost:8000"}).status_code == 200
    assert tc.get("/assets/a.js", headers={"Host": "10.0.0.5"}).status_code == 200


def test_long_host_is_truncated_in_page(tmp_path: Path) -> None:
    resp = _static_client(tmp_path).get("/", headers={"Host": "a" * 300 + ".example"})
    assert resp.status_code == 403
    assert "a" * 101 not in resp.text


def test_warning_is_logged_once_per_host(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    tc = _client(tmp_path)
    with caplog.at_level("WARNING", logger="app.api.guard"):
        for _ in range(3):
            tc.get("/api/logs/settings", headers={"Host": "once.example"})
        tc.get("/", headers={"Host": "other.example"})
    assert caplog.text.count("once.example") == 1
    assert caplog.text.count("other.example") == 1
