import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from app.sources.base import Post
from app.targets.comicinfo import build_cbz, comic_info
from app.targets.placement import Plan


def _post() -> Post:
    return Post(
        source="nhentai",
        post_id="1",
        title="T",
        tags={"parody": ["Foo"], "artist": ["A"]},
        source_url="https://x/1",
    )


def test_series_numbered():
    post = _post()
    placement = Plan(kind="series", series="Root", number="2", folder=None, via="tag")
    root = ET.fromstring(comic_info(post, 5, placement))
    assert root.findtext("Series") == "Root"
    assert root.findtext("Number") == "2"


def test_series_no_number():
    post = _post()
    placement = Plan(kind="series", series="Root", number="", folder=None, via="tag")
    root = ET.fromstring(comic_info(post, 5, placement))
    assert root.findtext("Series") == "Root"
    assert root.find("Number") is None


def test_oneshot_no_series():
    post = _post()
    placement = Plan(kind="oneshot", series=None, number="", folder=None, via="tag")
    root = ET.fromstring(comic_info(post, 5, placement))
    assert root.find("Series") is None
    assert root.find("Number") is None


def test_placement_none_legacy():
    post = _post()
    root = ET.fromstring(comic_info(post, 5))
    assert root.findtext("Series") == "Foo"


def test_build_cbz_deterministic_and_comicinfo(tmp_path: Path):
    post = _post()
    placement = Plan(kind="series", series="Root", number="2", folder=None, via="tag")

    page_a = tmp_path / "a.jpg"
    page_b = tmp_path / "b.png"
    page_a.write_bytes(b"\xff\xd8\xff\xd9")
    page_b.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00")

    dest1 = tmp_path / "out1.cbz"
    dest2 = tmp_path / "out2.cbz"

    build_cbz(dest1, [page_a, page_b], post, placement)
    build_cbz(dest2, [page_a, page_b], post, placement)

    assert dest1.read_bytes() == dest2.read_bytes()

    with zipfile.ZipFile(dest1) as zf:
        names = zf.namelist()
        assert "001.jpg" in names
        assert "002.png" in names
        comicinfo_bytes = zf.read("ComicInfo.xml")

    root = ET.fromstring(comicinfo_bytes)
    assert root.findtext("Series") == "Root"
    assert root.findtext("Number") == "2"
