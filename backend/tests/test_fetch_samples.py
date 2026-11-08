"""Black-box tests for backend/scripts/fetch_samples.py."""

import contextlib
import importlib.util
import json
import zipfile
from io import BytesIO
from pathlib import Path
from unittest import mock

from PIL import Image

_spec = importlib.util.spec_from_file_location(
    "fetch_samples", Path(__file__).parents[1] / "scripts" / "fetch_samples.py"
)
fs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fs)
from app.fixtures import mediagen  # noqa: E402


def _jpg(w, h, c=(128, 64, 200)):
    b = BytesIO()
    Image.new("RGB", (w, h), c).save(b, format="JPEG")
    return b.getvalue()


_SOURCES = {
    "photos": [
        {"title": "P1", "license": "CC-BY", "author": "A1", "url": "https://cdn.example/p1.jpg"},
        {
            "title": "P2",
            "license": "CC0",
            "author": "A2",
            "crop": "square",
            "url": "https://cdn.example/p2.jpg",
        },
    ],
    "videos": [],
    "comics": [
        {
            "name": "C1",
            "title": "Comic1",
            "license": "CC-BY-SA",
            "author": "CA",
            "files": [f"https://cdn.example/c1_{i}.jpg" for i in (1, 2, 3)],
        },
    ],
}


def _fake_fetch(url):
    url = url.lower()
    if "p1" in url:
        return _jpg(2400, 1200, (200, 50, 50))
    if "p2" in url:
        return _jpg(2400, 1200, (50, 200, 50))
    if "c1_1" in url:
        return _jpg(900, 1300, (10, 200, 10))
    if "c1_2" in url:
        return _jpg(900, 1300, (10, 10, 200))
    if "c1_3" in url:
        return _jpg(900, 1300, (200, 10, 10))
    raise ValueError(url)


@contextlib.contextmanager
def _ctx(tmp_path, fetch_se=None):
    out = tmp_path / "out"
    fb = mock.MagicMock(side_effect=fetch_se or _fake_fetch)
    with contextlib.ExitStack() as s:
        s.enter_context(mock.patch.object(fs, "load_sources", return_value=_SOURCES))
        s.enter_context(mock.patch.object(fs, "fetch_bytes", fb))
        s.enter_context(mock.patch.object(fs, "THROTTLE_SECONDS", 0))
        s.enter_context(mock.patch.object(mediagen, "IMG_COUNT", 3))
        s.enter_context(mock.patch.object(mediagen, "BOOK_COUNT", 1))
        s.enter_context(mock.patch.object(mediagen, "VIDEO_COUNT", 0))
        s.enter_context(mock.patch.object(mediagen, "_ffmpeg", lambda: None))
        yield out, fb


def test_photos_replaced_square_crop_and_thumbs(tmp_path):
    with _ctx(tmp_path) as (out, _):
        rc = fs.main(["--out", str(out), "--force"])
    assert rc == 0
    img0 = Image.open(out / "images" / "0.jpg")
    assert max(img0.size) <= 1920
    img1 = Image.open(out / "images" / "1.jpg")
    assert img1.size[0] == img1.size[1]
    assert (out / "images" / "0_thumb.jpg").exists()
    assert (out / "images" / "1_thumb.jpg").exists()


def test_comic_cbz_pages_and_comicinfo(tmp_path):
    with _ctx(tmp_path) as (out, _):
        rc = fs.main(["--out", str(out), "--force"])
    assert rc == 0
    with zipfile.ZipFile(out / "books" / "0.cbz") as z:
        pages = sorted(n for n in z.namelist() if n.startswith("page_"))
        assert pages == ["page_001.jpg", "page_002.jpg", "page_003.jpg"]
        ci = z.read("ComicInfo.xml").decode()
        assert ">3<" in ci and "PageCount" in ci
    img = mediagen.read_cbz_page(out / "books" / "0.cbz", 1)
    assert img is not None


def test_manifest_and_no_refetch(tmp_path):
    with _ctx(tmp_path) as (out, fb):
        assert fs.main(["--out", str(out), "--force"]) == 0
        assert fb.call_count == 5  # 2 photos + 3 comic pages
        assert fs.main(["--out", str(out)]) == 0
        assert fb.call_count == 5  # zero new calls
    manifest = json.loads((out / "manifest.json").read_text())
    items = manifest["items"]
    assert len(items) == 3
    for it in items:
        assert it["license"] and it["author"]
        assert "file" in it and "kind" in it and "title" in it and "url" in it


def test_fetch_bytes_host_validation():
    import pytest

    with pytest.raises(ValueError):
        fs.fetch_bytes("https://example.com/x.jpg")


def test_oserror_photo0_placeholder_kept(tmp_path):
    state = {"n": 0}

    def flaky(url):
        state["n"] += 1
        if state["n"] == 1:
            raise OSError("simulated network failure")
        return _fake_fetch(url)

    with _ctx(tmp_path, fetch_se=flaky) as (out, _):
        rc = fs.main(["--out", str(out), "--force"])
    assert rc == 0
    assert (out / "images" / "0.jpg").exists()
    img0 = Image.open(out / "images" / "0.jpg")
    assert img0.size != (1920, 960)  # still the placeholder
    img1 = Image.open(out / "images" / "1.jpg")
    assert max(img1.size) <= 1920  # was replaced


def test_dry_run_no_fetch(tmp_path):
    with _ctx(tmp_path) as (out, fb):
        rc = fs.main(["--out", str(out), "--force", "--dry-run"])
    assert rc == 0
    fb.assert_not_called()
