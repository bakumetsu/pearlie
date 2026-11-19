"""T-379: hunt-3 backend fixes (F3, F5, F6, F7, F9, F10, F14), mocked sites only."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest

from app import logs
from app.api import media_web_real as mw
from app.db import connect, init_db
from app.library import trash as trash_mod
from app.library.trash import TrashSpec, TrashStore
from app.sources.danbooru import parse_retry_after
from app.sources.throttle import Throttle
from tests.test_search_real import load, make_client


@pytest.fixture
def env(tmp_path):
    db = tmp_path / "p.db"
    init_db(db)
    (tmp_path / "trash").mkdir()
    (tmp_path / "lib").mkdir()
    return TrashStore(db, tmp_path / "trash"), tmp_path / "lib", db


def _spec(lib, name, **over):
    f = lib / name
    f.write_bytes(b"x")
    kw = dict(target="stash", kind="image", entity_id=name, title=name, orig_path=f)
    kw.update(over)
    return TrashSpec(**kw)


def test_f3_purge_keeps_saved_item_of_other_target(env):
    store, lib, db = env
    conn = connect(db)
    # (source, post_id) is unique: this row belongs to stump, so a stash purge must keep it
    conn.execute(
        "INSERT INTO saved_items (source, post_id, md5, target, image_id, kind) "
        "VALUES ('gelbooru','9','m','stump','z','image')"
    )
    conn.commit()
    conn.close()
    row = store.delete(_spec(lib, "a.jpg", source="gelbooru", post_id="9"), lambda: None)
    store.purge_row(row["token"])
    conn = connect(db)
    left = [r[0] for r in conn.execute("SELECT target FROM saved_items")]
    conn.close()
    assert left == ["stump"]


def test_f5_owned_ids_cached_and_dropped_on_write(env, monkeypatch):
    store, lib, _ = env
    scans = []
    real = trash_mod.connect

    def counting(path):
        scans.append(1)
        return real(path)

    monkeypatch.setattr(trash_mod, "connect", counting)
    assert store.stump_owned_ids() == set()
    n = len(scans)
    assert store.stump_owned_ids() == set()
    assert len(scans) == n  # served from the cache
    row = store.delete(
        _spec(lib, "b.cbz", target="stump", kind="book", entity_id="B1"), lambda: None
    )
    assert "B1" in store.stump_owned_ids()  # the write dropped the cache
    store.purge_row(row["token"])
    assert "B1" not in store.stump_owned_ids()


def test_f6_indexes_exist(env):
    _, _, db = env
    conn = connect(db)
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    conn.close()
    assert {
        "idx_trash_state",
        "idx_trash_source_post",
        "idx_trash_expires",
        "idx_rules_enabled",
    } <= names


def test_f7_parse_retry_after():
    assert parse_retry_after(None) is None
    assert parse_retry_after("-5") == 0.0
    assert parse_retry_after("0") == 0.0
    assert parse_retry_after("12") == 12.0
    assert parse_retry_after("nan") is None
    assert parse_retry_after("soon") is None
    when = format_datetime(datetime.now(UTC) + timedelta(seconds=30), usegmt=True)
    assert 20 < (parse_retry_after(when) or 0) <= 30
    past = format_datetime(datetime.now(UTC) - timedelta(seconds=30), usegmt=True)
    assert parse_retry_after(past) == 0.0


def test_f7_proxy_caps_retry_after():
    big = httpx.Response(429, headers={"Retry-After": "99999"})
    assert mw._retry_after(big) == mw.MAX_RETRY_AFTER
    zero = httpx.Response(429, headers={"Retry-After": "0"})
    assert mw._retry_after(zero) == 0.0


def test_f9_thumb_total_deadline(monkeypatch):
    class Src:
        id = "danbooru"
        _client = httpx.Client(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(
                    200, headers={"content-type": "image/png"}, content=b"x" * 10
                )
            )
        )

    monkeypatch.setattr(mw, "THUMB_DEADLINE", -1.0)
    out = mw._fetch_thumb(Src(), "1", "https://example.test/t.png", Throttle(0.0))  # type: ignore[arg-type]
    assert isinstance(out, mw._Refused)
    assert out.status == 504


def test_f10_search_cache_ignores_tag_order(tmp_path):
    calls = []

    def handler(request):
        calls.append(request.url)
        return httpx.Response(200, json=load("search"))

    client = make_client(tmp_path, handler)
    assert client.get("/api/search?q=a b&sources=danbooru").status_code == 200
    assert client.get("/api/search?q=b a&sources=danbooru").status_code == 200
    assert len(calls) == 1


def test_f14_secret_registration_failure_logs_class_only(caplog):
    class Store:
        def field_values(self, name):
            raise RuntimeError("hunter2-secret-value")

    with caplog.at_level(logging.WARNING, logger="pearlie.logs"):
        logs.register_stored_connections(Store())
    text = caplog.text
    assert "RuntimeError" in text
    assert "hunter2" not in text
