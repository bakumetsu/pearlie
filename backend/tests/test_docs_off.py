"""/docs, /redoc and /openapi.json exist only in fixture mode."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

DOC_PATHS = ("/docs", "/redoc", "/openapi.json")


def _client(tmp_path: Path, mode: str) -> TestClient:
    settings = Settings(
        mode=mode,  # pyright: ignore[reportArgumentType]
        db_path=tmp_path / "p.db",
        static_dir=tmp_path / "nostatic",
        _env_file=None,  # pyright: ignore[reportCallIssue]
    )
    return TestClient(create_app(settings))


@pytest.mark.parametrize("path", DOC_PATHS)
def test_docs_served_in_fixture_mode(tmp_path: Path, path: str) -> None:
    assert _client(tmp_path, "fixture").get(path).status_code == 200


@pytest.mark.parametrize("path", DOC_PATHS)
def test_docs_off_in_real_mode(tmp_path: Path, path: str) -> None:
    assert _client(tmp_path, "real").get(path).status_code == 404
