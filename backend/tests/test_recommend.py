"""Recommend and Random (T-388): ranking, the MIN_SCORE floor, rules, safe mode, Stump, nhentai."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

import httpx
from fastapi.testclient import TestClient

from app.api import recommend as rec
from app.bookserver.stump import StumpBookServer
from app.config import Settings
from app.filters.rules import RuleSet, load_rules, save_rules
from app.main import create_app
from app.sources.nhentai import NHentai
from app.sources.throttle import Throttle
from app.stump import Stump
from tests import stump_mock


def _cand(key: str, tags: set[str], people: set[str] | None = None) -> rec.Cand:
    return rec.Cand(key=key, tags=tags, people=people or set(), payload=None)


def _live_like_pool() -> tuple[set[str], list[rec.Cand], set[str]]:
    """215 books like the live Stump: 332 tags, two generic ones on ~87% of the books."""
    rng = random.Random(7)
    rare = [f"t{i}" for i in range(330)]
    weights = [1 / (i + 40) for i in range(330)]  # mean ~12 books per tag, a mild head
    seed = set(rng.sample(rare[:200], 20)) | {"big breasts", "sole male"}
    related = {0, 1, 2}
    pool: list[rec.Cand] = []
    for i in range(214):
        tags = set(rng.choices(rare, weights, k=rng.randint(4, 34)))
        if rng.random() < 0.88:
            tags.add("big breasts")
        if rng.random() < 0.87:
            tags.add("sole male")
        if i in related:  # a true neighbour: 11 of the seed's 22 tags
            tags = set(rng.sample(sorted(seed), 11)) | set(rng.sample(rare, 8))
        pool.append(_cand(f"b{i}", tags))
    return seed, pool, {f"b{i}" for i in related}


def test_floor_keeps_neighbours_and_drops_noise() -> None:
    seed, pool, related = _live_like_pool()
    got = rec.rank(seed, set(), pool)
    assert related <= {c.key for c in got}  # all true neighbours pass the floor
    assert (
        len(got) <= len(related) + 15
    )  # overlap noise does not flood the list (6.0 let 92 of 214 in)
    assert all(c.score >= rec.MIN_SCORE for c in got)
    assert got[0].key in related  # best first


def test_generic_tags_weigh_little() -> None:
    seed = {"big breasts", "sole male", "rare"}
    pool = [_cand(f"g{i}", {"big breasts", "sole male"}) for i in range(60)]
    pool.append(_cand("hit", {"rare"}))
    idf = rec.idf_table(seed, pool)
    assert idf["rare"] > 4 * idf["big breasts"]
    assert idf["rare"] > idf["sole male"]


def test_author_first_even_with_low_score() -> None:
    tags = {"a", "b", "c", "d", "e", "f", "g", "h"}
    pool = [_cand("strong", set(tags)), _cand("same", set(), {"mei"})]
    got = rec.rank(tags, {"mei"}, pool)
    assert [c.key for c in got] == ["same", "strong"]


def test_empty_when_nothing_reaches_the_floor() -> None:
    seed = {f"s{i}" for i in range(10)}
    assert rec.rank(seed, set(), [_cand("x", {"s0"})]) == []


def test_title_people() -> None:
    assert rec.title_people("[Group (Artist)] Name") == ("Artist", "Group")
    assert rec.title_people("[Solo] Name") == ("Solo", "")
    assert rec.title_people("No brackets") == ("", "")


# --- Stump endpoints ---


def _book(i: int, tags: list[str], title: str | None = None) -> dict:
    d = stump_mock.book(i)
    d["tags"] = [{"name": t} for t in tags]
    d["metadata"] = dict(d["metadata"], title=title or f"Book {i}")
    return d


def _app(tmp_path: Path, books: list[dict] | None = None, nh=None) -> TestClient:
    app = create_app(
        Settings(
            mode="real",
            db_path=tmp_path / "p.db",
            static_dir=tmp_path / "nostatic",
            _env_file=None,  # pyright: ignore[reportCallIssue]
        )
    )
    if books is not None:
        mock = stump_mock.MockStump([stump_mock.lib()], [stump_mock.series()], books, None)
        client = Stump(
            "http://stump.test",
            "k",
            httpx.Client(base_url="http://stump.test", transport=httpx.MockTransport(mock)),
            sleep=lambda _s: None,
        )
        app.state.settings.stump_url = "http://stump.test"
        app.state.books = StumpBookServer(client, None)
        app.state.stump_conn = ("http://stump.test", "")
    if nh is not None:
        app.state.sources["nhentai"] = NHentai(
            client=httpx.Client(transport=httpx.MockTransport(nh)), throttle=Throttle(0.0)
        )
    return TestClient(app)


SHARED = [f"s{i}" for i in range(10)]


def _library() -> list[dict]:
    return [
        _book(1, SHARED, "[Grp (Mei)] Seed"),
        _book(2, SHARED[:9], "Neighbour"),
        _book(3, ["zzz"], "[Grp (Mei)] Same author"),
        _book(4, ["other"], "Unrelated"),
        _book(5, SHARED + ["banned"], "Hidden by rule"),
    ]


def test_stump_recommend_orders_author_first_and_drops_seed(tmp_path) -> None:
    client = _app(tmp_path, _library())
    r = client.get("/api/recommend", params={"source": "stump", "id": "b1", "limit": 5})
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    ids = [i["id"] for i in items]
    assert ids[0] == "b3"  # same author first
    assert "b1" not in ids and "b4" not in ids
    assert {"b2", "b5"} <= set(ids)
    assert items[0]["author"] == "Mei" and items[0]["source"] == "stump"
    assert not {"score", "reason"} & set(items[0])


def test_stump_recommend_applies_reject_rules(tmp_path) -> None:
    client = _app(tmp_path, _library())
    db = client.app.state.settings.db_path  # pyright: ignore[reportAttributeAccessIssue]
    current = load_rules(db)
    save_rules(db, current.version, RuleSet(**{**current.__dict__, "reject": ["banned"]}))
    r = client.get("/api/recommend", params={"source": "stump", "id": "b1"})
    ids = [i["id"] for i in r.json()["items"]]
    assert "b5" not in ids and "b2" in ids


def test_stump_recommend_safe_mode_drops_warn_tags(tmp_path) -> None:
    client = _app(tmp_path, _library())
    db = client.app.state.settings.db_path  # pyright: ignore[reportAttributeAccessIssue]
    current = load_rules(db)
    save_rules(db, current.version, RuleSet(**{**current.__dict__, "warn": ["banned"]}))
    params = {"source": "stump", "id": "b1"}
    shown = [i["id"] for i in client.get("/api/recommend", params=params).json()["items"]]
    on = client.get("/api/recommend", params={**params, "safe": "true"})
    assert "b5" in shown and "b5" not in [i["id"] for i in on.json()["items"]]


def test_stump_series_recommend_drops_own_books(tmp_path) -> None:
    books = _library()
    for b in books[:2]:
        b["seriesId"] = "s1"
    for b in books[2:]:
        b["seriesId"] = "s2"
    client = _app(tmp_path, books)
    r = client.get("/api/recommend", params={"source": "stump", "id": "s1", "kind": "series"})
    assert r.status_code == 200, r.text
    assert not {i["id"] for i in r.json()["items"]} & {"b1", "b2"}


def test_stump_random_excludes_and_shuffles(tmp_path) -> None:
    client = _app(tmp_path, _library())
    seen = set()
    for _ in range(12):
        r = client.get(
            "/api/recommend/random", params={"source": "stump", "limit": 4, "exclude": "b1"}
        )
        assert r.status_code == 200, r.text
        ids = [i["id"] for i in r.json()["items"]]
        assert len(ids) == 4 and "b1" not in ids
        seen.add(tuple(ids))
    assert len(seen) > 1


def test_stump_walk_hides_trashed_books_before_the_scan(tmp_path, monkeypatch) -> None:
    client = _app(tmp_path, _library())
    state: Any = client.app.state  # pyright: ignore[reportAttributeAccessIssue]
    monkeypatch.setattr(state.trash, "stump_owned_ids", lambda: {"b2", "b3"})
    r = client.get("/api/recommend", params={"source": "stump", "id": "b1", "kind": "book"})
    assert r.status_code == 200, r.text
    assert not {"b2", "b3"} & {i["id"] for i in r.json()["items"]}
    for _ in range(12):
        r = client.get("/api/recommend/random", params={"source": "stump", "limit": 5})
        assert not {"b2", "b3"} & {i["id"] for i in r.json()["items"]}


def test_unknown_source_is_invalid(tmp_path) -> None:
    r = _app(tmp_path).get("/api/recommend/random", params={"source": "nope"})
    assert r.status_code == 422 and r.json()["code"] == "invalid"


# --- nhentai ---


def _gallery(i: int, tags: list[tuple[str, str]]) -> dict:
    return {
        "id": i,
        "media_id": str(1000 + i),
        "title": {"english": f"G{i}", "pretty": f"G{i}"},
        "thumbnail": f"galleries/{1000 + i}/thumb.jpg",
        "thumbnail_width": 250,
        "thumbnail_height": 350,
        "num_pages": 20,
        "tags": [{"id": 100 * i + n, "type": k, "name": v} for n, (k, v) in enumerate(tags)],
    }


def _is_search(request: httpx.Request) -> bool:
    return request.url.path.endswith("/search")


def _handler(seen: list, rows: list[dict], state: dict | None = None):
    state = state if state is not None else {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if state.get("limit") and _is_search(request):
            return httpx.Response(429, headers={"Retry-After": "30"})
        if _is_search(request):
            return httpx.Response(200, json={"result": rows, "num_pages": 9, "per_page": 25})
        gid = request.url.path.rsplit("/", 1)[1]
        return httpx.Response(200, json=next(r for r in rows if str(r["id"]) == gid))

    return handler


def test_nhentai_recommend_one_cached_search(tmp_path) -> None:
    pairs = [("tag", f"t{i}") for i in range(8)]
    rows = [
        _gallery(1, [("artist", "mei"), *pairs]),
        _gallery(2, [("artist", "mei")]),
        _gallery(3, pairs),
        _gallery(4, [("tag", "t0")]),
    ]
    seen: list = []
    client = _app(tmp_path, nh=_handler(seen, rows))
    params = {"source": "nhentai", "id": "1"}
    r = client.get("/api/recommend", params=params)
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    ids = [i["id"] for i in items]
    assert ids[0] == "2" and "1" not in ids and "4" not in ids and "3" in ids
    searches = [q for q in seen if _is_search(q)]
    assert len(searches) == 1 and "artist" in searches[0].url.params["query"]
    client.get("/api/recommend", params=params)
    assert len([q for q in seen if _is_search(q)]) == 1  # same seed, cached page
    assert items[0]["thumb_url"].startswith("/api/media/web/nhentai/")


def test_nhentai_rate_limited_carries_retry_after(tmp_path) -> None:
    seen: list = []
    state = {"limit": True}
    client = _app(tmp_path, nh=_handler(seen, [_gallery(1, [("artist", "mei")])], state))
    r = client.get("/api/recommend", params={"source": "nhentai", "id": "1"})
    assert r.status_code == 429, r.text
    body = r.json()
    assert body["code"] == "rate_limited" and body["retry_after"] > 0
    assert len([q for q in seen if _is_search(q)]) == 1  # no retry by itself


def test_nhentai_random_filters_page_and_serves_last_on_429(tmp_path) -> None:
    rows = [_gallery(i, [("language", "english"), ("tag", f"t{i}")]) for i in range(1, 7)]
    state: dict = {}
    seen: list = []
    client = _app(tmp_path, nh=_handler(seen, rows, state))
    r = client.get(
        "/api/recommend/random", params={"source": "nhentai", "limit": 3, "exclude": "1"}
    )
    assert r.status_code == 200, r.text
    ids = [i["id"] for i in r.json()["items"]]
    assert len(ids) == 3 and "1" not in ids
    state["limit"] = True
    for _ in range(20):  # random page numbers: some are cached, some hit the 429
        again = client.get("/api/recommend/random", params={"source": "nhentai", "limit": 3})
        assert again.status_code == 200  # the last random page stands in; never an error
        assert len(again.json()["items"]) == 3


def test_small_seed_floor_is_lower() -> None:
    pool = [_cand("hit", {"a", "b", "c", "d"}), _cand("miss", {"a"})] + [
        _cand(f"n{i}", set()) for i in range(30)
    ]
    assert [c.key for c in rec.rank({"a", "b", "c", "d"}, set(), pool)] == ["hit"]
