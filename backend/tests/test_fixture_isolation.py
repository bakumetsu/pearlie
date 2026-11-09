# T-44: fixture mode ignores PEARLIE_REAL and never mounts real routers
import logging

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def _app(tmp_path):
    return create_app(
        Settings(
            mode="fixture",
            real="search,library_komga,media_komga,library_stash,media_stash",
            komga_url="http://real-komga.invalid",
            komga_api_key="SECRET-KOMGA-KEY",
            stash_url="http://real-stash.invalid",
            stash_api_key="SECRET-STASH-KEY",
            db_path=tmp_path / "p.db",
            static_dir=tmp_path / "nostatic",
            _env_file=None,  # pyright: ignore[reportCallIssue]
        )
    )


def test_fixture_mode_ignores_real(tmp_path):
    app = _app(tmp_path)
    assert app.state.komga is None


def test_fixture_mode_serves_fixture_library_and_media(tmp_path):
    app = _app(tmp_path)
    client = TestClient(app)

    r = client.get("/api/library/komga/books")
    assert r.status_code == 200
    book_id = r.json()["items"][0]["id"]

    r = client.get(f"/api/media/komga/books/{book_id}/pages/1/thumb")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"

    r = client.get("/api/library/stash/images")
    assert r.status_code == 200
    assert r.json()["items"]

    r = client.get("/api/search")
    assert r.status_code == 200


def test_fixture_mode_logs_ignored_real(tmp_path, caplog):
    with caplog.at_level(logging.WARNING, logger="pearlie"):
        _app(tmp_path)

    ignored = [rec for rec in caplog.records if "PEARLIE_REAL ignored" in rec.message]
    assert any(
        "library_komga" in rec.message and "media_stash" in rec.message
        for rec in ignored
    )
    for rec in caplog.records:
        msg = rec.getMessage()
        assert "SECRET" not in msg
        assert "invalid" not in msg


def test_fixture_mode_without_real_logs_nothing(tmp_path, caplog):
    with caplog.at_level(logging.WARNING, logger="pearlie"):
        create_app(
            Settings(
                mode="fixture",
                real="",
                db_path=tmp_path / "p.db",
                static_dir=tmp_path / "nostatic",
                _env_file=None,  # pyright: ignore[reportCallIssue]
            )
        )

    assert not any("PEARLIE_REAL ignored" in rec.getMessage() for rec in caplog.records)
