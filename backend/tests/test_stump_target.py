from __future__ import annotations

from pathlib import Path
from typing import cast

import httpx
import pytest

from app.bookserver.base import BookServerError
from app.config import Settings
from app.db import connect, init_db
from app.sources.nhentai import NHentai
from app.sources.throttle import Throttle
from app.stump import Stump
from app.targets import destinations
from app.targets.komga import scan_failed_notice
from app.targets.stash import PendingScan
from app.targets.stump import StumpTarget
from tests import stump_mock
from tests.test_komga_target import make_post


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(destinations, "validate_komga_folder", lambda folder, roots, *a: folder)
    dest = tmp_path / "lib" / "incoming"
    settings = Settings(
        mode="real",
        db_path=tmp_path / "p.db",
        stump_incoming_dir=dest.as_posix(),
        stump_temp_dir=tmp_path / "lib" / ".tmp",
    )
    init_db(settings.db_path)
    (tmp_path / "lib").mkdir()
    lib = stump_mock.lib()
    lib["path"] = (tmp_path / "lib").as_posix()
    mock = stump_mock.MockStump([lib], [], [])
    client = httpx.Client(base_url="http://stump", transport=httpx.MockTransport(mock))
    http = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"page"))
    )
    target = StumpTarget(
        settings,
        Stump("http://stump", "k", client),
        http,
        {"nhentai": NHentai(client=http, throttle=Throttle(0))},
        throttles={"nhentai": Throttle(0)},
        sleep=lambda _s: None,
    )
    return target, mock, settings, dest


def test_save_uses_stump_target_and_library(env) -> None:
    target, _mock, settings, dest = env
    res = target.save(make_post(), [])
    assert res.status == "saved"
    assert res.pending_scan is not None and res.pending_scan.library_id == "L1"
    assert [n.code for n in res.notices] == []
    conn = connect(settings.db_path)
    row = conn.execute("SELECT target FROM saved_items").fetchone()
    conn.close()
    assert row["target"] == "stump"
    assert len(list(dest.glob("oneshots/*.cbz"))) == 1


def test_scan_waits_for_job_and_find_books_uses_media_by_path(env) -> None:
    target, mock, _s, _d = env
    target.scan("L1")
    assert mock.scanned == ["L1"]
    assert any(c[2].get("operationName") == "Job" for c in mock.calls)
    book = stump_mock.book(1)
    mock.books.append(book)
    pending = PendingScan(library_id="L1", name="book1.cbz", komga_path=book["path"])
    miss = PendingScan(library_id="L1", name="x.cbz", komga_path="/nope.cbz")
    assert target.find_books("L1", {"1": pending, "2": miss}) == {"1"}


def test_failed_scan_job_raises_and_notice_names_stump(env) -> None:
    target, mock, _s, _d = env
    mock.job_status = ["FAILED"]
    with pytest.raises(BookServerError) as exc:
        target.scan("L1")
    assert exc.value.status == 502
    notice = scan_failed_notice(target.label)
    assert notice.code == "scan_failed"
    assert "Stump" in notice.message and "Komga" not in notice.message


def test_unconfigured_client_is_save_error() -> None:
    target = StumpTarget(cast(Settings, Settings(mode="real")), None, httpx.Client(), {})
    with pytest.raises(Exception, match="not configured"):
        _ = target._books
