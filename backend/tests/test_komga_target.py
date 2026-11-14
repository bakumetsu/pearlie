from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path
from typing import cast

import httpx
import pytest

from app.config import Settings
from app.db import connect, init_db
from app.komga import Komga, KomgaError
from app.sources.base import Post
from app.sources.nhentai import NHentai
from app.sources.throttle import Throttle
from app.targets import destinations
from app.targets.komga import KomgaTarget
from app.targets.stash import SaveError


class FakeKomga:
    def __init__(self, root: str, fail_scan: bool = False) -> None:
        self.root = root
        self.oneshots: str | None = None
        self.fail_scan = fail_scan
        self.scanned: list[str] = []
        self.visible = True
        self.list_calls = 0
        self.dest: Path | None = None

    def list_libraries(self) -> list[dict]:
        lib = {"id": "L1", "name": "Doujin", "root": self.root}
        if self.oneshots:
            lib["oneshotsDirectory"] = self.oneshots
        return [lib]

    def scan_library(self, library_id: str) -> None:
        if self.fail_scan:
            raise KomgaError("upstream_error", "down", 502)
        self.scanned.append(library_id)

    def list_books(self, page, size, q, sort, series_id=None, library_id=None) -> dict:
        self.list_calls += 1
        if not self.visible or self.dest is None:
            return {"content": []}
        return {
            "content": [
                {"id": "B1", "url": f.as_posix()} for f in self.dest.rglob("*.cbz")
            ]
        }


def make_post(pages: int = 3, media_id: str = "123") -> Post:
    return Post(
        source="nhentai",
        post_id="42",
        title="Title: A/B?",
        source_url="https://nhentai.net/g/42/",
        tags={"general": ["x & y"], "artist": ["bob"], "language": ["english"]},
        extra={"media_id": media_id, "page_exts": ["jpg"] * pages},
    )


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Windows paths are not posix-absolute; folder validation has its own test below.
    monkeypatch.setattr(destinations, "validate_komga_folder", lambda folder, roots, *a: folder)
    dest = tmp_path / "lib" / "incoming"
    settings = Settings(
        mode="real",
        db_path=tmp_path / "p.db",
        komga_incoming_dir=dest.as_posix(),
        komga_temp_dir=tmp_path / "lib" / ".tmp",
    )
    init_db(settings.db_path)
    hits: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hits.append(f"{request.url.host}{request.url.path}")
        assert "cookie" not in request.headers
        n = request.url.path.rsplit("/", 1)[1].split(".")[0]
        return httpx.Response(200, content=f"page{n}".encode())

    http = httpx.Client(transport=httpx.MockTransport(handler))
    src = NHentai(client=http, throttle=Throttle(0))
    komga = FakeKomga((tmp_path / "lib").as_posix())
    komga.dest = dest
    target = KomgaTarget(
        settings,
        cast(Komga, komga),
        http,
        {"nhentai": src},
        throttles={"nhentai": Throttle(0)},
        sleep=lambda _s: None,
    )
    return target, komga, settings, dest, hits


def test_saves_ordered_cbz_with_comicinfo(env) -> None:
    target, komga, settings, dest, hits = env
    res = target.save(make_post(), [])
    assert res.status == "saved"
    files = list(dest.iterdir())
    assert len(files) == 1 and files[0].suffix == ".cbz"
    assert not any(c.name.endswith(".part") for c in files)
    with zipfile.ZipFile(files[0]) as zf:
        assert zf.namelist() == ["001.jpg", "002.jpg", "003.jpg", "ComicInfo.xml"]
        assert zf.read("001.jpg") == b"page1"
        info = zf.read("ComicInfo.xml").decode()
    assert "<LanguageISO>en</LanguageISO>" in info and "x &amp; y" in info
    assert hits == [f"i.nhentai.net/galleries/123/{n}.jpg" for n in (1, 2, 3)]
    assert komga.scanned == ["L1"]
    assert not list(settings.komga_temp_dir.glob("pearlie-*"))
    conn = connect(settings.db_path)
    row = conn.execute("SELECT md5, target, image_id FROM saved_items").fetchone()
    conn.close()
    assert row["md5"] == hashlib.md5(files[0].read_bytes()).hexdigest()
    assert (row["target"], row["image_id"]) == ("komga", "")


def test_second_save_is_duplicate(env) -> None:
    target, _komga, _s, dest, _h = env
    target.save(make_post(), [])
    assert target.save(make_post(), []).status == "duplicate"
    assert len(list(dest.iterdir())) == 1


def test_name_clash_renames_and_notices(env) -> None:
    target, _komga, settings, dest, _h = env
    target.save(make_post(), [])
    conn = connect(settings.db_path)
    conn.execute("DELETE FROM saved_items")
    conn.commit()
    conn.close()
    existing = next(dest.iterdir())
    existing.write_bytes(b"other")
    res = target.save(make_post(), [])
    assert res.status == "saved"
    assert any(n.code == "name_clash" for n in res.notices)
    assert len(list(dest.iterdir())) == 2


def test_scan_failure_is_a_notice(env) -> None:
    target, komga, _s, dest, _h = env
    komga.fail_scan = True
    res = target.save(make_post(), [])
    assert res.status == "saved"
    assert [n.code for n in res.notices] == ["oneshots_not_set", "scan_failed"]
    assert len(list(dest.iterdir())) == 1


def test_verified_book_has_no_notice(env) -> None:
    target, komga, _s, dest, _h = env
    komga.oneshots = "_oneshots"
    res = target.save(make_post(), [])
    assert res.notices == []
    assert res.dest_path and res.dest_path.startswith(dest.as_posix())
    assert komga.list_calls == 1


def test_missing_book_is_waiting_for_komga(env) -> None:
    target, komga, _s, dest, _h = env
    komga.visible = False
    res = target.save(make_post(), [])
    assert res.status == "saved"
    codes = [n.code for n in res.notices]
    assert codes == ["oneshots_not_set", "waiting_for_komga"]
    assert komga.list_calls == 5


def test_cbz_is_deterministic(env) -> None:
    target, _komga, settings, dest, _h = env
    target.save(make_post(), [])
    first = next(dest.iterdir()).read_bytes()
    conn = connect(settings.db_path)
    conn.execute("DELETE FROM saved_items")
    conn.commit()
    conn.close()
    next(dest.iterdir()).unlink()
    target.save(make_post(), [])
    assert next(dest.iterdir()).read_bytes() == first


def test_bad_media_id_has_no_file(env) -> None:
    target = env[0]
    with pytest.raises(SaveError) as e:
        target.save(make_post(media_id="../evil"), [])
    assert e.value.code == "no_file"


def test_page_failure_leaves_nothing(env) -> None:
    target, _komga, settings, dest, _h = env
    target._http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    with pytest.raises(SaveError) as e:
        target.save(make_post(), [])
    assert e.value.code == "download_failed"
    assert not list(dest.glob("*")) and not list(settings.komga_temp_dir.glob("pearlie-*"))


def test_validate_komga_folder() -> None:
    assert destinations.validate_komga_folder("/lib/in", ["/lib"]) == "/lib/in"
    with pytest.raises(destinations.DestinationError) as e:
        destinations.validate_komga_folder("/other", ["/lib"])
    assert "Komga" in e.value.message


def titled(title: str, post_id: str) -> Post:
    post = make_post()
    return post.model_copy(update={"title": title, "post_id": post_id})


def _comic_info(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        return zf.read("ComicInfo.xml").decode()


def test_oneshot_goes_to_oneshots_folder(env) -> None:
    target, komga, _s, dest, _h = env
    komga.oneshots = "_oneshots"
    res = target.save(titled("[Foo] Lonely Book", "1"), [])
    assert res.status == "saved" and res.notices == []
    book = next((dest / "_oneshots").iterdir())
    assert "<Series>" not in _comic_info(book)
    assert [p.name for p in dest.iterdir()] == ["_oneshots"]


def test_series_book_goes_to_author_root_folder(env) -> None:
    target, komga, _s, dest, _h = env
    komga.oneshots = "_oneshots"
    target.save(titled("[Foo] My Sister vol 2", "2"), [])
    book = next((dest / "[Foo] My Sister").iterdir())
    info = _comic_info(book)
    assert "<Series>My Sister</Series>" in info and "<Number>2</Number>" in info


def test_second_volume_moves_first_oneshot(env) -> None:
    target, komga, _s, dest, _h = env
    komga.oneshots = "_oneshots"
    target.save(titled("[Foo] My Sister", "1"), [])
    first = next((dest / "_oneshots").iterdir())
    data = first.read_bytes()
    res = target.save(titled("[Foo] My Sister 2", "2"), [])
    assert res.notices == []
    names = sorted(p.name for p in (dest / "[Foo] My Sister").iterdir())
    assert first.name in names and len(names) == 2
    assert not list((dest / "_oneshots").iterdir())
    assert (dest / "[Foo] My Sister" / first.name).read_bytes() == data


def test_move_failure_never_fails_the_save(env, monkeypatch: pytest.MonkeyPatch) -> None:
    target, komga, _s, dest, _h = env
    komga.oneshots = "_oneshots"
    target.save(titled("[Foo] My Sister", "1"), [])

    def boom(src, dst):
        raise PermissionError(13, "denied")

    monkeypatch.setattr("app.targets.komga.os.rename", boom)
    res = target.save(titled("[Foo] My Sister 2", "2"), [])
    assert res.status == "saved"
    assert "move_failed" in [n.code for n in res.notices]
    assert len(list((dest / "_oneshots").iterdir())) == 1


def test_missing_old_file_is_move_skipped(env) -> None:
    target, komga, _s, dest, _h = env
    komga.oneshots = "_oneshots"
    target.save(titled("[Foo] My Sister", "1"), [])
    plan_cache = target._index_cache
    plan_cache.get(dest, "_oneshots")  # warm the cache, then remove the file behind it
    next((dest / "_oneshots").iterdir()).unlink()
    res = target.save(titled("[Foo] My Sister 2", "2"), [])
    assert res.status == "saved"
    assert "move_skipped" in [n.code for n in res.notices]


def test_override_oneshot_wins_over_series(env) -> None:
    target, komga, _s, dest, _h = env
    komga.oneshots = "_oneshots"
    target.save(titled("[Foo] My Sister vol 2", "2"), [], placement="oneshot")
    assert len(list((dest / "_oneshots").iterdir())) == 1
    assert not (dest / "[Foo] My Sister").exists()


def test_override_series_for_oneshot(env) -> None:
    target, komga, _s, dest, _h = env
    komga.oneshots = "_oneshots"
    target.save(titled("[Foo] Lonely Book", "1"), [], placement="series")
    assert len(list((dest / "[Foo] Lonely Book").iterdir())) == 1


def test_job_placement_roundtrip(tmp_path: Path) -> None:
    from app.jobs.store import JobStore

    init_db(tmp_path / "j.db")
    store = JobStore(tmp_path / "j.db")
    jid = store.enqueue(make_post(), "komga", "t", "", placement="oneshot")
    assert store.load_placement(jid) == "oneshot"
    other = make_post().model_copy(update={"post_id": "43"})
    assert store.load_placement(store.enqueue(other, "komga", "t", "")) is None
