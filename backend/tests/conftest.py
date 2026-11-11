from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        mode="fixture",
        db_path=tmp_path / "p.db",
        static_dir=tmp_path / "nostatic",
        _env_file=None,  # pyright: ignore[reportCallIssue]
    )


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


@pytest.fixture(autouse=True)
def _same_origin_header(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Mutating /api routes require Origin; browsers always send it."""
    if request.node.get_closest_marker("no_default_origin"):
        return
    original_init = TestClient.__init__

    def _patched_init(self: TestClient, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        self.headers.setdefault("Origin", str(self.base_url).rstrip("/"))

    monkeypatch.setattr(TestClient, "__init__", _patched_init)
