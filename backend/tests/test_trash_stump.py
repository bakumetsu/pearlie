"""Stump trash layer through the routes: real files in tmp_path, mocked Stump GraphQL."""

import os
import time
from pathlib import Path
from typing import Any

import httpx
from fastapi.testclient import TestClient

from app.bookserver.stump import StumpBookServer
from app.config import Settings
from app.library.stump_trash import StumpTrash
from app.main import create_app
from app.stump import Stump
from tests import stump_mock

URL = "http://stump.test"
KEY = "stump-secret-key"


class FsStump(stump_mock.MockStump):
    """A Stump whose scan marks books with a missing file MISSING, revives found ones and
    adds unknown files under a new id."""

    def __init__(self, lib_dir: Path, folder: Path) -> None:
        lib = stump_mock.lib()
        lib["path"] = str(lib_dir)
        series = stump_mock.series()
        series.update(path=folder.as_posix(), mediaCount=2)
        super().__init__([lib], [series], [])
        self.lib_dir = lib_dir
        self.n = 100
        self.fail_clean = False

    def add_file(self, i: int, f: Path, progress: dict | None = None) -> None:
        b = stump_mock.book(i)
        b.update(id=f"B{i}", path=f.as_posix(), name=f.stem, readProgress=progress)
        self.books.append(b)

    def _gql(self, body: dict) -> httpx.Response:
        if body["operationName"] == "ScanLibrary":
            self._scan()
        if body["operationName"] == "CleanLibrary" and self.fail_clean:
            return httpx.Response(200, json={"errors": [{"message": "denied"}]})
        return super()._gql(body)

    def _scan(self) -> None:
        for b in self.books:
            exists = os.path.exists(b["path"])
            if not exists:
                b["status"] = "MISSING"
            elif b["status"] == "MISSING":
                b["status"] = "READY"
        known = {b["path"] for b in self.books}
        for f in sorted(self.lib_dir.rglob("*.cbz")):
            if f.as_posix() not in known:
                self.n += 1
                self.add_file(self.n, f)
                self.books[-1].update(id=f"N{self.n}", tags=[], readProgress=None)


def make(tmp_path, mock, wait=0.0, **extra):
    (tmp_path / "trash").mkdir(exist_ok=True)
    app = create_app(
        Settings(
            mode="real",
            real="library_stump",
            stump_url=URL,
            stump_api_key=KEY,  # pyright: ignore[reportArgumentType]
            db_path=tmp_path / "p.db",
            static_dir=tmp_path / "nostatic",
            trash_dir=tmp_path / "trash",
            _env_file=None,  # pyright: ignore[reportCallIssue]
            **extra,
        )
    )
    http = httpx.Client(base_url=URL, transport=httpx.MockTransport(mock))
    adapter = StumpBookServer(Stump(URL, KEY, http, sleep=lambda _s: None))
    state: Any = app.state
    state.books = adapter
    state.stump_conn = (URL, KEY)
    state.stump_trash = StumpTrash(
        state.settings,
        state.trash,
        adapter,
        wait_s=lambda: wait,
        settle_timeout_s=2.0,
        poll_s=0.01,
        restore_timeout_s=2.0,
    )
    return TestClient(app)


def setup_lib(tmp_path):
    lib = tmp_path / "lib"
    folder = lib / "Series A"
    folder.mkdir(parents=True)
    f1, f2 = folder / "one.cbz", folder / "two.cbz"
    f1.write_bytes(b"1")
    f2.write_bytes(b"2")
    m = FsStump(lib, folder)
    m.add_file(1, f1, progress={"page": 4})
    m.add_file(2, f2)
    return folder, f1, f2, m


def wait_for(cond, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_delete_moves_file_then_scan_and_clean_library(tmp_path):
    _, f1, f2, m = setup_lib(tmp_path)
    c = make(tmp_path, m)
    r = c.delete("/api/library/books/B1")
    assert r.status_code == 200, r.text
    assert not f1.exists() and f2.exists()
    assert wait_for(lambda: m.cleaned == ["L1"])
    assert m.scanned == ["L1"]
    assert [b["id"] for b in m.books] == ["B2"]
    assert [i["token"] for i in c.get("/api/trash").json()["items"]] == [r.json()["token"]]
    state: Any = c.app.state  # pyright: ignore[reportAttributeAccessIssue]
    assert state.trash.get(r.json()["token"])["target"] == "stump"


def test_few_foreign_missing_items_still_clean_library(tmp_path):
    folder, _, _, m = setup_lib(tmp_path)
    m.add_file(9, folder / "offline.cbz")  # never on disk: the scan marks it MISSING
    c = make(tmp_path, m)
    assert c.delete("/api/library/books/B1").status_code == 200
    assert wait_for(lambda: m.cleaned == ["L1"])
    assert {b["id"] for b in m.books} == {"B2"}


def test_many_foreign_missing_items_block_clean_library(tmp_path):
    folder, _, _, m = setup_lib(tmp_path)
    m.add_file(9, folder / "offline.cbz")
    m.add_file(8, folder / "offline2.cbz")
    c = make(tmp_path, m, stump_clean_max_foreign=1)
    assert c.delete("/api/library/books/B1").status_code == 200
    assert wait_for(lambda: m.scanned == ["L1"])
    time.sleep(0.3)
    assert m.cleaned == []
    assert {b["id"] for b in m.books if b["status"] == "MISSING"} == {"B1", "B8", "B9"}


def test_trashed_book_is_hidden_from_search_section(tmp_path):
    _, _, _, m = setup_lib(tmp_path)
    c = make(tmp_path, m, wait=60.0)  # scan has not run: Stump still lists B1 as READY
    assert c.delete("/api/library/books/B1").status_code == 200
    r = c.get("/api/search", params={"sources": "stump_books"})
    assert r.status_code == 200, r.text
    ids = [i["id"] for i in r.json()["sections"][0]["items"]]
    assert "B1" not in ids and "B2" in ids


def test_clean_library_failure_keeps_items_and_does_not_retry(tmp_path):
    _, _, _, m = setup_lib(tmp_path)
    m.fail_clean = True
    c = make(tmp_path, m)
    assert c.delete("/api/library/books/B1").status_code == 200
    assert wait_for(lambda: m.scanned == ["L1"])
    time.sleep(0.3)
    assert m.scanned == ["L1"]
    assert c.get("/api/trash").json()["items"] != []


def test_restore_after_clean_remaps_id_and_restores_tags_progress(tmp_path):
    _, f1, _, m = setup_lib(tmp_path)
    c = make(tmp_path, m)
    tok = c.delete("/api/library/books/B1").json()["token"]
    assert wait_for(lambda: m.cleaned == ["L1"])
    r = c.post(f"/api/trash/{tok}/restore")
    assert r.status_code == 200, r.text
    new_id = r.json()["item"]["id"]
    assert new_id.startswith("N")
    assert f1.exists()
    new = next(b for b in m.books if b["id"] == new_id)
    assert [t["name"] for t in new["tags"]] == ["x"]
    assert new["readProgress"] == {"page": 4}
    assert [(op, i) for op, i, _f in m.locks] == [("setMediaLockedFields", new_id)]
    assert "TAGS" in m.locks[0][2]
    assert c.get("/api/trash").json()["items"] == []


def test_restore_before_clean_keeps_same_id(tmp_path):
    _, f1, _, m = setup_lib(tmp_path)
    c = make(tmp_path, m, wait=60.0)  # cleanLibrary has not run yet
    tok = c.delete("/api/library/books/B1").json()["token"]
    r = c.post(f"/api/trash/{tok}/restore")
    assert r.status_code == 200, r.text
    assert r.json()["item"]["id"] == "B1"
    assert f1.exists() and next(b for b in m.books if b["id"] == "B1")["status"] == "READY"
    assert m.cleaned == []


def test_startup_repair_has_a_stump_destroyer(tmp_path):
    import asyncio

    from app.db import connect
    from app.main import _trash_purge_loop

    _, _, _, m = setup_lib(tmp_path)
    c = make(tmp_path, m, wait=60.0)
    token = c.delete("/api/library/books/B1").json()["token"]
    state: Any = c.app.state  # pyright: ignore[reportAttributeAccessIssue]
    conn = connect(state.settings.db_path)
    conn.execute("UPDATE trash_items SET state='moving' WHERE token=?", (token,))
    conn.commit()
    conn.close()
    called: list[str] = []
    state.stump_trash.destroy_row = lambda row: called.append(row["token"])

    async def run() -> None:
        task = asyncio.create_task(_trash_purge_loop(c.app))  # pyright: ignore[reportArgumentType]
        await asyncio.sleep(0.3)
        task.cancel()

    asyncio.run(run())
    assert called == [token]
    assert state.trash.get(token)["state"] == "trashed"


def test_restore_of_a_komga_era_row_moves_the_file_back_and_scans(tmp_path):
    """A row written under Komga (unknown book and library ids) restores as a file."""
    import json

    from app.db import connect
    from app.legacy import migrate_komga

    _, f1, _, m = setup_lib(tmp_path)
    c = make(tmp_path, m, wait=60.0)
    tok = c.delete("/api/library/books/B1").json()["token"]
    state: Any = c.app.state  # pyright: ignore[reportAttributeAccessIssue]
    db = state.settings.db_path
    conn = connect(db)
    row = conn.execute("SELECT meta FROM trash_items WHERE token=?", (tok,)).fetchone()
    meta = json.loads(row["meta"])
    meta["library_id"] = "komga-lib-7"
    conn.execute(
        "UPDATE trash_items SET target='komga', entity_id='komga-book-9', meta=? WHERE token=?",
        (json.dumps(meta), tok),
    )
    conn.commit()
    conn.close()
    migrate_komga(db)
    m.scanned.clear()
    r = c.post(f"/api/trash/{tok}/restore")
    assert r.status_code == 200, r.text
    assert f1.exists()
    assert m.scanned == ["L1"]
    assert c.get("/api/trash").json()["items"] == []


BOOK_ID = "3f2b8c1e-5a47-4d9e-9c1a-7e6d2b4f8a10"
SERIES_ID = "9a1d6e52-0c3b-4f87-b2e4-5d8a7c3f1e69"


def one_book_lib(tmp_path, in_root=False):
    """A library whose only series holds one book (real-shaped dashed UUID ids)."""
    lib = tmp_path / "lib"
    folder = lib if in_root else lib / "Series A"
    folder.mkdir(parents=True)
    f1 = folder / "one.cbz"
    f1.write_bytes(b"1")
    m = FsStump(lib, folder)
    m.series[0].update(id=SERIES_ID, mediaCount=1)
    m.add_file(1, f1)
    m.books[0].update(id=BOOK_ID, seriesId=SERIES_ID)
    return folder, f1, m


def test_last_book_removes_the_empty_series_folder_then_scans(tmp_path):
    folder, f1, m = one_book_lib(tmp_path)
    c = make(tmp_path, m)
    assert c.delete(f"/api/library/books/{BOOK_ID}").status_code == 200
    assert not folder.exists() and (tmp_path / "lib").is_dir()
    assert wait_for(lambda: m.scanned == ["L1"])


def test_series_with_books_left_keeps_its_folder(tmp_path):
    folder, _, _, m = setup_lib(tmp_path)
    c = make(tmp_path, m)
    assert c.delete("/api/library/books/B1").status_code == 200
    assert folder.is_dir()


def test_folder_with_another_file_is_kept(tmp_path):
    folder, _, m = one_book_lib(tmp_path)
    (folder / ".hidden").write_bytes(b"x")
    c = make(tmp_path, m)
    assert c.delete(f"/api/library/books/{BOOK_ID}").status_code == 200
    assert folder.is_dir() and (folder / ".hidden").exists()


def test_library_root_is_never_removed(tmp_path):
    folder, f1, m = one_book_lib(tmp_path, in_root=True)
    c = make(tmp_path, m)
    assert c.delete(f"/api/library/books/{BOOK_ID}").status_code == 200
    assert not f1.exists() and folder.is_dir()


def test_restore_recreates_the_series_folder_and_the_book(tmp_path):
    folder, f1, m = one_book_lib(tmp_path)
    c = make(tmp_path, m)
    tok = c.delete(f"/api/library/books/{BOOK_ID}").json()["token"]
    assert not folder.exists()
    r = c.post(f"/api/trash/{tok}/restore")
    assert r.status_code == 200, r.text
    assert folder.is_dir() and f1.exists()
