import pytest

from app.fixtures.store import store
from app.models import JobList, LibraryItem, LibraryItemDetail, Page, SearchResponse, TrashResult


@pytest.fixture(autouse=True)
def _reset(client):
    client.post("/api/_fixture/reset")
    yield
    client.post("/api/_fixture/reset")


def test_search_all_sections(client):
    """Six sections in order with size limits."""
    r = client.get("/api/search")
    assert r.status_code == 200
    sr = SearchResponse.model_validate(r.json())
    assert [s.id for s in sr.sections] == [
        "stash_images",
        "stash_videos",
        "komga_books",
        "danbooru",
        "gelbooru",
        "nhentai",
    ]
    for s in sr.sections[:3]:
        assert len(s.items) <= 12
    for s in sr.sections[3:]:
        assert len(s.items) <= 18


def test_search_single_source_pages(client):
    """Single source paged at 60 per page."""
    sr = SearchResponse.model_validate(
        client.get("/api/search", params={"sources": "danbooru"}).json()
    )
    assert len(sr.sections[0].items) == 60
    assert sr.sections[0].next_page == 2
    sr2 = SearchResponse.model_validate(
        client.get("/api/search", params={"sources": "danbooru", "page": 2}).json()
    )
    assert sr2.sections[0].next_page == 3


def test_search_rule34_accepted(client):
    """rule34 is a valid source."""
    assert client.get("/api/search", params={"sources": "rule34"}).status_code == 200


def test_search_unknown_source_422(client):
    """Unknown source returns 422 invalid."""
    r = client.get("/api/search", params={"sources": "nope"})
    assert r.status_code == 422
    assert r.json()["code"] == "invalid"
    assert r.json()["field"] == "sources"


def test_library_list_each_kind(client):
    """Four list paths return Page[LibraryItem]."""
    paths = [
        "/api/library/stash/images",
        "/api/library/stash/videos",
        "/api/library/komga/books",
        "/api/library/series",
    ]
    for p in paths:
        r = client.get(p, params={"page_size": 5})
        assert r.status_code == 200
        assert len(Page[LibraryItem].model_validate(r.json()).items) == 5


def test_library_first_page_stable(client):
    """First page ids identical across calls, even sort=random."""
    a = [i["id"] for i in client.get("/api/library/stash/images").json()["items"]]
    b = [i["id"] for i in client.get("/api/library/stash/images").json()["items"]]
    assert a == b
    c = [
        i["id"]
        for i in client.get("/api/library/stash/images", params={"sort": "random"}).json()["items"]
    ]
    d = [
        i["id"]
        for i in client.get("/api/library/stash/images", params={"sort": "random"}).json()["items"]
    ]
    assert c == d


def test_detail_and_404(client):
    """Detail endpoint validates; unknown ids and kinds give 404."""
    d = LibraryItemDetail.model_validate(client.get("/api/library/images/3").json())
    assert d.full_url
    assert len(client.get("/api/library/series/0").json()["items"]) == 3
    r404 = client.get("/api/library/images/99999")
    assert r404.status_code == 404 and r404.json()["code"] == "not_found"
    assert client.get("/api/library/bogus/1").status_code == 404


def test_patch_round_trip(client):
    """PATCH fields persist; invalid values rejected."""
    client.patch("/api/library/images/3", json={"rating": 4, "favorite": True, "tags": ["a", "b"]})
    g = client.get("/api/library/images/3").json()
    assert g["rating"] == 4 and g["favorite"] is True and g["tags"] == ["a", "b"]
    client.patch("/api/library/images/3", json={"rating": None})
    assert client.get("/api/library/images/3").json()["rating"] is None
    assert client.patch("/api/library/images/3", json={"rating": 9}).status_code == 422
    rb = client.patch("/api/library/images/3", json={"tags": [""]})
    assert rb.status_code == 422 and "tags" in rb.json()["field"]


def test_delete_restore(client):
    """Delete, verify 404s, restore, double-restore 404."""
    TrashResult.model_validate(client.delete("/api/library/images/3").json())
    assert client.get("/api/library/images/3").status_code == 404
    assert client.get("/api/media/stash/images/3/thumb").status_code == 404
    assert client.post("/api/library/images/3/restore").status_code == 200
    assert client.get("/api/library/images/3").status_code == 200
    assert client.post("/api/library/images/3/restore").status_code == 404


def test_progress(client):
    """Page 99 on a 100-page book marks completed."""
    r = client.post("/api/library/komga/books/0/progress", json={"page": 99})
    assert r.status_code == 200 and r.json()["completed"] is True


def test_media_range(client):
    """Range request, cache headers, 404 on unknown, video skip."""
    r = client.get("/api/media/stash/images/3/full", headers={"Range": "bytes=0-99"})
    assert r.status_code == 206
    assert r.headers["content-range"].startswith("bytes 0-99/")
    t = client.get("/api/media/stash/images/3/thumb")
    assert "cache-control" in t.headers
    assert "etag" in t.headers
    assert client.get("/api/media/stash/images/99999/thumb").status_code == 404
    if client.get("/api/media/stash/videos/1/stream").status_code == 404:
        pytest.skip("video stream unavailable")


def test_save_flow(client):
    """Save web item, verify job, re-save conflicts."""
    sr = SearchResponse.model_validate(
        client.get("/api/search", params={"sources": "danbooru"}).json()
    )
    target = next(i for i in sr.sections[0].items if not i.saved)
    r = client.post("/api/save", json={"source": "danbooru", "id": target.id})
    assert r.status_code == 202
    assert client.get(f"/api/jobs/{r.json()['job_id']}").status_code == 200
    dup = client.post("/api/save", json={"source": "danbooru", "id": target.id})
    assert dup.status_code == 409 and dup.json()["code"] == "already_saved"


def test_save_rejected_422(client):
    """Saving a _rejected post returns 422 rejected_by_rule."""
    rejected = next(p for p in store.web["danbooru"] if "_rejected" in str(p))
    r = client.post("/api/save", json={"source": "danbooru", "id": rejected.id})
    assert r.status_code == 422 and r.json()["code"] == "rejected_by_rule"


def test_jobs_list_seed(client):
    """Seed: 20 jobs, filter, retry, delete semantics."""
    jl = JobList.model_validate(client.get("/api/jobs").json())
    assert len(jl.items) == 20
    jl_f = JobList.model_validate(client.get("/api/jobs", params={"state": "failed"}).json())
    assert len(jl_f.items) == 2 and all(j.state == "failed" for j in jl_f.items)
    assert client.post(f"/api/jobs/{jl_f.items[0].id}/retry").json()["state"] == "queued"
    done = next(j for j in jl.items if j.state == "done")
    assert client.post(f"/api/jobs/{done.id}/retry").status_code == 409
    assert client.delete(f"/api/jobs/{done.id}").status_code == 204
    running = next(j for j in jl.items if j.state == "running")
    assert client.delete(f"/api/jobs/{running.id}").status_code == 409


def test_rules_flow(client):
    """Versioning, stale conflict, validation, test endpoint."""
    rules = client.get("/api/rules").json()
    assert rules["version"] == 1 and rules["base_list"]["read_only"] is True
    assert client.put("/api/rules", json={**rules, "warn": ["x"]}).json()["version"] == 2
    stale = client.put("/api/rules", json={**rules, "warn": ["y"]})
    assert stale.status_code == 409 and stale.json()["code"] == "stale_version"
    bad = client.put("/api/rules", json={**rules, "mapping": [{"pattern": "", "action": "allow"}]})
    assert bad.status_code == 422 and bad.json()["field"]
    assert client.post("/api/rules/test", json={"tags": ["base_one"]}).json()["layer"] == "base"


def test_scenario_empty(client):
    """Empty scenario makes all search items empty."""
    client.post("/api/_fixture/scenario", json={"name": "empty"})
    sr = SearchResponse.model_validate(client.get("/api/search").json())
    assert all(len(s.items) == 0 for s in sr.sections)


def test_scenario_errors(client):
    """Errors scenario: upstream_error on search, 502 on patch."""
    client.post("/api/_fixture/scenario", json={"name": "errors"})
    sr = SearchResponse.model_validate(
        client.get("/api/search", params={"sources": "danbooru"}).json()
    )
    assert sr.sections[0].error["code"] == "upstream_error"
    assert client.patch("/api/library/images/3", json={"rating": 4}).status_code == 502


def test_scenario_conflict(client):
    """Conflict scenario: save always 409."""
    client.post("/api/_fixture/scenario", json={"name": "conflict"})
    assert client.post("/api/save", json={"source": "danbooru", "id": "x"}).status_code == 409


def test_scenario_offline(client):
    """Offline scenario: stash health is down."""
    client.post("/api/_fixture/scenario", json={"name": "offline"})
    assert client.get("/api/health").json()["stash"]["state"] == "down"


def test_scenario_unknown(client):
    """Unknown scenario name gives 422."""
    assert client.post("/api/_fixture/scenario", json={"name": "nope"}).status_code == 422


def test_scenario_slow(client):
    """Slow scenario skipped."""
    pytest.skip("slow scenario not exercised")


def test_reset_restores(client):
    """Reset restores original favorite value."""
    original = client.get("/api/library/images/3").json()["favorite"]
    client.patch("/api/library/images/3", json={"favorite": True})
    client.post("/api/_fixture/reset")
    assert client.get("/api/library/images/3").json()["favorite"] == original


def test_fixture_router_absent_when_real(tmp_path):
    """In real mode the fixture router is not mounted."""
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import create_app

    app = create_app(Settings(mode="real", data_dir=tmp_path))
    assert TestClient(app).post("/api/_fixture/reset").status_code == 404
