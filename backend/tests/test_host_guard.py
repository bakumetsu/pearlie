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


def test_static_files_are_not_host_checked(tmp_path: Path) -> None:
    static = tmp_path / "dist"
    static.mkdir()
    (static / "index.html").write_text("<html>ok</html>")
    settings = Settings(
        mode="fixture",
        db_path=tmp_path / "p.db",
        static_dir=static,
        _env_file=None,  # pyright: ignore[reportCallIssue]
    )
    resp = TestClient(create_app(settings)).get("/", headers={"Host": "evil.example"})
    assert resp.status_code == 200
