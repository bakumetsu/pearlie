"""Stash trash layer through the routes: real files, mocked Stash GraphQL."""

import json
from typing import Any, cast

import httpx
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import connect
from app.main import create_app
from app.targets.stash_client import StashClient

URL = "http://stash.test"


class FakeStash:
    """Answers the GraphQL calls the trash layer makes; records the destroys."""

    def __init__(self, lib, files, fail_destroy=False):
        self.lib = lib
        self.files = files
        self.fail_destroy = fail_destroy
        self.destroyed = []
        self.exists = True

    def __call__(self, request: httpx.Request) -> httpx.Response:
        q = json.loads(request.content)["query"]
        if "stashes" in q:
            data = {"configuration": {"general": {"stashes": [{"path": str(self.lib)}]}}}
        elif "findImage(id" in q and "visual_files" in q:
            data = {"findImage": {"id": "1", "title": "T", "visual_files": self.files,
                                  "tags": [], "performers": [], "galleries": [], "urls": []}
                    if self.exists else None}
        elif "findImage(id" in q:
            data = {"findImage": None}
        elif "imageDestroy" in q:
            if self.fail_destroy:
                return httpx.Response(200, json={"errors": [{"message": "boom"}]})
            self.destroyed.append("image")
            self.exists = False
            data = {"imageDestroy": True}
        else:
            raise AssertionError("unexpected query: " + q[:80])
        return httpx.Response(200, json={"data": data})


def make(tmp_path, stash):
    (tmp_path / "trash").mkdir(exist_ok=True)
    app = create_app(
        Settings(
            mode="real", real="library_stash", stash_url=URL,
            db_path=tmp_path / "p.db", static_dir=tmp_path / "nostatic",
            trash_dir=tmp_path / "trash", _env_file=None,  # pyright: ignore[reportCallIssue]
        )
    )
    app.state.stash = StashClient(
        URL, "k", client=httpx.Client(base_url=URL, transport=httpx.MockTransport(stash))
    )
    return TestClient(app)


def lib_file(tmp_path, name="a.jpg"):
    lib = tmp_path / "lib"
    lib.mkdir(exist_ok=True)
    f = lib / name
    f.write_bytes(b"data")
    return lib, f


def one_file(f, **over):
    d = {"path": str(f), "size": 4, "zip_file": None,
         "fingerprints": [{"type": "md5", "value": "ABC"}]}
    d.update(over)
    return d


def test_delete_moves_file_and_lists_in_trash(tmp_path):
    lib, f = lib_file(tmp_path)
    stash = FakeStash(lib, [one_file(f)])
    c = make(tmp_path, stash)
    r = c.delete("/api/library/images/1")
    assert r.status_code == 200
    body = r.json()
    assert body["item"]["kind"] == "image"
    assert body["retention_days"] == 7
    assert not f.exists()
    assert stash.destroyed == ["image"]
    listed = c.get("/api/trash").json()
    assert [i["token"] for i in listed["items"]] == [body["token"]]


def test_destroy_failure_puts_file_back(tmp_path):
    lib, f = lib_file(tmp_path)
    c = make(tmp_path, FakeStash(lib, [one_file(f)], fail_destroy=True))
    r = c.delete("/api/library/images/1")
    assert r.status_code >= 400
    assert f.exists()
    assert c.get("/api/trash").json()["items"] == []


def test_multi_file_is_refused(tmp_path):
    lib, f = lib_file(tmp_path)
    stash = FakeStash(lib, [one_file(f), one_file(f)])
    c = make(tmp_path, stash)
    r = c.delete("/api/library/images/1")
    assert r.status_code == 422
    assert r.json()["code"] == "multi_file"
    assert f.exists()
    assert stash.destroyed == []


def test_file_in_archive_is_refused(tmp_path):
    lib, f = lib_file(tmp_path)
    c = make(tmp_path, FakeStash(lib, [one_file(f, zip_file={"id": "9"})]))
    r = c.delete("/api/library/images/1")
    assert r.status_code == 422
    assert r.json()["code"] == "in_archive"
    assert f.exists()


def test_file_outside_library_is_refused(tmp_path):
    lib, _ = lib_file(tmp_path)
    other = tmp_path / "other.jpg"
    other.write_bytes(b"x")
    c = make(tmp_path, FakeStash(lib, [one_file(other)]))
    r = c.delete("/api/library/images/1")
    assert r.status_code == 422
    assert r.json()["code"] == "path_outside_library"
    assert other.exists()


def test_delete_twice_is_409_while_trashed(tmp_path):
    lib, f = lib_file(tmp_path)
    stash = FakeStash(lib, [one_file(f)])
    c = make(tmp_path, stash)
    c.delete("/api/library/images/1")
    stash.exists = True  # Stash still answers, e.g. a stale id
    r = c.delete("/api/library/images/1")
    assert r.status_code == 409
    assert r.json()["code"] == "already_trashed"


def test_delete_for_good_and_empty_routes(tmp_path):
    lib, f = lib_file(tmp_path)
    c = make(tmp_path, FakeStash(lib, [one_file(f)]))
    token = c.delete("/api/library/images/1").json()["token"]
    assert c.delete(f"/api/trash/{token}").status_code == 204
    assert c.delete(f"/api/trash/{token}").status_code == 404
    assert c.delete("/api/trash").json()["removed"] == 0
    assert not (tmp_path / "trash" / token).exists()


def test_restore_unknown_token_is_404(tmp_path):
    lib, f = lib_file(tmp_path)
    c = make(tmp_path, FakeStash(lib, [one_file(f)]))
    assert c.post("/api/trash/nope/restore").status_code == 404


def test_drop_if_gone_keeps_trashed_row(tmp_path):
    lib, f = lib_file(tmp_path)
    c = make(tmp_path, FakeStash(lib, [one_file(f)]))
    conn = connect(tmp_path / "p.db")
    conn.execute(
        "INSERT INTO saved_items (source, post_id, md5, target, image_id, kind) "
        "VALUES ('gelbooru','55','abc','stash','1','image')"
    )
    conn.commit()
    conn.close()
    c.delete("/api/library/images/1")
    # Stash no longer knows id 1 (destroyed); the saved row must stay while trashed.
    assert cast(Any, c.app).state.stash_target.drop_if_gone("1") is False
    conn = connect(tmp_path / "p.db")
    n = conn.execute("SELECT COUNT(*) FROM saved_items WHERE image_id = '1'").fetchone()[0]
    conn.close()
    assert n == 1
