from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
from test_job_worker import enqueue, make

from app import logs
from app.config import Settings
from app.connections_store import ConnectionStore
from app.main import create_app
from app.targets.stash import SaveError

SENTINEL = "SENTINEL-CONN-91c4f7aa"


@pytest.fixture(autouse=True)
def _reset_logging(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.delenv(logs.ENV_DEBUG, raising=False)
    logs.clear_secrets()
    yield
    h = logs._handler
    if h is not None:
        logging.getLogger().removeHandler(h)
        h.close()
    logs._handler = None
    logs.clear_secrets()


def text(d: Path) -> str:
    return "".join(f.read_text(encoding="utf-8") for f in sorted(d.glob("*.log")))


def test_create_app_writes_a_daily_file(settings: Settings, tmp_path: Path) -> None:
    create_app(settings)
    logging.getLogger("pearlie.test").info("hello from the test")
    logs_dir = tmp_path / "logs"
    assert logs.log_dir() == logs_dir
    assert "hello from the test" in text(logs_dir)
    assert not logs.is_debug()


def test_env_flag_turns_debug_on(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(logs.ENV_DEBUG, "1")
    create_app(settings)
    assert logs.is_debug()


def test_saved_connection_secret_is_hidden(settings: Settings, tmp_path: Path) -> None:
    create_app(settings)
    store = ConnectionStore(settings, {})
    store.save("stash", "http://stash:9999", SENTINEL, False)
    logging.getLogger("pearlie.test").error("stash answered with key %s", SENTINEL)
    out = text(tmp_path / "logs")
    assert "stash answered with key" in out
    assert SENTINEL not in out


def test_worker_end_line_has_state_code_and_message(tmp_path: Path) -> None:
    logs.setup_logging(tmp_path / "logs", debug=False)
    worker, store, target, sources, _clock = make(tmp_path)
    target.results.append(SaveError("image_not_found", "Stash did not index the file", 502))
    jid = enqueue(store, sources, "danbooru", "1")
    assert worker.run_once() is True
    out = text(tmp_path / "logs")
    assert f"job={jid} start source=danbooru target=stash" in out
    assert f"job={jid} end state=failed code=image_not_found message=Stash did not index" in out
