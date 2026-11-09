from io import BytesIO

import pytest
from PIL import Image

from app.fixtures.store import store
from app.models import (
    JobList,
    LibraryItem,
    LibraryItemDetail,
    Page,
    SearchResponse,
    TrashList,
    TrashResult,
    WebItem,
)


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
        "/api/library/komga/series",
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
    params = {"sort": "random"}
    c = [i["id"] for i in client.get("/api/library/stash/images", params=params).json()["items"]]
    d = [i["id"] for i in client.get("/api/library/stash/images", params=params).json()["items"]]
    assert c == d


def test_detail_and_404(client):
    """Detail endpoint validates; unknown ids and kinds give 404."""
    d = LibraryItemDetail.model_validate(client.get("/api/library/images/3").json())
    assert d.full_url
    LibraryItemDetail.model_validate(client.get("/api/library/series/0").json())
    r404 = client.get("/api/library/images/99999")
    assert r404.status_code == 404
    assert r404.json()["code"] == "not_found"
    assert client.get("/api/library/bogus/1").status_code == 404


def test_patch_round_trip(client):
    """PATCH fields persist; invalid values rejected."""
    client.patch(
        "/api/library/images/3",
        json={"rating": 4, "favorite": True, "tags": ["a", "b"]},
    )
    g = client.get("/api/library/images/3").json()
    assert g["rating"] == 4
    assert g["favorite"] is True
    assert [t["name"] for t in g["tags"]] == ["a", "b"]
    client.patch("/api/library/images/3", json={"rating": None})
    assert client.get("/api/library/images/3").json()["rating"] is None
    assert client.patch("/api/library/images/3", json={"rating": 9}).status_code == 422
    rb = client.patch("/api/library/images/3", json={"tags": [""]})
    assert rb.status_code == 422
    assert "tags" in rb.json()["field"]


def test_delete_restore(client):
    """Delete, verify 404s, restore, double-restore 404."""
    tr = TrashResult.model_validate(client.delete("/api/library/images/3").json())
    assert client.get("/api/library/images/3").status_code == 404
    assert client.get("/api/media/stash/images/3/thumb").status_code == 404
    assert client.post(f"/api/trash/{tr.token}/restore").status_code == 200
    assert client.get("/api/library/images/3").status_code == 200
    assert client.post(f"/api/trash/{tr.token}/restore").status_code == 404


def test_trash_list(client):
    """GET /api/trash lists deleted items newest-first with retention info."""
    assert client.get("/api/trash").json() == {"items": [], "retention_days": 7}
    client.delete("/api/library/images/3")
    client.delete("/api/library/images/4")
    tl = TrashList.model_validate(client.get("/api/trash").json())
    assert len(tl.items) == 2
    assert tl.items[0].item.id == "4"
    assert tl.items[1].item.id == "3"
    for entry in tl.items:
        assert entry.token
        assert entry.expires_at
        assert entry.item.title
    # restoring one removes it from the list
    client.post(f"/api/trash/{tl.items[0].token}/restore")
    tl2 = TrashList.model_validate(client.get("/api/trash").json())
    assert len(tl2.items) == 1
    assert tl2.items[0].item.id == "3"


def test_trash_expired_hidden_not_purged(client):
    """Expired trash entries are hidden from GET but not purged."""
    tr = TrashResult.model_validate(client.delete("/api/library/images/3").json())
    store.trash[tr.token]["expires"] = 0
    tl = TrashList.model_validate(client.get("/api/trash").json())
    assert len(tl.items) == 0
    assert tr.token in store.trash
    assert client.post(f"/api/trash/{tr.token}/restore").status_code == 404


def test_trash_empty(client):
    """DELETE /api/trash purges all entries and is idempotent."""
    tr1 = TrashResult.model_validate(client.delete("/api/library/images/3").json())
    client.delete("/api/library/images/4")
    resp = client.delete("/api/trash")
    assert resp.status_code == 200
    assert resp.json() == {"removed": 2}
    assert TrashList.model_validate(client.get("/api/trash").json()).items == []
    assert client.post(f"/api/trash/{tr1.token}/restore").status_code == 404
    assert client.delete("/api/trash").json() == {"removed": 0}


def test_trash_absent_when_real(tmp_path):
    """In real mode the trash endpoints are not mounted."""
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import create_app

    app = create_app(
        Settings(
            mode="real",
            db_path=tmp_path / "p.db",
            static_dir=tmp_path / "nostatic",
            _env_file=None,  # pyright: ignore[reportCallIssue]
        )
    )
    c = TestClient(app)
    assert c.get("/api/trash").status_code == 404
    assert c.delete("/api/trash").status_code == 404


def test_progress(client):
    """Page 99 on a 100-page book marks completed."""
    r = client.post("/api/library/komga/books/0/progress", json={"page": 99})
    assert r.status_code == 200
    assert r.json()["completed"] is True


def test_page_thumb_fixture(client):
    """Fixture page thumbnail returns a small JPEG with cache headers."""
    book_id = client.get("/api/library/komga/books").json()["items"][0]["id"]
    r = client.get(f"/api/media/komga/books/{book_id}/pages/1/thumb")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert r.headers["cache-control"] == "private, max-age=86400"
    img = Image.open(BytesIO(r.content))
    assert max(img.size) <= 200

    assert client.get(f"/api/media/komga/books/{book_id}/pages/0/thumb").status_code == 404
    assert client.get(f"/api/media/komga/books/{book_id}/pages/9999/thumb").status_code == 404
    assert client.get("/api/media/komga/books/nonexistent/pages/1/thumb").status_code == 404


def test_book_detail_page_thumb_url(client):
    """Fixture book detail exposes page_thumb_url with {n} and unchanged page_url."""
    book_id = client.get("/api/library/komga/books").json()["items"][0]["id"]
    d = client.get(f"/api/library/books/{book_id}").json()
    assert "{n}" in d["page_thumb_url"]
    assert d["page_url"] == f"/api/media/komga/books/{book_id}/pages/{{n}}"


def test_media_range(client):
    """Range request, cache headers, 404 on unknown, video skip."""
    r = client.get(
        "/api/media/stash/images/3/full",
        headers={"Range": "bytes=0-99"},
    )
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
    blocked = {
        (j["source"], j["post_id"]) for j in store.jobs.jobs if j["state"] in ("queued", "running")
    }
    web_items = [i for i in sr.sections[0].items if isinstance(i, WebItem)]
    target = next(i for i in web_items if not i.saved and ("danbooru", i.post_id) not in blocked)
    r = client.post(
        "/api/save",
        json={"source": "danbooru", "post_id": target.post_id},
    )
    assert r.status_code == 202
    assert client.get(f"/api/jobs/{r.json()['job_id']}").status_code == 200
    dup = client.post(
        "/api/save",
        json={"source": "danbooru", "post_id": target.post_id},
    )
    assert dup.status_code == 409
    assert dup.json()["code"] == "already_saved"


def test_save_rejected_422(client):
    """Saving a _rejected post returns 422 rejected_by_rule."""
    rejected = next(p for p in store.web["danbooru"] if "_rejected" in str(p))
    r = client.post(
        "/api/save",
        json={"source": "danbooru", "post_id": rejected["post_id"]},
    )
    assert r.status_code == 422
    assert r.json()["code"] == "rejected_by_rule"


def test_jobs_list_seed(client):
    """Seed: 20 jobs, filter, retry, delete semantics."""
    jl = JobList.model_validate(client.get("/api/jobs").json())
    assert len(jl.items) == 20
    jl_f = JobList.model_validate(client.get("/api/jobs", params={"state": "failed"}).json())
    assert len(jl_f.items) == 2
    assert all(j.state == "failed" for j in jl_f.items)
    assert client.post(f"/api/jobs/{jl_f.items[0].id}/retry").json()["state"] == "queued"
    after = JobList.model_validate(client.get("/api/jobs").json())
    assert len(after.items) == 20
    assert len({j.id for j in after.items}) == 20
    done = next(j for j in jl.items if j.state == "done")
    assert client.post(f"/api/jobs/{done.id}/retry").status_code == 409
    assert client.delete(f"/api/jobs/{done.id}").status_code == 204
    running = next(j for j in jl.items if j.state == "running")
    assert client.delete(f"/api/jobs/{running.id}").status_code == 409


def test_rules_flow(client):
    """Versioning, stale conflict, validation, test endpoint."""
    rules = client.get("/api/rules").json()
    assert rules["version"] == 1
    assert rules["base_list"]["read_only"] is True
    assert (client.put("/api/rules", json={**rules, "warn": ["x"]}).json())["version"] == 2
    stale = client.put("/api/rules", json={**rules, "warn": ["y"]})
    assert stale.status_code == 409
    assert stale.json()["code"] == "stale_version"
    bad = client.put(
        "/api/rules",
        json={
            **rules,
            "mapping": [{"pattern": "", "action": "allow"}],
        },
    )
    assert bad.status_code == 422
    assert bad.json()["field"]
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
    err = sr.sections[0].error
    assert err is not None
    assert err.code == "upstream_error"
    assert client.patch("/api/library/images/3", json={"rating": 4}).status_code == 502


def test_scenario_conflict(client):
    """Conflict scenario: save always 409."""
    client.post("/api/_fixture/scenario", json={"name": "conflict"})
    assert client.post("/api/save", json={"source": "danbooru", "post_id": "x"}).status_code == 409


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

    app = create_app(
        Settings(
            mode="real",
            db_path=tmp_path / "p.db",
            static_dir=tmp_path / "nostatic",
            _env_file=None,  # pyright: ignore[reportCallIssue]
        )
    )
    assert TestClient(app).post("/api/_fixture/reset").status_code == 404
