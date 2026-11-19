"""Group trash routes: POST /api/library/trash and POST /api/trash/group/{group}/restore."""

from fastapi.testclient import TestClient
from test_trash_stump import make, setup_lib, wait_for

from app.config import Settings
from app.main import create_app


def test_batch_delete_then_group_restore(tmp_path):
    folder, f1, f2, k = setup_lib(tmp_path)
    c = make(tmp_path, k)
    r = c.post(
        "/api/library/trash",
        json={"items": [{"kind": "book", "id": "B1"}, {"kind": "book", "id": "B2"}]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["results"]) == 2 and body["failed"] == []
    assert {x["item"]["group_id"] for x in body["results"]} == {body["group"]}
    assert not f1.exists() and not f2.exists()
    assert wait_for(lambda: len(k.cleaned) >= 1)
    r = c.post(f"/api/trash/group/{body['group']}/restore")
    assert r.status_code == 200, r.text
    assert len(r.json()["restored"]) == 2 and r.json()["failed"] == []
    assert f1.exists() and f2.exists()
    assert c.get("/api/trash").json()["items"] == []


def test_batch_lists_failures_and_skips_duplicates(tmp_path, caplog):
    _, f1, _, k = setup_lib(tmp_path)
    c = make(tmp_path, k)
    caplog.set_level("WARNING", logger="pearlie")
    r = c.post(
        "/api/library/trash",
        json={
            "items": [
                {"kind": "book", "id": "B1"},
                {"kind": "book", "id": "B1"},
                {"kind": "book", "id": "nope"},
                {"kind": "image", "id": "12"},
            ]
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["results"]) == 1
    assert [(f["kind"], f["id"]) for f in body["failed"]] == [("book", "nope"), ("image", "12")]
    assert body["failed"][1]["code"] == "not_configured"
    assert "trash refused kind=image id=12 code=not_configured" in caplog.text
    assert not f1.exists()


def test_batch_size_limits(tmp_path):
    _, _, _, k = setup_lib(tmp_path)
    c = make(tmp_path, k)
    assert c.post("/api/library/trash", json={"items": []}).status_code == 422
    many = [{"kind": "book", "id": str(i)} for i in range(51)]
    assert c.post("/api/library/trash", json={"items": many}).status_code == 422


def test_group_restore_unknown_is_404(tmp_path):
    _, _, _, k = setup_lib(tmp_path)
    c = make(tmp_path, k)
    assert c.post("/api/trash/group/missing/restore").status_code == 404


def test_fixture_batch_and_group_restore(tmp_path):
    c = TestClient(
        create_app(Settings(mode="fixture", db_path=tmp_path / "p.db", _env_file=None))  # pyright: ignore[reportCallIssue]
    )
    items = c.get("/api/library/stash/images").json()["items"][:2]
    ids = [{"kind": "image", "id": i["id"]} for i in items]
    r = c.post("/api/library/trash", json={"items": [*ids, {"kind": "image", "id": "zzz"}]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["results"]) == len(ids) and len(body["failed"]) == 1
    listed = c.get("/api/trash").json()["items"]
    assert {t["item"]["group_id"] for t in listed} >= {body["group"]}
    r = c.post(f"/api/trash/group/{body['group']}/restore")
    assert r.status_code == 200 and len(r.json()["restored"]) == len(ids)
    assert c.post(f"/api/trash/group/{body['group']}/restore").status_code == 404


def test_uuid_ids_trash_and_undo(tmp_path):
    """Stump ids are UUIDs with dashes; the live delete was refused as not_found (T-350)."""
    uid = "46d7fdf9-81aa-4dbe-b25c-8ad21ea4868f"
    _, f1, _, k = setup_lib(tmp_path)
    k.books[0]["id"] = uid
    c = make(tmp_path, k)
    r = c.post("/api/library/trash", json={"items": [{"kind": "book", "id": uid}]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["failed"] == [] and len(body["results"]) == 1
    assert not f1.exists()
    r = c.post(f"/api/trash/group/{body['group']}/restore")
    assert r.status_code == 200, r.text
    assert len(r.json()["restored"]) == 1 and r.json()["failed"] == []
    assert f1.exists()
