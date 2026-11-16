"""Komga trash layer through the routes: real files in tmp_path, mocked Komga REST."""

import json
import os
import time

import httpx
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import connect
from app.komga import Komga
from app.library.komga_trash import KomgaTrash
from app.main import create_app

URL = "http://komga.test"


class FakeKomga:
    """Komga with a scan that soft-deletes missing files and revives or re-adds found ones."""

    def __init__(self, lib, new_ids=False, fail_empty=None):
        self.lib = lib
        self.new_ids = new_ids
        self.fail_empty = fail_empty
        self.n = 100
        self.books: dict[str, dict] = {}
        self.series: dict[str, dict] = {}
        self.scans = 0
        self.empties = 0
        self.tag_calls: list[tuple[str, dict]] = []
        self.progress_calls: list[tuple[str, dict]] = []
        self.unreachable = False

    def add_series(self, sid, folder):
        self.series[sid] = {"id": sid, "libraryId": "L1", "name": folder.name, "url": str(folder),
                            "booksCount": 0, "booksReadCount": 0, "deleted": False,
                            "created": "2026-01-01T00:00:00",
                            "metadata": {"title": folder.name, "tags": ["a"]}, "booksMetadata": {}}

    def add_book(self, bid, sid, f, progress=None):
        self.books[bid] = {"id": bid, "seriesId": sid, "seriesTitle": "S", "libraryId": "L1",
                           "name": f.stem, "url": str(f), "deleted": False,
                           "created": "2026-01-01T00:00:00", "media": {"pagesCount": 10},
                           "metadata": {"title": f.stem, "tags": ["x", "y"]},
                           "readProgress": progress}
        self.series[sid]["booksCount"] += 1

    def _scan(self):
        self.scans += 1
        for d in [*self.books.values(), *self.series.values()]:
            if not d["deleted"] and not os.path.exists(d["url"]):
                d["deleted"] = True
        for d in [*self.books.values(), *self.series.values()]:
            if d["deleted"] and os.path.exists(d["url"]):
                if self.new_ids:
                    self.n += 1
                    store = self.books if d in self.books.values() else self.series
                    nd = dict(d, id=f"N{self.n}", deleted=False,
                              metadata={**d["metadata"], "tags": []}, readProgress=None)
                    store[nd["id"]] = nd
                else:
                    d["deleted"] = False
        if self.new_ids:
            self._discover()

    def _discover(self):
        known = {d["url"] for d in self.books.values()}
        for f in self.lib.rglob("*.cbz"):
            if str(f) in known:
                continue
            sid = next((k for k, d in self.series.items() if d["url"] == str(f.parent)), None)
            if sid is None:
                continue
            self.n += 1
            self.books[f"N{self.n}"] = {
                "id": f"N{self.n}", "seriesId": sid, "seriesTitle": "S", "libraryId": "L1",
                "name": f.stem, "url": str(f), "deleted": False, "created": "2026-01-01T00:00:00",
                "media": {"pagesCount": 10}, "metadata": {"title": f.stem, "tags": []},
                "readProgress": None,
            }

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if self.unreachable:
            raise httpx.ConnectError("down")
        path, method = request.url.path, request.method
        body = json.loads(request.content) if request.content else {}
        if path == "/api/v1/libraries":
            return httpx.Response(200, json=[{"id": "L1", "name": "L", "root": str(self.lib)}])
        if path == "/api/v1/libraries/L1/scan":
            self._scan()
            return httpx.Response(202)
        if path == "/api/v1/libraries/L1/empty-trash":
            if self.fail_empty:
                return httpx.Response(self.fail_empty)
            self.empties += 1
            for store in (self.books, self.series):
                for k in [k for k, d in store.items() if d["deleted"]]:
                    del store[k]
            return httpx.Response(202)
        for plural, store in (("books", self.books), ("series", self.series)):
            if path.startswith(f"/api/v1/{plural}/") and path.count("/") == 4 and method == "GET":
                d = store.get(path.rsplit("/", 1)[1])
                return httpx.Response(200, json=d) if d else httpx.Response(404)
            if path == f"/api/v1/{plural}/list":
                return httpx.Response(200, json=self._list(store, body))
            if path.startswith(f"/api/v1/{plural}/") and path.endswith("/metadata"):
                self.tag_calls.append((path, body))
                return httpx.Response(204)
        if path.endswith("/read-progress"):
            self.progress_calls.append((path, body))
            return httpx.Response(204)
        raise AssertionError(f"unexpected {method} {path}")

    @staticmethod
    def _list(store, body):
        cond = json.dumps(body.get("condition", {}))
        items = list(store.values())
        if "isTrue" in cond:
            items = [d for d in items if d["deleted"]]
        else:
            items = [d for d in items if not d["deleted"]]
        if '"seriesId"' in cond:
            sid = body["condition"]["seriesId"]["value"]
            items = [d for d in items if d.get("seriesId") == sid]
        return {"content": items, "last": True, "totalElements": len(items)}


def make(tmp_path, komga, wait=0.0):
    (tmp_path / "trash").mkdir(exist_ok=True)
    app = create_app(
        Settings(
            mode="real", real="library_komga", komga_url=URL,
            db_path=tmp_path / "p.db", static_dir=tmp_path / "nostatic",
            trash_dir=tmp_path / "trash", _env_file=None,  # pyright: ignore[reportCallIssue]
        )
    )
    app.state.komga = Komga(
        URL, "k", client=httpx.Client(base_url=URL, transport=httpx.MockTransport(komga))
    )
    app.state.komga_trash = KomgaTrash(
        app.state.settings, app.state.trash, app.state.komga,
        wait_s=lambda: wait, settle_timeout_s=2.0, poll_s=0.01,
    )
    return TestClient(app)


def setup_lib(tmp_path, komga_new_ids=False, **kw):
    lib = tmp_path / "lib"
    folder = lib / "Series A"
    folder.mkdir(parents=True)
    f1, f2 = folder / "one.cbz", folder / "two.cbz"
    f1.write_bytes(b"1")
    f2.write_bytes(b"2")
    k = FakeKomga(lib, new_ids=komga_new_ids, **kw)
    k.add_series("S1", folder)
    k.add_book("B1", "S1", f1, progress={"page": 4, "completed": False})
    k.add_book("B2", "S1", f2)
    return lib, folder, f1, f2, k


def wait_for(cond, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_delete_book_scans_then_empties(tmp_path):
    _, _, f1, f2, k = setup_lib(tmp_path)
    c = make(tmp_path, k)
    r = c.delete("/api/library/books/B1")
    assert r.status_code == 200
    assert r.json()["item"]["kind"] == "book"
    assert not f1.exists() and f2.exists()
    assert wait_for(lambda: k.empties == 1)
    assert k.scans == 1
    assert "B1" not in k.books and "B2" in k.books
    assert [i["token"] for i in c.get("/api/trash").json()["items"]] == [r.json()["token"]]


def test_scan_is_debounced(tmp_path):
    _, _, f1, f2, k = setup_lib(tmp_path)
    c = make(tmp_path, k, wait=0.3)
    assert c.delete("/api/library/books/B1").status_code == 200
    assert c.delete("/api/library/books/B2").status_code == 200
    assert k.scans == 0
    assert wait_for(lambda: k.empties == 1)
    assert k.scans == 1


def test_foreign_soft_deleted_item_blocks_empty_trash(tmp_path):
    _, folder, f1, _, k = setup_lib(tmp_path)
    other = folder / "offline.cbz"
    k.add_book("B9", "S1", other)  # file never existed: the scan soft-deletes it
    c = make(tmp_path, k)
    assert c.delete("/api/library/books/B1").status_code == 200
    assert wait_for(lambda: k.scans == 1)
    time.sleep(0.3)
    assert k.empties == 0
    assert k.books["B9"]["deleted"] is True
    # fallback: the trashed book is hidden from the list
    ids = [i["id"] for i in c.get("/api/library/komga/books").json()["items"]]
    assert "B1" not in ids and "B2" in ids
    assert c.get("/api/library/books/B1").status_code == 404


def test_empty_trash_403_falls_back_without_retry(tmp_path):
    _, _, _, _, k = setup_lib(tmp_path, fail_empty=403)
    c = make(tmp_path, k)
    assert c.delete("/api/library/books/B1").status_code == 200
    assert wait_for(lambda: k.scans == 1)
    time.sleep(0.3)
    assert k.empties == 0 and k.scans == 1
    ids = [i["id"] for i in c.get("/api/library/komga/books").json()["items"]]
    assert "B1" not in ids


def test_komga_down_rolls_back(tmp_path):
    _, _, f1, _, k = setup_lib(tmp_path)
    c = make(tmp_path, k)
    real_get = k.__call__

    def flaky(request):
        if request.url.path == "/api/v1/libraries" and getattr(flaky, "armed", False):
            raise httpx.ConnectError("down")
        return real_get(request)

    c.app.state.komga = Komga(
        URL, "k", client=httpx.Client(base_url=URL, transport=httpx.MockTransport(flaky))
    )
    c.app.state.komga_trash = KomgaTrash(
        c.app.state.settings, c.app.state.trash, c.app.state.komga,
        wait_s=lambda: 0.0, poll_s=0.01,
    )
    calls = {"n": 0}
    orig = c.app.state.komga_trash._check_under_library

    def arm(local):
        orig(local)
        flaky.armed = True  # type: ignore[attr-defined]
        calls["n"] += 1

    c.app.state.komga_trash._check_under_library = arm
    r = c.delete("/api/library/books/B1")
    assert r.status_code == 502
    assert f1.exists()
    assert c.get("/api/trash").json()["items"] == []


def test_restore_after_empty_trash_gets_new_id_with_tags_and_progress(tmp_path):
    _, _, f1, _, k = setup_lib(tmp_path, komga_new_ids=True)
    c = make(tmp_path, k)
    tok = c.delete("/api/library/books/B1").json()["token"]
    assert wait_for(lambda: k.empties == 1)
    r = c.post(f"/api/trash/{tok}/restore")
    assert r.status_code == 200, r.text
    new_id = r.json()["item"]["id"]
    assert new_id.startswith("N")
    assert f1.exists()
    assert ("/api/v1/books/%s/metadata" % new_id, {"tags": ["x", "y"], "tagsLock": True}) in k.tag_calls
    assert k.progress_calls == [(f"/api/v1/books/{new_id}/read-progress",
                                 {"page": 4, "completed": False})]
    assert c.get("/api/trash").json()["items"] == []


def test_restore_before_empty_trash_keeps_same_id(tmp_path):
    _, _, f1, _, k = setup_lib(tmp_path)
    c = make(tmp_path, k, wait=60.0)  # empty-trash has not run yet
    tok = c.delete("/api/library/books/B1").json()["token"]
    r = c.post(f"/api/trash/{tok}/restore")
    assert r.status_code == 200, r.text
    assert r.json()["item"]["id"] == "B1"
    assert f1.exists() and k.books["B1"]["deleted"] is False
    assert k.tag_calls and k.progress_calls
    assert k.empties == 0


def test_restoring_item_is_not_purged(tmp_path):
    _, _, _, _, k = setup_lib(tmp_path)
    c = make(tmp_path, k, wait=60.0)
    c.delete("/api/library/books/B1")
    k.books["B1"]["deleted"] = True
    assert c.app.state.komga_trash.foreign_deleted("L1") == 0
    # a soft-deleted item whose row is `restoring` is not ours any more
    c.app.state.trash._run("UPDATE trash_items SET state = 'restoring'")
    assert c.app.state.komga_trash.foreign_deleted("L1") == 1


def test_series_delete_moves_folder_and_empties(tmp_path):
    _, folder, f1, f2, k = setup_lib(tmp_path)
    c = make(tmp_path, k)
    r = c.delete("/api/library/series/S1")
    assert r.status_code == 200
    assert not folder.exists()
    assert wait_for(lambda: k.empties == 1)
    assert k.series == {} and k.books == {}
    tok = r.json()["token"]
    assert c.post(f"/api/trash/{tok}/restore").status_code in (200, 502)


def test_last_book_delete_owns_the_emptied_series(tmp_path):
    _, folder, f1, f2, k = setup_lib(tmp_path)
    c = make(tmp_path, k)
    c.delete("/api/library/books/B1")
    assert wait_for(lambda: k.empties == 1)
    c.delete("/api/library/books/B2")
    k.series["S1"]["deleted"] = True  # Komga drops the now empty series
    assert wait_for(lambda: k.empties == 2)


def test_dedupe_post_in_trash_is_409(tmp_path):
    _, _, f1, _, k = setup_lib(tmp_path)
    c = make(tmp_path, k)
    conn = connect(tmp_path / "p.db")
    conn.execute(
        "INSERT INTO saved_items (source, post_id, md5, target, image_id, library_id) "
        "VALUES ('nhentai','42','m','komga','','B1')"
    )
    conn.commit()
    conn.close()
    tok = c.delete("/api/library/books/B1").json()["token"]
    row = c.app.state.trash.find_in_trash("nhentai", "42")
    assert row is not None and row["token"] == tok
