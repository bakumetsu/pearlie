"""Tests for mediagen.ensure_media()."""

import subprocess
import time
from pathlib import Path

import pytest
from PIL import Image

from app.fixtures import mediagen
from app.fixtures.mediagen import ensure_media


@pytest.fixture(autouse=True)
def _shrink_counts(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(mediagen, "IMG_COUNT", 2)
    monkeypatch.setattr(mediagen, "BOOK_COUNT", 2)
    monkeypatch.setattr(mediagen, "VIDEO_COUNT", 1)


@pytest.fixture
def media(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "media"
    d.mkdir()
    monkeypatch.setattr(mediagen, "media_dir", lambda: d)
    return d


def test_ensure_media_completes_partial(media: Path, monkeypatch: pytest.MonkeyPatch):
    """A dir with only images (no .complete) gets books finished and marker written."""
    monkeypatch.setattr(mediagen, "_ffmpeg", lambda: None)

    # Simulate an interrupted generate: images present, books absent, no marker.
    (media / "images").mkdir()
    Image.new("RGB", (64, 64), "red").save(media / "images" / "0.jpg", quality=85)

    ensure_media()

    assert (media / "books" / "0.cbz").exists()
    assert (media / "books" / "0_thumb.jpg").exists()
    assert (media / "books" / "1.cbz").exists()
    assert (media / "books" / "1_thumb.jpg").exists()
    assert (media / ".complete").exists()


def test_ensure_media_second_call_no_regen(media: Path, monkeypatch: pytest.MonkeyPatch):
    """Second ensure_media call returns early; mtimes are unchanged."""
    monkeypatch.setattr(mediagen, "_ffmpeg", lambda: None)

    ensure_media()
    book = media / "books" / "0.cbz"
    mtime1 = book.stat().st_mtime

    time.sleep(0.05)
    ensure_media()

    assert book.stat().st_mtime == mtime1


def test_ensure_media_ffmpeg_fail_books_still_generated(
    media: Path, monkeypatch: pytest.MonkeyPatch
):
    """When _ffmpeg resolves but the binary fails, books are still generated."""
    fake = str(media / "fake_ffmpeg")
    monkeypatch.setattr(mediagen, "_ffmpeg", lambda: fake)

    def _fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0])

    monkeypatch.setattr(subprocess, "run", _fail)

    ensure_media()

    assert (media / "books" / "0.cbz").exists()
    assert (media / "books" / "0_thumb.jpg").exists()
    assert (media / "books" / "1.cbz").exists()
    assert (media / "books" / "1_thumb.jpg").exists()
    assert (media / ".complete").exists()
