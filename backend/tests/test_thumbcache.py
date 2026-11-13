import os
import threading
from pathlib import Path

import pytest

from app import thumbcache
from app.config import Settings
from app.thumbcache import ThumbCache, sniff_image_type

JPEG = b"\xff\xd8\xff\xe0" + b"x" * 60
PNG = b"\x89PNG\r\n\x1a\n" + b"y" * 60


def make(tmp_path: Path, **kw: object) -> ThumbCache:
    cache = ThumbCache(tmp_path / "thumbcache", **kw)  # type: ignore[arg-type]
    cache.rescan()
    return cache


def set_cap_bytes(cache: ThumbCache, n: int) -> None:
    cache._max_bytes = n


def test_store_then_hit(tmp_path: Path) -> None:
    cache = make(tmp_path)
    assert cache.get("danbooru", "1") is None
    assert cache.put("danbooru", "1", JPEG)
    path = cache.get("danbooru", "1")
    assert path is not None and path.read_bytes() == JPEG
    assert path.name.endswith(".img")
    assert path.relative_to(cache.root).parts[0] == "danbooru"
    assert cache.stats()["files"] == 1 and cache.stats()["used_bytes"] == len(JPEG)


def test_overwrite_keeps_totals(tmp_path: Path) -> None:
    cache = make(tmp_path)
    cache.put("rule34", "1", JPEG)
    cache.put("rule34", "1", PNG + b"z" * 10)
    st = cache.stats()
    assert st["files"] == 1 and st["used_bytes"] == len(PNG) + 10


def test_atomic_write_leaves_no_part(tmp_path: Path) -> None:
    cache = make(tmp_path)
    cache.put("gelbooru", "9", JPEG)
    assert not list(cache.root.rglob("*.part"))


def test_rejects_non_image_and_oversize(tmp_path: Path) -> None:
    cache = make(tmp_path)
    assert not cache.put("danbooru", "1", b"<html>error</html>")
    assert not cache.put("danbooru", "1", b"")
    assert not cache.put("danbooru", "1", JPEG + b"0" * thumbcache.MAX_THUMB_BYTES)
    assert cache.stats()["files"] == 0


def test_corrupt_file_is_dropped(tmp_path: Path) -> None:
    cache = make(tmp_path)
    cache.put("danbooru", "1", JPEG)
    path = cache.path_for("danbooru", "1")
    path.write_bytes(b"<html>")
    assert cache.get("danbooru", "1") is None
    assert not path.exists()


def test_lru_evicts_oldest_down_to_90_percent(tmp_path: Path) -> None:
    cache = make(tmp_path)
    body = JPEG + b"0" * 1000  # 1064 bytes
    set_cap_bytes(cache, 10 * len(body))
    for i in range(10):
        cache.put("danbooru", str(i), body)
        os.utime(cache.path_for("danbooru", str(i)), (1000 + i, 1000 + i))
    cache.get("danbooru", "0")  # touch: 0 is now the newest
    cache.put("danbooru", "10", body)  # 11 files, over the cap
    left = {i for i in range(11) if cache.path_for("danbooru", str(i)).exists()}
    assert 0 in left and 10 in left and 1 not in left
    assert cache.stats()["used_bytes"] <= 0.9 * 10 * len(body)
    assert cache.stats()["files"] == len(left)


def test_cap_change_evicts(tmp_path: Path) -> None:
    cache = make(tmp_path)
    body = JPEG + b"0" * 1000
    for i in range(20):
        cache.put("rule34", str(i), body)
    set_cap_bytes(cache, 5 * len(body))
    cache.set_max_mb(thumbcache.MIN_MAX_MB)  # still above usage: nothing evicted
    assert cache.stats()["files"] == 20
    set_cap_bytes(cache, 5 * len(body))
    cache._evict(thumbcache.EVICT_TARGET)
    assert cache.stats()["used_bytes"] <= 0.9 * 5 * len(body)


def test_set_max_mb_validates(tmp_path: Path) -> None:
    cache = make(tmp_path)
    for bad in (0, 49, 20481):
        with pytest.raises(ValueError):
            cache.set_max_mb(bad)
    cache.set_max_mb(50)
    assert cache.max_mb == 50


def test_clear_empties(tmp_path: Path) -> None:
    cache = make(tmp_path)
    cache.put("danbooru", "1", JPEG)
    cache.put("nhentai", "2", PNG)
    freed = cache.clear()
    assert freed == len(JPEG) + len(PNG)
    assert cache.stats()["files"] == 0 and cache.stats()["used_bytes"] == 0
    assert not list(cache.root.rglob("*.img"))
    assert (cache.root / "danbooru").is_dir()


def test_startup_walk_cleans_part_and_counts(tmp_path: Path) -> None:
    first = make(tmp_path)
    first.put("danbooru", "1", JPEG)
    stale = first.root / "danbooru" / "ab" / "stale.img.part"
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_bytes(b"half")
    second = ThumbCache(first.root)
    done = threading.Event()

    def run() -> None:
        second.rescan()
        done.set()

    threading.Thread(target=run).start()
    assert done.wait(5)
    assert not stale.exists()
    assert second.stats()["files"] == 1


def test_hostile_ids_stay_inside_root(tmp_path: Path) -> None:
    cache = make(tmp_path)
    for pid in ("../../etc/passwd", r"..\..\x", "a/b", "\0", "x" * 500):
        path = cache.path_for("danbooru", pid)
        assert cache.root.resolve() in path.resolve().parents
        assert "etc" not in path.relative_to(cache.root).parts
    with pytest.raises(ValueError):
        cache.path_for("../evil", "1")


def test_name_has_no_post_id_or_url(tmp_path: Path) -> None:
    cache = make(tmp_path)
    name = cache.path_for("danbooru", "12345").name
    assert "12345" not in name and len(name) == 64 + len(".img")


def test_disk_error_passes_through(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                   caplog: pytest.LogCaptureFixture) -> None:
    cache = make(tmp_path)

    def boom(self: Path, data: bytes) -> int:
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_bytes", boom)
    with caplog.at_level("WARNING", logger="pearlie.thumbcache"):
        assert cache.put("danbooru", "1", JPEG) is False
        assert cache.put("danbooru", "2", JPEG) is False
    assert len([r for r in caplog.records if "write failed" in r.message]) == 1
    assert cache.stats()["files"] == 0


def test_unwritable_root_is_pass_through(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x")
    cache = ThumbCache(blocker / "thumbcache")
    assert not cache.available
    assert cache.put("danbooru", "1", JPEG) is False
    assert cache.get("danbooru", "1") is None
    assert cache.clear() == 0
    assert cache.stats()["available"] is False


def test_root_inside_protected_folder_refused(tmp_path: Path) -> None:
    trash = tmp_path / "trash"
    trash.mkdir()
    cache = ThumbCache(trash / "thumbcache", forbidden=[trash])
    assert not cache.available
    assert not (trash / "thumbcache").exists()


def test_sniff_types() -> None:
    assert sniff_image_type(JPEG) == "image/jpeg"
    assert sniff_image_type(PNG) == "image/png"
    assert sniff_image_type(b"GIF89a" + b"0" * 10) == "image/gif"
    assert sniff_image_type(b"RIFF\0\0\0\0WEBPVP8 ") == "image/webp"
    assert sniff_image_type(b"\0\0\0\x18ftypavif" + b"0" * 4) == "image/avif"
    assert sniff_image_type(b"<svg xmlns=") is None


def test_settings_default_root(tmp_path: Path) -> None:
    s = Settings(mode="fixture", db_path=tmp_path / "data" / "pearlie.db", _env_file=None)  # type: ignore[call-arg]
    assert s.thumb_cache_root == tmp_path / "data" / "thumbcache"
    s2 = Settings(mode="fixture", thumb_cache_dir=" ", _env_file=None)  # type: ignore[call-arg]
    assert s2.thumb_cache_dir is None
    s3 = Settings(mode="fixture", thumb_cache_dir=tmp_path / "tc", _env_file=None)  # type: ignore[call-arg]
    assert s3.thumb_cache_root == tmp_path / "tc"
