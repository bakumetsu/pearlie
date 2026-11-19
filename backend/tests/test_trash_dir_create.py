"""The trash folder is created at start and again before a move; failures stay 503."""

import logging
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import init_db
from app.library.trash import TrashError, TrashStore
from app.main import create_app


def real_app(tmp_path: Path, trash: Path):
    return create_app(
        Settings(
            mode="real", real="library_stash", stash_url="http://stash.test",
            db_path=tmp_path / "p.db", static_dir=tmp_path / "nostatic",
            trash_dir=trash, _env_file=None,  # pyright: ignore[reportCallIssue]
        )
    )


def test_start_creates_missing_trash_dir(tmp_path):
    trash = tmp_path / "deep" / "trash"
    with TestClient(real_app(tmp_path, trash)):
        pass
    assert trash.is_dir()


def test_start_warns_when_trash_dir_cannot_be_created(tmp_path, monkeypatch, caplog):
    trash = tmp_path / "ro" / "trash"
    real_mkdir = Path.mkdir

    def deny(self, *a, **kw):
        if self == trash:
            raise PermissionError(13, "denied")
        return real_mkdir(self, *a, **kw)

    monkeypatch.setattr(Path, "mkdir", deny)
    with caplog.at_level(logging.WARNING):
        client = TestClient(real_app(tmp_path, trash))
    assert any(str(trash) in r.getMessage() and "PermissionError" in r.getMessage()
               for r in caplog.records)
    assert not trash.exists()
    with pytest.raises(TrashError) as ei:
        client.app.state.trash.check_dir()  # pyright: ignore[reportAttributeAccessIssue]
    assert ei.value.code == "trash_unavailable"


def test_check_dir_recreates_removed_folder(tmp_path):
    db = tmp_path / "p.db"
    init_db(db)
    trash = tmp_path / "trash"
    store = TrashStore(db, trash)
    store.check_dir()
    assert trash.is_dir()
    os.rmdir(trash)
    store.check_dir()
    assert trash.is_dir()
