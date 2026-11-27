"""Tests for the pure Discover merge logic."""

from __future__ import annotations

from app.discover_merge import dedupe, dedupe_key, interleave, rail_sites
from app.sources.base import Post


def _post(source: str, pid: str, md5: str | None = None) -> Post:
    return Post(source=source, post_id=pid, md5=md5)


def test_rail_sites_drops_hidden_and_unconfigured():
    got = rail_sites(["a", "b", "c", "d"], hidden={"b"}, available={"a", "b", "d"})
    assert got == ["a", "d"]


def test_interleave_round_robin_in_rail_order():
    lists = {"a": [1, 2, 3], "b": [10, 20], "c": [100]}
    assert interleave(lists, ["a", "b", "c"]) == [1, 10, 100, 2, 20, 3]


def test_interleave_five_sites_no_cut_below_per_site_times_sites():
    sites = [f"s{i}" for i in range(5)]
    lists = {s: [f"{s}-{n}" for n in range(12)] for s in sites}
    row = interleave(lists, sites)
    assert len(row) == 60
    assert row[:5] == [f"s{i}-0" for i in range(5)]
    assert row[-1] == "s4-11"


def test_interleave_cuts_each_site_to_per_site():
    lists = {"a": list(range(30)), "b": list(range(30))}
    assert len(interleave(lists, ["a", "b"])) == 24
    assert len(interleave(lists, ["a", "b"], per_site=None)) == 60


def test_interleave_have_sites_first_then_late_site_appended():
    lists = {"a": [1, 2], "b": [10, 20], "c": [100, 200]}
    row = interleave(lists, ["a", "b", "c"], have={"a", "b"})
    assert row == [1, 10, 2, 20, 100, 200]


def test_interleave_skips_site_without_list():
    assert interleave({"a": [1], "c": [3]}, ["a", "b", "c"]) == [1, 3]


def test_dedupe_by_md5_first_wins():
    posts = [_post("danbooru", "1", "AB"), _post("gelbooru", "9", "ab"), _post("rule34", "2", "cd")]
    assert [p.post_id for p in dedupe(posts)] == ["1", "2"]


def test_dedupe_without_md5_uses_source_and_id():
    posts = [_post("nhentai", "5"), _post("nhentai", "5"), _post("danbooru", "5")]
    assert dedupe_key(posts[0]) == "nhentai:5"
    assert [p.source for p in dedupe(posts)] == ["nhentai", "danbooru"]
