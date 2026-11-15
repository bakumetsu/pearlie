"""Edge cases of the generated secret.key file (corrupt, wrong size, empty, loose mode)."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

pytestmark = pytest.mark.no_default_origin


def make_client(tmp_path: Path) -> TestClient:
    settings = Settings(
        mode="real",
        real="search",
        db_path=tmp_path / "p.db",
        static_dir=tmp_path / "nostatic",
        _env_file=None,  # pyright: ignore[reportCallIssue]
    )
    return TestClient(create_app(settings), base_url="http://localhost")


def test_non_utf8_key_file_does_not_crash(tmp_path: Path) -> None:
    (tmp_path / "secret.key").write_bytes(b"\xff\xfe\x00\x80garbage")
    r = make_client(tmp_path).get("/api/connections")
    assert r.status_code == 200
    assert r.json()["can_store"] is False
    assert (tmp_path / "secret.key").read_bytes() == b"\xff\xfe\x00\x80garbage"


def test_wrong_size_key_file_is_refused_and_kept(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    bad = "short-key-not-fernet"
    (tmp_path / "secret.key").write_text(bad, encoding="utf-8")
    with caplog.at_level(logging.DEBUG):
        c = make_client(tmp_path)
        r = c.get("/api/connections")
        put = c.put(
            "/api/connections/stash",
            json={"address": "http://stash.local:9999", "secret": "s3cret"},
            headers={"Origin": "http://localhost", "Content-Type": "application/json"},
        )
    assert r.json()["can_store"] is False
    assert put.status_code == 409
    assert (tmp_path / "secret.key").read_text(encoding="utf-8") == bad
    assert bad not in caplog.text


def test_empty_key_file_is_regenerated(tmp_path: Path) -> None:
    (tmp_path / "secret.key").write_text("", encoding="utf-8")
    r = make_client(tmp_path).get("/api/connections")
    assert r.json()["can_store"] is True
    Fernet((tmp_path / "secret.key").read_text(encoding="utf-8").strip())


@pytest.mark.skipif(os.name != "posix", reason="file modes")
def test_loose_key_file_mode_is_tightened(tmp_path: Path) -> None:
    path = tmp_path / "secret.key"
    path.write_text(Fernet.generate_key().decode(), encoding="utf-8")
    path.chmod(0o644)
    assert make_client(tmp_path).get("/api/connections").json()["can_store"] is True
    assert path.stat().st_mode & 0o077 == 0
