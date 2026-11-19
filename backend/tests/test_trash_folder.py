"""Options trash folder: status, save checks, create, reset, runtime pickup."""

import errno
import os
from pathlib import Path

from fastapi.testclient import TestClient

from app.bookserver.stump import StumpBookServer
from app.config import Settings
from app.library.stump_trash import StumpTrash
from app.main import create_app
from app.targets.stash_client import StashClient, StashError
from tests.test_trash_stash import FakeStash, lib_file, make, one_file


class FakeStump:
    def __init__(self, root):
        self.root = root

    def list_libraries(self):
        return [{"id": "L1", "name": "Lib", "path": str(self.root), "config": {}}]


def put(c: TestClient, path: str):
    return c.put("/api/trash/folder", json={"path": path})


def test_get_env_source_and_missing_state(tmp_path):
    lib, _ = lib_file(tmp_path)
    c = make(tmp_path, FakeStash(lib, []))
    body = c.get("/api/trash/folder").json()
    assert body == {"path": str(tmp_path / "trash"), "source": "env",
                    "env_path": str(tmp_path / "trash"), "state": "ok", "items": 0}
    (tmp_path / "trash").rmdir()
    assert c.get("/api/trash/folder").json()["state"] == "missing"


def test_get_not_writable(tmp_path, monkeypatch):
    lib, _ = lib_file(tmp_path)
    c = make(tmp_path, FakeStash(lib, []))
    monkeypatch.setattr(os, "access", lambda p, m: False)
    assert c.get("/api/trash/folder").json()["state"] == "not_writable"


def test_put_ok_stores_and_next_move_uses_new_dir(tmp_path):
    lib, f = lib_file(tmp_path)
    c = make(tmp_path, FakeStash(lib, [one_file(f)]))
    new = tmp_path / "newtrash"
    new.mkdir()
    r = put(c, str(new))
    assert r.status_code == 200
    assert r.json()["source"] == "stored"
    assert r.json()["path"] == str(new)
    assert c.get("/api/trash/folder").json()["path"] == str(new)
    token = c.delete("/api/library/images/1").json()["token"]
    assert (new / token).is_dir()
    assert list((tmp_path / "trash").iterdir()) == []


def test_put_blocked_while_trash_has_items_then_ok(tmp_path):
    lib, f = lib_file(tmp_path)
    c = make(tmp_path, FakeStash(lib, [one_file(f)]))
    token = c.delete("/api/library/images/1").json()["token"]
    new = tmp_path / "newtrash"
    new.mkdir()
    r = put(c, str(new))
    assert r.status_code == 409
    assert r.json()["code"] == "trash_not_empty"
    assert c.get("/api/trash/folder").json()["items"] == 1
    assert c.delete(f"/api/trash/{token}").status_code == 204
    assert put(c, str(new)).status_code == 200


def test_put_rejects_relative_and_missing(tmp_path):
    lib, _ = lib_file(tmp_path)
    c = make(tmp_path, FakeStash(lib, []))
    r = put(c, "relative/dir")
    assert (r.status_code, r.json()["code"]) == (422, "invalid_path")
    r = put(c, str(tmp_path / "nope"))
    assert (r.status_code, r.json()["code"]) == (422, "folder_missing")
    assert c.get("/api/trash/folder").json()["source"] == "env"


def test_put_not_writable(tmp_path, monkeypatch):
    lib, _ = lib_file(tmp_path)
    c = make(tmp_path, FakeStash(lib, []))
    new = tmp_path / "ro"
    new.mkdir()
    real = os.access
    monkeypatch.setattr(os, "access", lambda p, m: False if str(p) == str(new) else real(p, m))
    r = put(c, str(new))
    assert (r.status_code, r.json()["code"]) == (422, "not_writable")


def test_put_inside_stash_root(tmp_path):
    lib, _ = lib_file(tmp_path)
    c = make(tmp_path, FakeStash(lib, []))
    inner = lib / "trash"
    inner.mkdir()
    for p in (lib, inner):
        r = put(c, str(p))
        assert (r.status_code, r.json()["code"]) == (422, "inside_library")


def test_put_inside_stump_root(tmp_path):
    lib, _ = lib_file(tmp_path)
    c = make(tmp_path, FakeStash(lib, []))
    kroot = tmp_path / "stump"
    inner = kroot / "x"
    inner.mkdir(parents=True)
    fake = FakeStump(kroot)
    c.app.state.stump = fake  # pyright: ignore[reportAttributeAccessIssue]
    c.app.state.settings.stump_url = "http://stump.test"  # pyright: ignore[reportAttributeAccessIssue]
    c.app.state.books = StumpBookServer(fake, None)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
    c.app.state.stump_conn = ("http://stump.test", "")  # pyright: ignore[reportAttributeAccessIssue]
    c.app.state.stump_trash = StumpTrash(  # pyright: ignore[reportAttributeAccessIssue]
        c.app.state.settings, c.app.state.trash, fake, wait_s=lambda: 0.0  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
    )
    r = put(c, str(inner))
    assert (r.status_code, r.json()["code"]) == (422, "inside_library")


def test_put_other_volume(tmp_path, monkeypatch):
    lib, _ = lib_file(tmp_path)
    c = make(tmp_path, FakeStash(lib, []))
    new = tmp_path / "newtrash"
    new.mkdir()
    real = os.rename

    def fake(src, dst):
        if ".pearlie-probe-" in str(dst) and "newtrash" in str(dst):
            raise OSError(errno.EXDEV, "cross")
        return real(src, dst)

    monkeypatch.setattr(os, "rename", fake)
    r = put(c, str(new))
    assert (r.status_code, r.json()["code"]) == (422, "other_volume")
    assert list(lib.glob(".pearlie-probe-*")) == []


def test_put_empty_resets_to_env(tmp_path):
    lib, _ = lib_file(tmp_path)
    c = make(tmp_path, FakeStash(lib, []))
    new = tmp_path / "newtrash"
    new.mkdir()
    put(c, str(new))
    r = put(c, "")
    assert r.status_code == 200
    assert (r.json()["source"], r.json()["path"]) == ("env", str(tmp_path / "trash"))


def test_put_empty_blocked_with_items(tmp_path):
    lib, f = lib_file(tmp_path)
    c = make(tmp_path, FakeStash(lib, [one_file(f)]))
    new = tmp_path / "newtrash"
    new.mkdir()
    put(c, str(new))
    c.delete("/api/library/images/1")
    r = put(c, "")
    assert (r.status_code, r.json()["code"]) == (409, "trash_not_empty")


def test_create_makes_nested_and_does_not_save(tmp_path):
    lib, _ = lib_file(tmp_path)
    c = make(tmp_path, FakeStash(lib, []))
    new = tmp_path / "a" / "b"
    r = c.post("/api/trash/folder/create", json={"path": str(new)})
    assert r.status_code == 200
    assert new.is_dir()
    assert r.json()["path"] == str(tmp_path / "trash")
    assert put(c, str(new)).status_code == 200


def test_create_current_when_body_empty(tmp_path):
    lib, _ = lib_file(tmp_path)
    c = make(tmp_path, FakeStash(lib, []))
    (tmp_path / "trash").rmdir()
    r = c.post("/api/trash/folder/create", json={})
    assert r.json()["state"] == "ok"


def test_create_failure_and_relative(tmp_path, monkeypatch):
    lib, _ = lib_file(tmp_path)
    c = make(tmp_path, FakeStash(lib, []))
    r = c.post("/api/trash/folder/create", json={"path": "rel"})
    assert r.json()["code"] == "invalid_path"

    def deny(self, *a, **kw):
        raise PermissionError(13, "denied")

    monkeypatch.setattr(Path, "mkdir", deny)
    r = c.post("/api/trash/folder/create", json={"path": str(tmp_path / "zz")})
    assert (r.status_code, r.json()["code"]) == (422, "cannot_create")


def test_stash_down_is_502_and_no_change(tmp_path, monkeypatch):
    lib, _ = lib_file(tmp_path)
    c = make(tmp_path, FakeStash(lib, []))
    new = tmp_path / "newtrash"
    new.mkdir()

    def boom(self):
        raise StashError("unreachable", "down")

    monkeypatch.setattr(StashClient, "library_paths", boom)
    r = put(c, str(new))
    assert r.status_code == 502
    monkeypatch.undo()
    assert c.get("/api/trash/folder").json()["source"] == "env"


def test_start_uses_stored_path_over_env(tmp_path):
    lib, _ = lib_file(tmp_path)
    c = make(tmp_path, FakeStash(lib, []))
    new = tmp_path / "stored"
    new.mkdir()
    assert put(c, str(new)).status_code == 200
    app2 = create_app(Settings(
        mode="real", real="library_stash", stash_url="http://stash.test",
        db_path=tmp_path / "p.db", static_dir=tmp_path / "nostatic",
        trash_dir=tmp_path / "trash", _env_file=None,  # pyright: ignore[reportCallIssue]
    ))
    assert app2.state.trash.dir == new


def test_fixture_mode_has_no_folder_route(tmp_path):
    app = create_app(Settings(
        mode="fixture", db_path=tmp_path / "p.db", static_dir=tmp_path / "nostatic",
        _env_file=None,  # pyright: ignore[reportCallIssue]
    ))
    with TestClient(app) as c:
        assert c.get("/api/trash/folder").status_code in (404, 405, 422)


def test_stored_path_inside_temp_dir_still_starts(tmp_path):
    lib, _ = lib_file(tmp_path)
    c = make(tmp_path, FakeStash(lib, []))
    temp = tmp_path / "stashtemp"
    inner = temp / "trash"
    inner.mkdir(parents=True)
    assert put(c, str(inner)).status_code == 200
    app2 = create_app(Settings(
        mode="real", real="library_stash", stash_url="http://stash.test",
        db_path=tmp_path / "p.db", static_dir=tmp_path / "nostatic",
        trash_dir=tmp_path / "trash", stash_temp_dir=temp, _env_file=None,  # pyright: ignore[reportCallIssue]
    ))
    assert app2.state.trash.dir == inner
