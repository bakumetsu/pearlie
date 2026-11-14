"""Tests for placement: oneshots dir, name index, plan rules, cache."""

from __future__ import annotations

from pathlib import Path

from app.targets import placement
from app.targets.placement import (
    IndexCache,
    build_index,
    clean_folder_name,
    make_plan,
    oneshots_dir_name,
)
from app.targets.placement_name import parse_name

LIBS = [
    {"id": "1", "root": "/komga/manga", "oneshotsDirectory": "_oneshots"},
    {"id": "2", "root": "/komga/other"},
]


def test_oneshots_dir_name_from_library():
    assert oneshots_dir_name(LIBS, "/komga/manga/nhentai").name == "_oneshots"


def test_oneshots_dir_name_maps_prefix():
    d = oneshots_dir_name(LIBS, "/data/manga/nh", "/data", "/komga")
    assert d.name == "_oneshots"


def test_oneshots_dir_not_set():
    d = oneshots_dir_name(LIBS, "/komga/other/x")
    assert (d.name, d.notice) == (None, "oneshots_not_set")


def test_oneshots_dir_refused_values():
    for bad in (".hidden", "a/b", "a\\b", "  "):
        libs = [{"root": "/k", "oneshotsDirectory": bad}]
        assert oneshots_dir_name(libs, "/k/x").name is None


def test_oneshots_dir_outside_any_library():
    assert oneshots_dir_name(LIBS, "/elsewhere").name is None


def test_clean_folder_name():
    assert clean_folder_name('[A] Foo: "Bar"?. ') == "[A] Foo Bar"
    assert clean_folder_name("???") == "Grouped_Series"


def _tree(tmp_path: Path) -> Path:
    root = tmp_path / "nh"
    (root / "[Kisaragi] Love").mkdir(parents=True)
    (root / "[Kisaragi] Hotel").mkdir()
    (root / "Plain Series").mkdir()
    (root / "loose.cbz").write_bytes(b"x")
    one = root / "_oneshots"
    one.mkdir()
    (one / "[Kisaragi] Solo (Original) [English].cbz").write_bytes(b"x")
    return root


def test_build_index(tmp_path):
    idx = build_index(_tree(tmp_path), "_oneshots")
    assert idx.series["[kisaragi]"] == {"love": "[Kisaragi] Love", "hotel": "[Kisaragi] Hotel"}
    assert idx.series[""] == {"plain series": "Plain Series"}
    assert "_oneshots" not in str(idx.series)
    assert idx.oneshots["[kisaragi]"][0][0] == "solo"


def test_build_index_without_oneshots_dir(tmp_path):
    idx = build_index(_tree(tmp_path), None)
    assert idx.oneshots == {}


def test_build_index_missing_root(tmp_path):
    idx = build_index(tmp_path / "nope", "_oneshots")
    assert idx.series == {} and not idx.too_large


def test_build_index_too_large(tmp_path, monkeypatch):
    monkeypatch.setattr(placement, "MAX_ENTRIES", 2)
    root = tmp_path / "big"
    root.mkdir()
    for i in range(3):
        (root / f"[A] S{i}").mkdir()
    assert build_index(root, None).too_large


def test_plan_exact_folder(tmp_path):
    idx = build_index(_tree(tmp_path), "_oneshots")
    p = make_plan(idx, parse_name("[kisaragi] LOVE 2 (Original)"), "auto")
    assert (p.kind, p.via, p.folder, p.number) == ("series", "folder", "[Kisaragi] Love", "2")


def test_plan_series_folder_without_number(tmp_path):
    idx = build_index(_tree(tmp_path), "_oneshots")
    p = make_plan(idx, parse_name("[Kisaragi] Love (Original)"), "auto")
    assert (p.kind, p.via) == ("series", "folder")


def test_plan_oneshot_pair_moves_first(tmp_path):
    idx = build_index(_tree(tmp_path), "_oneshots")
    p = make_plan(idx, parse_name("[Kisaragi] Solo 2 [English]"), "auto")
    assert p.kind == "series" and p.via == "oneshot_pair"
    assert p.folder == "[Kisaragi] Solo"
    assert p.move_from == ("[Kisaragi] Solo (Original) [English].cbz",)


def test_plan_new_series_and_oneshot(tmp_path):
    idx = build_index(_tree(tmp_path), "_oneshots")
    s = make_plan(idx, parse_name("[Other] Brand New 3"), "auto")
    assert (s.kind, s.via, s.folder, s.series) == (
        "series",
        "new",
        "[Other] Brand New",
        "Brand New",
    )
    o = make_plan(idx, parse_name("[Other] Lonely"), "auto")
    assert (o.kind, o.series, o.folder) == ("oneshot", None, None)


def test_plan_absorb_only_in_suggest(tmp_path):
    idx = build_index(_tree(tmp_path), "_oneshots")
    parsed = parse_name("[Kisaragi] Love Hotel Nights")
    auto = make_plan(idx, parsed, "auto")
    assert auto.kind == "oneshot"
    sug = make_plan(idx, parsed, "suggest")
    assert (sug.kind, sug.via, sug.folder, sug.series) == (
        "series",
        "absorb",
        "[Kisaragi] Love",
        "Love",
    )


def test_plan_absorb_needs_whole_word(tmp_path):
    idx = build_index(_tree(tmp_path), "_oneshots")
    p = make_plan(idx, parse_name("[Kisaragi] Lovely Days"), "suggest")
    assert p.kind == "oneshot"


def test_plan_absorb_shortest_wins(tmp_path):
    root = _tree(tmp_path)
    (root / "[Kisaragi] Love Hotel").mkdir()
    idx = build_index(root, "_oneshots")
    p = make_plan(idx, parse_name("[Kisaragi] Love Hotel Nights"), "suggest")
    assert p.folder == "[Kisaragi] Love"


def test_plan_reverse_prefix_does_not_absorb(tmp_path):
    root = _tree(tmp_path)
    (root / "[Mika] Night Shift Extra").mkdir()
    idx = build_index(root, "_oneshots")
    p = make_plan(idx, parse_name("[Mika] Night Shift"), "suggest")
    assert p.kind == "oneshot"


def test_plan_absorb_into_oneshot_moves_it(tmp_path):
    idx = build_index(_tree(tmp_path), "_oneshots")
    p = make_plan(idx, parse_name("[Kisaragi] Solo Again"), "suggest")
    assert (p.kind, p.via, p.folder) == ("series", "absorb", "[Kisaragi] Solo")
    assert len(p.move_from) == 1


def test_cache_ttl_and_invalidate(tmp_path):
    now = [0.0]
    cache = IndexCache(ttl=30, clock=lambda: now[0])
    root = _tree(tmp_path)
    first = cache.get(root, "_oneshots")
    (root / "[New] Thing").mkdir()
    assert cache.get(root, "_oneshots") is first
    now[0] = 31
    assert "[new]" in cache.get(root, "_oneshots").series
    (root / "[Newer] Thing").mkdir()
    cache.invalidate()
    assert "[newer]" in cache.get(root, "_oneshots").series
