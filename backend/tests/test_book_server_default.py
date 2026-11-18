"""Unset PEARLIE_BOOK_SERVER: Stump when a Stump address is known, else Komga; env wins."""

from __future__ import annotations

import logging

from app.config import Settings
from app.main import _with_book_server


def _settings(**kw: object) -> Settings:
    return Settings(mode="real", _env_file=None, **kw)  # type: ignore[call-arg]


def test_unset_without_stump_is_komga(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="pearlie"):
        s = _with_book_server(_settings())
    assert s.book_server == "komga"
    assert sum("book server: komga" in r.message for r in caplog.records) == 1


def test_unset_with_stump_address_is_stump(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="pearlie"):
        s = _with_book_server(_settings(stump_url="http://stump.test"))
    assert s.book_server == "stump"
    assert any("book server: stump" in r.message for r in caplog.records)


def test_explicit_env_wins() -> None:
    s = _with_book_server(_settings(book_server="komga", stump_url="http://stump.test"))
    assert s.book_server == "komga" and not s._book_server_auto


def test_reresolves_after_address_save() -> None:
    first = _with_book_server(_settings())
    assert first.book_server == "komga"
    saved = first.model_copy(update={"stump_url": "http://stump.test"})
    assert _with_book_server(saved).book_server == "stump"


def test_stable_resolve_logs_once(caplog) -> None:
    s = _with_book_server(_settings(stump_url="http://stump.test"))
    with caplog.at_level(logging.INFO, logger="pearlie"):
        again = _with_book_server(s)
    assert again.book_server == "stump" and not caplog.records


def test_env_cannot_set_the_auto_flag(monkeypatch) -> None:
    monkeypatch.setenv("PEARLIE_BOOK_SERVER_AUTO", "true")
    s = Settings(mode="real", book_server="komga", stump_url="http://stump.test", _env_file=None)  # type: ignore[call-arg]
    assert _with_book_server(s).book_server == "komga"


def test_options_save_flips_book_server_without_restart(tmp_path) -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app

    settings = Settings(
        mode="real",
        real="search",
        db_path=tmp_path / "p.db",
        static_dir=tmp_path / "nostatic",
        _env_file=None,  # type: ignore[call-arg]
    )
    app = create_app(settings)
    with TestClient(app, base_url="http://localhost") as c:
        assert app.state.settings.book_server == "komga"
        r = c.put(
            "/api/connections/stump",
            json={"address": "http://stump.test:10801"},
            headers={"Origin": "http://localhost", "Content-Type": "application/json"},
        )
        assert r.status_code == 200
        assert app.state.settings.book_server == "stump"
