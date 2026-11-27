"""Tests for GET /api/discover/merged/list (See all mixed list) with fake sources."""

from __future__ import annotations

import logging
import time
from typing import Any, cast

from app.api import discover_merged
from app.api.options import _write_db  # pyright: ignore[reportPrivateUsage]
from app.models import MergedPage
from app.sources.base import Post, SearchPage, SourceError
from tests.test_discover_merged import SITES, FakeSource, _Req, make

URL = "/api/discover/merged/list"


class PagedSource(FakeSource):
    """Gives posts that carry the page number in their id; pages above *last* are empty."""

    def __init__(self, sid, n=3, last=2, **kw):
        super().__init__(sid, n, **kw)
        self.n = n
        self.last = last
        self.pages: list[int] = []

    def search(self, tags, page=1, page_size=None, order=None, rating=None):
        self.pages.append(page)
        if self.gate:
            self.release.wait(5)
        if self.error:
            raise self.error
        if page > self.last:
            return SearchPage(posts=[], page=page)
        posts = [
            Post(source=self.id, post_id=f"{self.id}-p{page}-{i}", preview_url="https://x/p.jpg")
            for i in range(self.n)
        ]
        return SearchPage(posts=posts, page=page)


def get_page(client, page=1) -> MergedPage:
    r = client.get(f"{URL}?page={page}")
    assert r.status_code == 200
    return MergedPage.model_validate(r.json())


def paged(**over):
    return {s: over.get(s) or PagedSource(s) for s in SITES}


def test_page_is_interleave_of_the_same_page_of_every_site(tmp_path):
    client, _ = make(tmp_path, **paged())
    res = get_page(client, 2)
    ids = [i.post_id for i in res.items]
    assert ids[:4] == [f"{s}-p2-0" for s in SITES]
    assert len(ids) == 12
    assert res.page == 2
    assert res.next_page == 3
    assert [s.id for s in res.sites] == SITES


def test_no_per_site_cap(tmp_path):
    client, _ = make(tmp_path, **{s: PagedSource(s, n=20) for s in SITES})
    assert len(get_page(client).items) == 20 * len(SITES)


def test_page_one_reuses_the_row_cache_and_page_two_calls_each_site_once(tmp_path):
    srcs = paged()
    client, _ = make(tmp_path, **srcs)
    assert client.get("/api/discover/merged").status_code == 200
    get_page(client, 1)
    assert all(s.pages == [1] for s in srcs.values())
    get_page(client, 2)
    get_page(client, 2)
    assert all(s.pages == [1, 2] for s in srcs.values())


def test_next_page_is_null_when_no_site_gave_posts(tmp_path):
    client, _ = make(tmp_path, **{s: PagedSource(s, last=1) for s in SITES})
    res = get_page(client, 2)
    assert res.items == []
    assert res.next_page is None


def test_slow_site_left_out_and_logged(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(discover_merged, "MERGE_WAIT_S", 0.2)
    slow = PagedSource("nhentai")
    slow.gate = True
    client, _ = make(tmp_path, **paged(nhentai=slow))
    with caplog.at_level(logging.INFO, logger="pearlie.discover_merge"):
        res = get_page(client, 2)
        slow.release.set()
        for _ in range(100):
            if any("state=late" in r.getMessage() for r in caplog.records):
                break
            time.sleep(0.05)
    assert all(i.source != "nhentai" for i in res.items)
    assert next(s for s in res.sites if s.id == "nhentai").state == "pending"
    assert res.next_page == 3
    lines = [r.getMessage() for r in caplog.records if r.name == "pearlie.discover_merge"]
    assert sum("site=nhentai state=pending" in ln for ln in lines) == 1


def test_failing_site_is_skipped(tmp_path):
    err = SourceError("rate_limited", "slow down", 429)
    client, _ = make(tmp_path, **paged(gelbooru=PagedSource("gelbooru", error=err)))
    res = get_page(client)
    assert next(s for s in res.sites if s.id == "gelbooru").state == "rate_limited"
    assert all(i.source != "gelbooru" for i in res.items)


def test_one_rail_site_gives_409(tmp_path):
    client, app = make(tmp_path, **paged())
    _write_db(cast(Any, _Req(app)), "options.global.hidden_sites", "gelbooru,rule34,nhentai")
    r = client.get(URL)
    assert r.status_code == 409
    assert r.json()["code"] == "not_merged"


def test_page_below_one_is_rejected(tmp_path):
    client, _ = make(tmp_path, **paged())
    assert client.get(f"{URL}?page=0").status_code == 422
