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
        self.authors: dict[str, list[str]] = {}  # book file name -> Komga writer names

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
                {
                    "id": "B1",
                    "url": f.as_posix(),
                    "metadata": {
                        "authors": [
                            {"name": n, "role": "writer"} for n in self.authors.get(f.name, [])
                        ]
                    },
                }
                for f in self.dest.rglob("*.cbz")
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
    (tmp_path / "lib").mkdir()
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
    assert res.pending_scan is not None and res.pending_scan.library_id == "L1"
    assert komga.scanned == []  # save() no longer scans; ScanWait does
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


def _row_count(settings: Settings) -> int:
    conn = connect(settings.db_path)
    n = conn.execute("SELECT COUNT(*) FROM saved_items").fetchone()[0]
    conn.close()
    return n


def _age_rows(settings: Settings) -> None:
    conn = connect(settings.db_path)
    conn.execute("UPDATE saved_items SET created_at = datetime('now', '-2 days')")
    conn.commit()
    conn.close()


def test_drop_if_gone_keeps_fresh_row_before_komga_scan(env) -> None:
    target, komga, settings, _dest, _h = env
    target.save(make_post(), [])
    komga.visible = False
    assert target.drop_if_gone("nhentai", "42") is False
    assert _row_count(settings) == 1


def test_drop_if_gone_keeps_row_on_full_page(env) -> None:
    target, komga, settings, _dest, _h = env
    target.save(make_post(), [])
    _age_rows(settings)
    komga.list_books = lambda *a, **k: {  # type: ignore[method-assign]
        "content": [{"url": f"/lib/other{i}.cbz"} for i in range(50)]
    }
    assert target.drop_if_gone("nhentai", "42") is False
    assert _row_count(settings) == 1


def test_drop_if_gone_keeps_row_while_book_exists(env) -> None:
    target, _komga, settings, _dest, _h = env
    target.save(make_post(), [])
    _age_rows(settings)
    assert target.drop_if_gone("nhentai", "42") is False
    assert _row_count(settings) == 1


def test_drop_if_gone_drops_row_when_book_deleted(env) -> None:
    target, komga, settings, _dest, _h = env
    target.save(make_post(), [])
    _age_rows(settings)
    komga.visible = False
    assert target.drop_if_gone("nhentai", "42") is True
    assert _row_count(settings) == 0


def test_drop_if_gone_matches_book_by_web_link(env) -> None:
    target, komga, settings, _dest, _h = env
    target.save(make_post(), [])
    _age_rows(settings)
    komga.list_books = lambda *a, **k: {  # type: ignore[method-assign]
        "content": [
            {
                "url": "/lib/Renamed.cbz",
                "metadata": {"links": [{"url": "https://nhentai.net/g/42/"}]},
            }
        ]
    }
    assert target.drop_if_gone("nhentai", "42") is False
    assert _row_count(settings) == 1


def test_drop_if_gone_keeps_row_on_komga_error(env) -> None:
    target, komga, settings, _dest, _h = env
    target.save(make_post(), [])
    _age_rows(settings)

    def boom(*a, **k):
        raise KomgaError("upstream_error", "down", 502)

    komga.list_books = boom  # type: ignore[method-assign]
    assert target.drop_if_gone("nhentai", "42") is False
    assert _row_count(settings) == 1


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


def test_scan_call_failure_raises_komga_error(env) -> None:
    target, komga, _s, _dest, _h = env
    komga.fail_scan = True
    with pytest.raises(KomgaError):
        target.scan("L1")


def test_library_lookup_failure_is_a_notice(env) -> None:
    target, komga, _s, dest, _h = env

    real = komga.list_libraries

    def boom() -> list[dict]:
        if list(dest.glob("*.cbz")):  # the lookup after the file is placed
            raise KomgaError("upstream_error", "down", 502)
        return real()

    komga.list_libraries = boom  # type: ignore[method-assign]
    res = target.save(make_post(), [])
    assert res.status == "saved" and res.pending_scan is None
    assert [n.code for n in res.notices] == ["oneshots_not_set", "scan_failed"]
    assert len(list(dest.iterdir())) == 1


def test_save_returns_pending_scan_without_calling_komga(env) -> None:
    target, komga, _s, dest, _h = env
    komga.oneshots = "_oneshots"
    res = target.save(make_post(), [])
    assert res.notices == []
    assert res.dest_path and res.dest_path.startswith(dest.as_posix())
    assert res.pending_scan is not None
    assert res.pending_scan.komga_path == res.dest_path
    assert (komga.list_calls, komga.scanned) == (0, [])


def test_find_books_matches_by_path_or_name(env) -> None:
    from app.targets.stash import PendingScan

    target, komga, _s, dest, _h = env
    res = target.save(make_post(), [])
    assert res.pending_scan is not None
    other = PendingScan(library_id="L1", name="nope.cbz", komga_path="/x/nope.cbz")
    found = target.find_books("L1", {"1": res.pending_scan, "2": other})
    assert found == {"1"}
    assert komga.list_calls == 1
    komga.visible = False
    assert target.find_books("L1", {"1": res.pending_scan}) == set()


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


def test_second_book_pairs_with_oneshot_whose_name_has_no_artist(env) -> None:
    """The oneshot file name has no [artist]; Komga knows the author (hand-moved book)."""
    target, komga, _s, dest, _h = env
    komga.oneshots = "_oneshots"
    ones = dest / "_oneshots"
    ones.mkdir(parents=True)
    old = ones / "My Sister [1].cbz"
    old.write_bytes(b"old")
    komga.authors = {old.name: ["bob"]}
    res = target.save(titled("My Sister 2", "2"), [])  # make_post tags the artist "bob"
    assert res.notices == []
    names = sorted(p.name for p in (dest / "[bob] My Sister").iterdir())
    assert old.name in names and len(names) == 2
    assert not list(ones.iterdir())


def _hand_moved(dest: Path) -> Path:
    ones = dest / "_oneshots"
    ones.mkdir(parents=True)
    old = ones / "My Sister [1].cbz"
    old.write_bytes(b"old")
    return old


def test_pairing_matches_author_case_and_space_insensitive_any_writer(env) -> None:
    target, komga, _s, dest, _h = env
    komga.oneshots = "_oneshots"
    old = _hand_moved(dest)
    komga.authors = {old.name: ["someone", "  BOB "]}
    target.save(titled("My Sister 2", "2"), [])
    assert (dest / "[bob] My Sister" / old.name).exists()


def test_unscanned_oneshot_stays_unpaired(env) -> None:
    target, komga, _s, dest, _h = env
    komga.oneshots = "_oneshots"
    old = _hand_moved(dest)  # Komga has no metadata for it yet
    target.save(titled("My Sister 2", "2"), [])
    assert old.exists()


def test_author_lookup_is_cached_across_index_builds(env) -> None:
    target, komga, _s, dest, _h = env
    komga.oneshots = "_oneshots"
    old = _hand_moved(dest)
    komga.authors = {old.name: ["bob"]}
    post = titled("My Sister 2", "2")
    assert target.suggest(post).via == "oneshot_pair"
    first = komga.list_calls
    target._index_cache.invalidate()
    assert target.suggest(post).via == "oneshot_pair"
    assert komga.list_calls == first


def test_author_miss_is_retried_after_its_short_ttl(env) -> None:
    target, komga, _s, dest, _h = env
    komga.oneshots = "_oneshots"
    old = _hand_moved(dest)
    now = [1000.0]
    target._clock = lambda: now[0]
    post = titled("My Sister 2", "2")
    assert target.suggest(post).via == "new"  # not scanned yet
    komga.authors = {old.name: ["bob"]}
    target._index_cache.invalidate()
    assert target.suggest(post).via == "new"  # miss still cached
    now[0] += 301
    target._index_cache.invalidate()
    assert target.suggest(post).via == "oneshot_pair"


def test_komga_failure_in_author_lookup_still_saves(env) -> None:
    target, komga, _s, dest, _h = env
    komga.oneshots = "_oneshots"
    old = _hand_moved(dest)

    def boom(*_a, **_k):
        raise KomgaError("upstream_error", "down", 502)

    komga.list_books = boom  # type: ignore[method-assign]
    res = target.save(titled("My Sister 2", "2"), [])
    assert res.status == "saved" and old.exists()


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


def test_suggest_writes_nothing(env) -> None:
    target, _komga, _s, dest, _h = env
    target.save(titled("[Foo] My Sister vol 1", "1"), [])
    before = sorted(p.name for p in dest.rglob("*"))
    plan = target.suggest(titled("[Foo] My Sister vol 2", "2"))
    assert plan.kind == "series" and plan.series == "My Sister"
    assert sorted(p.name for p in dest.rglob("*")) == before


def test_prefix_absorb_only_for_suggestion_and_sheet_override(env) -> None:
    target, komga, _s, dest, _h = env
    komga.oneshots = "_oneshots"
    target.save(titled("[Foo] Love vol 2", "1"), [])  # makes the folder "[Foo] Love"
    longer = titled("[Foo] Love Hotel Nights", "2")
    # suggestion (sheet preview) joins by prefix
    assert target.suggest(longer).via == "absorb"
    # batch/rule save (no placement): exact root only, so a oneshot
    target.save(longer, [])
    assert len(list((dest / "[Foo] Love").iterdir())) == 1
    # sheet save (confirmed kind sent): joins the series
    target.save(titled("[Foo] Love Story", "3"), [], placement="series")
    assert len(list((dest / "[Foo] Love").iterdir())) == 2


def test_missing_library_root_fails_and_creates_nothing(env, tmp_path: Path) -> None:
    target, komga, settings, dest, _h = env
    komga.root = (tmp_path / "elsewhere").as_posix()
    settings.komga_incoming_dir = (tmp_path / "elsewhere" / "incoming").as_posix()
    with pytest.raises(SaveError) as err:
        target.save(make_post(), [])
    assert err.value.code == "library_not_mounted"
    assert not dest.exists() and not (tmp_path / "elsewhere").exists()


def test_library_root_checked_through_prefix_map(env, tmp_path: Path) -> None:
    target, komga, settings, dest, _h = env
    komga.root = "/komga/lib"
    settings.komga_path_prefix_pearlie = (tmp_path / "lib").as_posix()
    settings.komga_path_prefix_komga = "/komga/lib"
    assert (
        target.save(make_post(), []).dest_path == "/komga/lib/incoming/" + next(dest.iterdir()).name
    )
    assert komga.scanned == []


def test_to_pearlie_path_roundtrip() -> None:
    assert destinations.to_pearlie_path("/k/a/b", "/p", "/k") == "/p/a/b"
    assert destinations.to_pearlie_path("/k", "/p", "/k") == "/p"
    assert destinations.to_pearlie_path("/x", "/p", "/k") == "/x"
    assert destinations.to_pearlie_path("/x", "", "") == "/x"


def test_file_outside_every_library_leaves_no_index_row(env) -> None:
    target, komga, settings, _dest, _h = env
    komga.root = "/somewhere/else"
    res = target.save(make_post(), [])
    codes = [n.code for n in res.notices]
    assert "outside_library" in codes and "scan_failed" not in codes
    assert res.pending_scan is None
    assert _row_count(settings) == 0


def test_book_not_listed_yet_keeps_row_for_grace(env) -> None:
    target, komga, settings, _dest, _h = env
    komga.visible = False
    res = target.save(make_post(), [])
    assert res.pending_scan is not None
    assert _row_count(settings) == 1
