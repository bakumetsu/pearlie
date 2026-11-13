"""Tests for the real jobs API."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import connect, init_db
from app.jobs.store import JobStore
from app.jobs.worker import JobWorker
from app.main import create_app
from app.sources.base import Post, SourceError


class FakeSource:
    def __init__(self, id: str) -> None:
        self.id = id
        self.target = "stash"
        self.file_hosts: tuple[str, ...] = ()
        self.posts: dict[str, Post] = {}
        self.calls: list[str] = []

    def get_post(self, pid: str) -> Post:
        self.calls.append(pid)
        if pid not in self.posts:
            raise SourceError("not_found", "post not found")
        return self.posts[pid]

    def search(self, *args: object, **kwargs: object) -> Any:
        raise NotImplementedError


def _make_post(source_id: str, pid: str) -> Post:
    return Post(
        source=source_id,
        post_id=pid,
        md5=pid * 32,
        file_url="https://x/y.jpg",
        preview_url="https://x/t.jpg",
        tags={"general": ["a_b", "c"]},
    )


def make_client(
    tmp_path: Path, **kwargs: object
) -> tuple[TestClient, dict[str, FakeSource], Path]:
    db_path = tmp_path / "p.db"
    init_db(db_path)
    settings = Settings(
        mode="real",
        real="jobs",
        db_path=db_path,
        static_dir=tmp_path / "nostatic",
        stash_url="http://stash.invalid",
        worker_enabled=False,
        _env_file=None,  # pyright: ignore[reportCallIssue]
        **kwargs,
    )
    app = create_app(settings)
    fake = FakeSource("danbooru")
    fake.posts["1"] = _make_post("danbooru", "1")
    fake.posts["2"] = _make_post("danbooru", "2")
    app.state.sources = {"danbooru": fake}
    return TestClient(app), {"danbooru": fake}, db_path


def test_save_ok(tmp_path: Path) -> None:
    client, _, _ = make_client(tmp_path)
    resp = client.post("/api/save", json={"source": "danbooru", "post_id": "1"})
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]
    resp2 = client.get(f"/api/jobs/{job_id}")
    assert resp2.status_code == 200
    body = resp2.json()
    assert body["state"] == "queued"
    assert body["source"] == "danbooru"
    assert body["target"] == "stash"
    assert body["notices"] == []


def test_save_twice_queued_same_id(tmp_path: Path) -> None:
    client, sources, _ = make_client(tmp_path)
    r1 = client.post("/api/save", json={"source": "danbooru", "post_id": "1"})
    r2 = client.post("/api/save", json={"source": "danbooru", "post_id": "1"})
    assert r1.status_code == 202
    assert r2.status_code == 202
    assert r1.json()["job_id"] == r2.json()["job_id"]
    assert sources["danbooru"].calls == ["1"]
    resp = client.get("/api/jobs")
    assert len(resp.json()["items"]) == 1


def test_save_unknown_post(tmp_path: Path) -> None:
    client, _, _ = make_client(tmp_path)
    resp = client.post("/api/save", json={"source": "danbooru", "post_id": "99"})
    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"


def test_save_source_unavailable(tmp_path: Path) -> None:
    client, _, _ = make_client(tmp_path)
    resp = client.post("/api/save", json={"source": "gelbooru", "post_id": "1"})
    assert resp.status_code == 422
    assert resp.json()["code"] == "source_unavailable"


def test_save_already_saved(tmp_path: Path) -> None:
    client, _, db_path = make_client(tmp_path)
    conn = connect(db_path)
    conn.execute(
        "INSERT INTO saved_items (source, post_id, md5, target, image_id) "
        "VALUES (?, ?, ?, ?, ?)",
        ("danbooru", "1", "abc", "stash", "42"),
    )
    conn.commit()
    conn.close()
    resp = client.post("/api/save", json={"source": "danbooru", "post_id": "1"})
    assert resp.status_code == 409
    assert resp.json()["code"] == "already_saved"
    assert resp.json()["library_ref"] == {"kind": "image", "id": "42"}


def test_save_stale_index_row_allowed(tmp_path: Path) -> None:
    client, _, db_path = make_client(tmp_path)
    conn = connect(db_path)
    conn.execute(
        "INSERT INTO saved_items (source, post_id, md5, target, image_id) "
        "VALUES (?, ?, ?, ?, ?)",
        ("danbooru", "1", "abc", "stash", "42"),
    )
    conn.commit()
    conn.close()
    seen: list[str] = []

    class Gone:
        def get_image(self, id: str) -> None:
            seen.append(id)
            return None

    client.app.state.stash_target._client = Gone()  # pyright: ignore[reportAttributeAccessIssue]
    resp = client.post("/api/save", json={"source": "danbooru", "post_id": "1"})
    assert resp.status_code == 202
    assert seen == ["42"]
    conn = connect(db_path)
    n = conn.execute("SELECT COUNT(*) FROM saved_items").fetchone()[0]
    conn.close()
    assert n == 0


def test_enqueue_race(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, db_path = make_client(tmp_path)
    store = JobStore(db_path)
    pre_id = store.enqueue(_make_post("danbooru", "1"), "stash", "t", "u")
    original = JobStore.active_job_id
    call_count: list[int] = []

    def fake_active(self: JobStore, source: str, post_id: str) -> str | None:
        call_count.append(1)
        if len(call_count) == 1:
            return None
        return original(self, source, post_id)

    monkeypatch.setattr(JobStore, "active_job_id", fake_active)
    resp = client.post("/api/save", json={"source": "danbooru", "post_id": "1"})
    assert resp.status_code == 202
    assert resp.json()["job_id"] == pre_id


def test_list_order_and_filter(tmp_path: Path) -> None:
    client, _, db_path = make_client(tmp_path)
    store = JobStore(db_path)
    client.post("/api/save", json={"source": "danbooru", "post_id": "1"})
    client.post("/api/save", json={"source": "danbooru", "post_id": "2"})
    jid3 = store.enqueue(_make_post("danbooru", "3"), "stash", "t", "u")
    store.finish(jid3, "failed", error="x", error_code="e")

    resp = client.get("/api/jobs")
    ids = [int(j["id"]) for j in resp.json()["items"]]
    assert ids == sorted(ids, reverse=True)

    resp_f = client.get("/api/jobs?state=failed")
    items_f = resp_f.json()["items"]
    assert len(items_f) == 1
    assert items_f[0]["id"] == jid3

    resp_qf = client.get("/api/jobs?state=queued,failed")
    assert len(resp_qf.json()["items"]) == 3

    resp_bad = client.get("/api/jobs?state=bogus")
    assert resp_bad.status_code == 422
    assert resp_bad.json()["code"] == "invalid"


def test_list_empty_state_means_all(tmp_path: Path) -> None:
    client, _, _ = make_client(tmp_path)
    client.post("/api/save", json={"source": "danbooru", "post_id": "1"})
    resp = client.get("/api/jobs?state=")
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 1


def test_get_unknown_job(tmp_path: Path) -> None:
    client, _, _ = make_client(tmp_path)
    resp = client.get("/api/jobs/999")
    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"
    resp2 = client.get("/api/jobs/abc")
    assert resp2.status_code == 404
    assert resp2.json()["code"] == "not_found"


def test_retry(tmp_path: Path) -> None:
    client, _, db_path = make_client(tmp_path)
    store = JobStore(db_path)
    jid = store.enqueue(_make_post("danbooru", "1"), "stash", "t", "u")
    store.finish(jid, "failed", error="x", error_code="e")

    resp = client.post(f"/api/jobs/{jid}/retry")
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "queued"
    assert body["error"] is None

    resp2 = client.post(f"/api/jobs/{jid}/retry")
    assert resp2.status_code == 409
    assert resp2.json()["code"] == "bad_state"

    resp3 = client.post("/api/jobs/999/retry")
    assert resp3.status_code == 404
    assert resp3.json()["code"] == "not_found"


def test_retry_conflicts_with_active_job(tmp_path: Path) -> None:
    client, _, db_path = make_client(tmp_path)
    store = JobStore(db_path)
    post = _make_post("danbooru", "1")
    old = store.enqueue(post, "stash", "t", "u")
    store.finish(old, "failed", error="x", error_code="e")
    store.enqueue(post, "stash", "t", "u")
    resp = client.post(f"/api/jobs/{old}/retry")
    assert resp.status_code == 409
    assert resp.json()["code"] == "bad_state"
    assert "already queued" in resp.json()["message"]
    j = store.get(old)
    assert j is not None
    assert j.state == "failed"


def test_delete(tmp_path: Path) -> None:
    client, _, db_path = make_client(tmp_path)
    store = JobStore(db_path)

    jid = store.enqueue(_make_post("danbooru", "1"), "stash", "t", "u")
    resp = client.delete(f"/api/jobs/{jid}")
    assert resp.status_code == 204
    resp2 = client.get(f"/api/jobs/{jid}")
    assert resp2.status_code == 404

    jid2 = store.enqueue(_make_post("danbooru", "2"), "stash", "t", "u")
    store.mark_running(jid2)
    resp3 = client.delete(f"/api/jobs/{jid2}")
    assert resp3.status_code == 409
    assert resp3.json()["code"] == "bad_state"

    resp4 = client.delete("/api/jobs/999")
    assert resp4.status_code == 404
    assert resp4.json()["code"] == "not_found"


def test_no_secrets(tmp_path: Path) -> None:
    client, _, _ = make_client(tmp_path, stash_api_key="SECRETKEY123")
    resp = client.post("/api/save", json={"source": "danbooru", "post_id": "1"})
    assert "SECRETKEY123" not in resp.text
    resp2 = client.get("/api/jobs")
    assert "SECRETKEY123" not in resp2.text


def test_create_app_no_stash_url_answers_503(tmp_path: Path) -> None:
    app = create_app(
        Settings(
            mode="real",
            real="jobs",
            db_path=tmp_path / "p.db",
            static_dir=tmp_path / "nostatic",
            stash_url="",
            _env_file=None,  # pyright: ignore[reportCallIssue]
        )
    )
    assert TestClient(app).get("/api/jobs").status_code == 503
    assert app.state.worker is not None
    assert app.state.stash is None


def test_worker_wake(tmp_path: Path) -> None:
    client, _, _ = make_client(tmp_path)
    assert isinstance(cast(FastAPI, client.app).state.worker, JobWorker)
    resp = client.post("/api/save", json={"source": "danbooru", "post_id": "1"})
    assert resp.status_code == 202


def test_save_komga_source_without_komga_target(tmp_path: Path) -> None:
    client, sources, _ = make_client(tmp_path)
    sources["danbooru"].target = "komga"
    resp = client.post("/api/save", json={"source": "danbooru", "post_id": "1"})
    assert resp.status_code == 422
    assert resp.json()["code"] == "no_target"


def test_save_komga_source_queues_with_title(tmp_path: Path) -> None:
    client, sources, _ = make_client(tmp_path)
    sources["danbooru"].target = "komga"
    sources["danbooru"].posts["1"].title = "Some Gallery"
    client.app.state.komga = object()  # type: ignore[attr-defined]
    resp = client.post("/api/save", json={"source": "danbooru", "post_id": "1"})
    assert resp.status_code == 202
    job = client.get(f"/api/jobs/{resp.json()['job_id']}").json()
    assert job["target"] == "komga"
    assert job["title"] == "Some Gallery"
