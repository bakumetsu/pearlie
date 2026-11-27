"""Tests for GET /api/discover/merged with fake sources (no network)."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, cast

from fastapi.testclient import TestClient

from app.api import discover_merged
from app.api.options import _write_db  # pyright: ignore[reportPrivateUsage]
from app.config import Settings
from app.main import create_app
from app.models import MergedRow
from app.sources.base import Post, SearchPage, SourceError

SITES = ["danbooru", "gelbooru", "rule34", "nhentai"]


class FakeSource:
    """A source that returns a fixed page, can fail or wait on a gate, and counts its calls."""

    target = "stash"
    file_hosts: tuple[str, ...] = ()

    def __init__(self, sid, n=3, md5s=None, error=None):
        self.id = sid
        self.posts = [
            Post(
                source=sid,
                post_id=f"{sid}-{i}",
                md5=(md5s or {}).get(i),
                preview_url="https://x/p.jpg",
                width=10,
                height=10,
            )
            for i in range(n)
        ]
        self.error = error
        self.calls = 0
        self.release = threading.Event()
        self.gate = False

    def search(self, tags, page=1, page_size=None, order=None, rating=None):
        self.calls += 1
        if self.gate:
            self.release.wait(5)
        if self.error:
            raise self.error
        return SearchPage(posts=self.posts, page=page)


class _Req:
    """Stand-in for a Request: _write_db only reads .app."""

    def __init__(self, app):
        self.app = app


def make(tmp_path, **fakes):
    app = create_app(
        Settings(
            mode="real",
            real="search",
            db_path=tmp_path / "p.db",
            static_dir=tmp_path / "nostatic",
            _env_file=None,  # pyright: ignore[reportCallIssue]
        )
    )
    for sid in SITES:
        app.state.sources[sid] = fakes.get(sid) or FakeSource(sid)
    return TestClient(app), app


def get_row(client, url="/api/discover/merged") -> MergedRow:
    r = client.get(url)
    assert r.status_code == 200
    return MergedRow.model_validate(r.json())


def test_order_is_round_robin_in_rail_order(tmp_path):
    client, _ = make(tmp_path)
    row = get_row(client)
    ids = [i.post_id for i in row.items]
    assert ids[:4] == [f"{s}-0" for s in SITES]
    assert len(ids) == 12
    assert [s.id for s in row.sites] == SITES
    assert all(s.state == "ok" and s.count == 3 for s in row.sites)
    assert not row.pending


def test_site_order_option_sets_rail_order(tmp_path):
    client, app = make(tmp_path)
    _write_db(cast(Any, _Req(app)), "options.global.site_order", "nhentai,rule34")
    row = get_row(client)
    assert [s.id for s in row.sites] == ["nhentai", "rule34", "danbooru", "gelbooru"]
    assert row.items[0].post_id == "nhentai-0"


def test_dedupe_by_md5_across_sites(tmp_path):
    client, _ = make(
        tmp_path,
        danbooru=FakeSource("danbooru", 2, md5s={0: "aa"}),
        gelbooru=FakeSource("gelbooru", 2, md5s={0: "AA"}),
    )
    row = get_row(client)
    ids = [i.post_id for i in row.items]
    assert "danbooru-0" in ids
    assert "gelbooru-0" not in ids
    assert next(s for s in row.sites if s.id == "gelbooru").count == 1
    assert row.hidden == 0


def test_each_site_gives_at_most_twelve(tmp_path):
    client, _ = make(tmp_path, **{s: FakeSource(s, 20) for s in SITES})
    row = get_row(client)
    assert len(row.items) == 12 * len(SITES)
    assert all(s.count == 12 for s in row.sites)


def test_one_rail_site_gives_409(tmp_path):
    client, app = make(tmp_path)
    _write_db(cast(Any, _Req(app)), "options.global.hidden_sites", "gelbooru,rule34,nhentai")
    r = client.get("/api/discover/merged")
    assert r.status_code == 409
    assert r.json()["code"] == "not_merged"


def test_hidden_site_is_left_out(tmp_path):
    client, app = make(tmp_path)
    _write_db(cast(Any, _Req(app)), "options.global.hidden_sites", "rule34")
    row = get_row(client)
    assert [s.id for s in row.sites] == ["danbooru", "gelbooru", "nhentai"]


def test_failing_sites_state_and_one_log_line_without_secrets(tmp_path, caplog):
    client, _ = make(
        tmp_path,
        gelbooru=FakeSource("gelbooru", error=SourceError("rate_limited", "slow down", 429)),
        rule34=FakeSource("rule34", error=SourceError("upstream", "bad apikey=SECRET123")),
    )
    with caplog.at_level(logging.INFO, logger="pearlie.discover_merge"):
        row = get_row(client)
    states = {s.id: s.state for s in row.sites}
    assert states["gelbooru"] == "rate_limited"
    assert states["rule34"] == "error"
    assert all(i.source not in ("gelbooru", "rule34") for i in row.items)
    lines = [r.getMessage() for r in caplog.records if r.name == "pearlie.discover_merge"]
    assert len(lines) == 2
    assert all("SECRET123" not in ln and "bad" not in ln for ln in lines)
    assert any(
        "site=gelbooru state=rate_limited" in ln and "reason=rate_limited" in ln for ln in lines
    )
    assert any("site=rule34 state=error" in ln and "reason=upstream" in ln for ln in lines)


def test_all_sites_failing_gives_empty_row(tmp_path):
    err = SourceError("upstream", "down")
    client, _ = make(tmp_path, **{s: FakeSource(s, error=err) for s in SITES})
    row = get_row(client)
    assert row.items == []
    assert all(s.state == "error" for s in row.sites)


def test_partial_wait_pending_then_late_log(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(discover_merged, "MERGE_WAIT_S", 0.2)
    slow = FakeSource("nhentai")
    slow.gate = True
    client, _ = make(tmp_path, nhentai=slow)
    with caplog.at_level(logging.INFO, logger="pearlie.discover_merge"):
        row = get_row(client)
        assert row.pending
        assert next(s for s in row.sites if s.id == "nhentai").state == "pending"
        assert all(i.source != "nhentai" for i in row.items)
        slow.release.set()
        for _ in range(100):
            if any("state=late" in r.getMessage() for r in caplog.records):
                break
            time.sleep(0.05)
    lines = [r.getMessage() for r in caplog.records if r.name == "pearlie.discover_merge"]
    assert sum("site=nhentai state=pending" in ln for ln in lines) == 1
    assert sum("site=nhentai state=late" in ln for ln in lines) == 1
    # the late page is cached: the next call has the site, with no new site call
    row2 = get_row(client, "/api/discover/merged?have=danbooru,gelbooru,rule34")
    assert not row2.pending
    assert slow.calls == 1
    assert [i.source for i in row2.items][-3:] == ["nhentai"] * 3


def test_have_keeps_seen_sites_first(tmp_path):
    client, _ = make(tmp_path)
    row = get_row(client, "/api/discover/merged?have=gelbooru,danbooru")
    ids = [i.post_id for i in row.items]
    assert ids[:4] == ["danbooru-0", "gelbooru-0", "danbooru-1", "gelbooru-1"]
    assert ids[-1] == "nhentai-2"


def test_split_request_joins_running_merged_call(tmp_path, monkeypatch):
    monkeypatch.setattr(discover_merged, "MERGE_WAIT_S", 0.2)
    slow = FakeSource("danbooru")
    slow.gate = True
    client, _ = make(tmp_path, danbooru=slow)
    assert get_row(client).pending
    out: dict = {}

    def split():
        out["r"] = client.get("/api/search?sources=danbooru,gelbooru")

    t = threading.Thread(target=split)
    t.start()
    time.sleep(0.3)  # the split request now waits on the running call
    slow.release.set()
    t.join(5)
    assert out["r"].status_code == 200
    assert slow.calls == 1
