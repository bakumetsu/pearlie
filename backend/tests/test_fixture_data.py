"""Determinism, shape, and media-generation tests for the fixture data layer."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.fixtures import data, mediagen


class TestBuildAll:
    """Tests for data.build_all() determinism and shape."""

    def test_determinism(self) -> None:
        """Two consecutive calls produce equal dicts."""
        a = data.build_all()
        b = data.build_all()
        assert a == b

    def test_counts(self) -> None:
        raw = data.build_all()
        assert len(raw["images"]) == 200
        assert len(raw["videos"]) == 200
        assert len(raw["series"]) == 40
        assert len(raw["books"]) == 120
        for src in ("danbooru", "gelbooru", "nhentai"):
            assert len(raw["web"][src]) == 200, f"{src} post count"
        assert len(raw["web"]["rule34"]) == 200


def test_mediagen(tmp_path: Path) -> None:
    """generate() produces the expected file tree and is idempotent."""
    res = mediagen.generate(tmp_path)

    # images
    assert (tmp_path / "images" / "0.jpg").is_file()
    assert (tmp_path / "images" / "39.jpg").is_file()

    # books: 5 .cbz archives + at least one thumb
    cbz_files = sorted((tmp_path / "books").glob("*.cbz"))
    assert len(cbz_files) == 5
    assert (tmp_path / "books" / "0_thumb.jpg").is_file()

    # videos (skip if ffmpeg unavailable)
    if shutil.which("ffmpeg") is None or res["videos"] is False:
        pytest.skip("ffmpeg missing")
    mp4_files = sorted((tmp_path / "videos").glob("*.mp4"))
    assert len(mp4_files) == 6

    # idempotency: second call must not rewrite existing images
    img = tmp_path / "images" / "0.jpg"
    mtime_before = img.stat().st_mtime
    mediagen.generate(tmp_path)
    assert img.stat().st_mtime == mtime_before, "second generate() is not a no-op"
