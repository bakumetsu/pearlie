"""Tests for the random-sort feature on Komga library endpoints."""

from __future__ import annotations

import httpx
from test_komga_real import book_dto, make_client, page_of, series_dto


def _series_dtos() -> list[dict]:
    return [series_dto(f"s{i}") for i in range(25)]


def _book_dtos() -> list[dict]:
    return [book_dto(f"b{i}") for i in range(25)]


def _list_handler(dtos: list[dict], calls: list[str]):
    """MockTransport handler serving POST /api/v1/series/list and /api/v1/books/list."""

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if (
            request.method == "POST"
            and request.url.path in ("/api/v1/series/list", "/api/v1/books/list")
        ):
            page = int(request.url.params.get("page", "0"))
            size = int(request.url.params.get("size", "25"))
            start = page * size
            end = start + size
            items = dtos[start:end]
            last = end >= len(dtos)
            return httpx.Response(200, json=page_of(items, last=last, total=len(dtos)))
        return httpx.Response(404)

    return handler


def test_random_pages_same_seed_no_repeats(tmp_path):
    """Random sort with a fixed seed: pages are unique, complete, cached, and differ
    from createdDate order."""
    dtos = _series_dtos()
    calls: list[str] = []
    handler = _list_handler(dtos, calls)

    client = make_client(tmp_path, handler)
    all_ids: list[str] = []
    expected_all = [f"s{i}" for i in range(25)]

    for page_num in (1, 2, 3):
        r = client.get(
            f"/api/library/komga/series?sort=random&seed=42&page_size=10&page={page_num}"
        )
        assert r.status_code == 200
        body = r.json()
        assert body["seed"] == 42
        assert body["total"] == 25
        ids = [item["id"] for item in body["items"]]
        all_ids.extend(ids)

        if page_num == 1:
            assert len(ids) == 10
            assert body["next_page"] == 2
            # Must differ from plain createdDate (insertion) order
            assert ids != ["s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9"]
        elif page_num == 2:
            assert len(ids) == 10
            assert body["next_page"] == 3
        else:
            assert len(ids) == 5
            assert body["next_page"] is None

    # Unique across all pages, union equals full set
    assert len(all_ids) == 25
    assert len(set(all_ids)) == 25
    assert sorted(all_ids) == sorted(expected_all)

    # Only one full-library fetch across all three page requests (cache proof)
    assert calls.count("/api/v1/series/list") == 1


def test_random_same_seed_same_order_across_visits(tmp_path):
    """Same seed on a fresh client yields identical id order."""
    dtos = _series_dtos()

    calls1: list[str] = []
    client1 = make_client(tmp_path, _list_handler(dtos, calls1))
    r1 = client1.get("/api/library/komga/series?sort=random&seed=42&page_size=10&page=1")
    order1 = [item["id"] for item in r1.json()["items"]]

    # New client (fresh cache) with the same seed
    calls2: list[str] = []
    client2 = make_client(tmp_path, _list_handler(dtos, calls2))
    r2 = client2.get("/api/library/komga/series?sort=random&seed=42&page_size=10&page=1")
    order2 = [item["id"] for item in r2.json()["items"]]

    assert order1 == order2


def test_random_without_seed_makes_new_seed(tmp_path):
    """sort=random without seed returns a generated seed; page 2 with that seed has no repeats."""
    dtos = _series_dtos()
    calls: list[str] = []
    handler = _list_handler(dtos, calls)

    client = make_client(tmp_path, handler)
    r1 = client.get("/api/library/komga/series?sort=random&page_size=10&page=1")
    assert r1.status_code == 200
    body1 = r1.json()
    seed = body1["seed"]
    assert isinstance(seed, int)
    assert 0 <= seed < 10**8

    page1_ids = {item["id"] for item in body1["items"]}

    r2 = client.get(
        f"/api/library/komga/series?sort=random&seed={seed}&page_size=10&page=2"
    )
    assert r2.status_code == 200
    page2_ids = {item["id"] for item in r2.json()["items"]}

    assert page1_ids & page2_ids == set()


def test_random_books(tmp_path):
    """Random sort on books endpoint: same guarantees as series, one upstream request."""
    dtos = _book_dtos()
    calls: list[str] = []
    handler = _list_handler(dtos, calls)

    client = make_client(tmp_path, handler)
    all_ids: list[str] = []
    expected_all = [f"b{i}" for i in range(25)]

    for page_num in (1, 2, 3):
        r = client.get(
            f"/api/library/komga/books?sort=random&seed=42&page_size=10&page={page_num}"
        )
        assert r.status_code == 200
        body = r.json()
        assert body["seed"] == 42
        assert body["total"] == 25
        ids = [item["id"] for item in body["items"]]
        all_ids.extend(ids)

    assert len(all_ids) == 25
    assert len(set(all_ids)) == 25
    assert sorted(all_ids) == sorted(expected_all)
    assert calls.count("/api/v1/books/list") == 1


def test_random_no_option_ignored_notice(tmp_path):
    """sort=random gives no notice; with favorite=true the notice names favorite only."""
    dtos = _series_dtos()
    calls: list[str] = []
    handler = _list_handler(dtos, calls)

    client = make_client(tmp_path, handler)

    r = client.get("/api/library/komga/series?sort=random&page_size=10&page=1")
    assert r.status_code == 200
    assert r.json()["notice"] is None

    r2 = client.get(
        "/api/library/komga/series?sort=random&favorite=true&page_size=10&page=1"
    )
    assert r2.status_code == 200
    notice = r2.json()["notice"]
    assert notice is not None
    assert notice["code"] == "option_ignored"
    assert "favorite=true" in notice["message"]
    assert "sort=random" not in notice["message"]


def test_random_upstream_error(tmp_path):
    """Upstream 500 on the list endpoint surfaces as 502 with code upstream_error."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = make_client(tmp_path, handler)
    r = client.get("/api/library/komga/series?sort=random&seed=42&page_size=10&page=1")
    assert r.status_code == 502
    assert r.json()["code"] == "upstream_error"
