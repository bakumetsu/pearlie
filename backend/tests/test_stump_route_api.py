"""nhentai save job: route B (official download link) and the fall back to route A."""

from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.db import init_db
from app.sources.nhentai import DOWNLOAD_LIMIT, NHentai
from app.sources.throttle import Throttle
from app.stump import Stump
from app.targets import destinations
from app.targets.stump import StumpTarget
from tests import stump_mock
from tests.test_stump_target import make_post

KEY = "sekrit-key-123"
LINK = "https://i4.nhentai.net/download/99?sig=SIGNED"


def make_zip(names: list[str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("meta.json", "{}")
        for n in names:
            zf.writestr(n, b"img-" + n.encode())
    return buf.getvalue()


class Site:
    """Mock of the API host and the file host; counts what each route used."""

    def __init__(self) -> None:
        self.user = 200
        self.download = 200
        self.link = LINK
        self.file: bytes = make_zip(["2.webp", "1.webp", "10.webp"])
        self.file_status = 200
        self.posts = 0
        self.file_gets = 0
        self.page_gets = 0

    def api(self, req: httpx.Request) -> httpx.Response:
        if req.url.path == "/api/v2/user":
            return httpx.Response(self.user, json={})
        if req.method == "POST" and req.url.path.endswith("/download"):
            self.posts += 1
            return httpx.Response(self.download, json={"url": self.link})
        return httpx.Response(404)

    def files(self, req: httpx.Request) -> httpx.Response:
        if req.url.path.startswith("/download/"):
            self.file_gets += 1
            return httpx.Response(self.file_status, content=self.file)
        self.page_gets += 1
        return httpx.Response(200, content=b"page")


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(destinations, "validate_book_folder", lambda folder, roots, *a: folder)
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
    stump = Stump(
        "http://stump",
        "k",
        httpx.Client(base_url="http://stump", transport=httpx.MockTransport(mock)),
    )
    site = Site()
    src = NHentai(
        client=httpx.Client(transport=httpx.MockTransport(site.api)),
        throttle=Throttle(0),
        credentials=lambda: {"api_key": KEY},
        paced=False,
    )
    http = httpx.Client(transport=httpx.MockTransport(site.files))
    target = StumpTarget(
        settings,
        stump,
        http,
        {"nhentai": src},
        throttles={"nhentai": Throttle(0)},
        sleep=lambda _s: None,
    )
    return target, src, site, dest


def cbz_names(dest: Path) -> list[str]:
    (cbz,) = list(dest.glob("oneshots/*.cbz"))
    with zipfile.ZipFile(cbz) as zf:
        return zf.namelist()


def test_key_ok_uses_download_endpoint(env, caplog: pytest.LogCaptureFixture) -> None:
    target, src, site, dest = env
    src.check_key()
    caplog.set_level(logging.INFO)
    assert target.save(make_post(), []).status == "saved"
    assert (site.posts, site.file_gets, site.page_gets) == (1, 1, 0)
    assert cbz_names(dest) == ["001.webp", "002.webp", "003.webp", "ComicInfo.xml"]
    assert "route=api" in caplog.text
    assert KEY not in caplog.text and "SIGNED" not in caplog.text


@pytest.mark.parametrize(
    "setup",
    ["no_key_check", "download_500", "download_401", "bad_zip", "file_404", "bad_host", "no_pages"],
)
def test_failures_fall_back_to_route_a(env, caplog: pytest.LogCaptureFixture, setup: str) -> None:
    target, src, site, dest = env
    if setup != "no_key_check":
        src.check_key()
    if setup == "download_500":
        site.download = 500
    elif setup == "download_401":
        site.download = 401
    elif setup == "bad_zip":
        site.file = b"not a zip"
    elif setup == "file_404":
        site.file_status = 404
    elif setup == "bad_host":
        site.link = "https://evil.example/download/1"
    elif setup == "no_pages":
        site.file = make_zip(["cover.txt"])
    caplog.set_level(logging.INFO)
    assert target.save(make_post(), []).status == "saved"
    assert site.page_gets == 3  # three pages came from route A
    assert cbz_names(dest)[-1] == "ComicInfo.xml"
    assert "route=gallery-dl" in caplog.text
    assert KEY not in caplog.text and "SIGNED" not in caplog.text
    if setup == "download_401":
        assert src.key_state == ("failed", "invalid")


def test_failed_key_never_calls_download(env) -> None:
    target, src, site, _dest = env
    site.user = 401
    src.check_key()
    target.save(make_post(), [])
    assert site.posts == 0 and site.page_gets == 3


def test_download_budget_does_not_wait(env) -> None:
    target, src, site, _dest = env
    src.check_key()
    for _ in range(DOWNLOAD_LIMIT):
        src.download_url("42")
    assert site.posts == DOWNLOAD_LIMIT
    target.save(make_post(), [])
    assert site.posts == DOWNLOAD_LIMIT  # no 8th call; the job took route A
    assert site.page_gets == 3


def test_throttle_refusal_does_not_use_download_budget(env) -> None:
    from app.sources.base import SourceError

    _target, src, site, _dest = env
    src.check_key()
    src._throttle.hold_until(60.0, "download")
    for _ in range(DOWNLOAD_LIMIT + 3):
        with pytest.raises(SourceError) as exc:
            src.download_url("42")
        assert exc.value.status == 429
    assert len(src._download_times) == 0 and site.posts == 0


def test_same_page_bytes_give_the_same_cbz_from_both_routes(tmp_path: Path) -> None:
    from app.targets.comicinfo import build_cbz, repack_download

    post = make_post(pages=2)
    pages = []
    for n in (1, 2):
        p = tmp_path / f"{n}.webp"
        p.write_bytes(b"same-%d" % n)
        pages.append(p)
    a = tmp_path / "a.cbz"
    build_cbz(a, pages, post)
    z = tmp_path / "d.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("meta.json", "{}")
        for p in reversed(pages):
            zf.writestr(p.name, p.read_bytes())
    b = tmp_path / "b.cbz"
    assert repack_download(z, b, post) == 2
    assert a.read_bytes() == b.read_bytes()
