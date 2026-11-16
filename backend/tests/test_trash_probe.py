"""Path guard and per-root probe of the Stash trash layer."""

import errno
import os

import pytest

from tests.test_trash_stash import FakeStash, lib_file, make, one_file


def test_path_outside_every_root_is_422_before_any_rename(tmp_path):
    lib, _ = lib_file(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    f = outside / "o.jpg"
    f.write_bytes(b"x")
    stash = FakeStash(lib, [one_file(f)])
    c = make(tmp_path, stash)
    r = c.delete("/api/library/images/1")
    assert r.status_code == 422
    assert r.json()["code"] == "path_outside_library"
    assert f.exists()
    assert stash.destroyed == []
    assert list((tmp_path / "trash").iterdir()) == []


def test_dotdot_escape_is_422(tmp_path):
    lib, _ = lib_file(tmp_path)
    outside = tmp_path / "o.jpg"
    outside.write_bytes(b"x")
    stash = FakeStash(lib, [one_file(lib / ".." / "o.jpg")])
    c = make(tmp_path, stash)
    r = c.delete("/api/library/images/1")
    assert r.status_code == 422
    assert outside.exists()
    assert stash.destroyed == []


def test_symlink_escape_is_422(tmp_path):
    lib, _ = lib_file(tmp_path)
    outside = tmp_path / "o.jpg"
    outside.write_bytes(b"x")
    link = lib / "link.jpg"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not available")
    stash = FakeStash(lib, [one_file(link)])
    c = make(tmp_path, stash)
    r = c.delete("/api/library/images/1")
    assert r.status_code == 422
    assert outside.exists()
    assert stash.destroyed == []


def test_status_probe_ok_cached_and_clean(tmp_path):
    lib, _ = lib_file(tmp_path)
    c = make(tmp_path, FakeStash(lib, []))
    body = c.get("/api/trash/status").json()
    assert body["roots"] == [{"index": 0, "stash_path": str(lib), "state": "ok"}]
    assert list(lib.glob(".pearlie-probe-*")) == []
    assert list((tmp_path / "trash").iterdir()) == []
    assert c.get("/api/trash/status").json() == body


def test_status_unreachable_root(tmp_path):
    c = make(tmp_path, FakeStash(tmp_path / "missing", []))
    assert c.get("/api/trash/status").json()["roots"][0]["state"] == "not_reachable"


def test_status_other_volume(tmp_path, monkeypatch):
    lib, _ = lib_file(tmp_path)
    real = os.rename

    def fake(src, dst):
        if ".pearlie-probe-" in str(dst) and "trash" in str(dst):
            raise OSError(errno.EXDEV, "cross")
        return real(src, dst)

    monkeypatch.setattr(os, "rename", fake)
    c = make(tmp_path, FakeStash(lib, []))
    assert c.get("/api/trash/status").json()["roots"][0]["state"] == "other_volume"
    assert list(lib.glob(".pearlie-probe-*")) == []
