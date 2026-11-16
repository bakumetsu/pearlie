# Tests for grid GIF play fields (T-299).

from types import SimpleNamespace

import pytest

from app.gif_grid import GIF_GRID_MAX_BYTES, grid_gif_ok, grid_gif_reject
from app.sources.danbooru import Danbooru
from app.targets import stash_library


@pytest.mark.parametrize(
    ("name", "size", "ok"),
    [
        ("a.gif", 1000, True),
        ("A.GIF", 1000, True),
        ("https://x/a.gif?v=1", 1000, True),
        ("a.gif", GIF_GRID_MAX_BYTES, True),
        ("a.gif", GIF_GRID_MAX_BYTES + 1, False),
        ("a.gif", None, False),
        ("a.jpg", 1000, False),
        ("https://x/a.jpg?f=a.gif", 1000, False),
        (None, 1000, False),
    ],
)
def test_grid_gif_ok(name, size, ok):
    assert grid_gif_ok(name, size) is ok


def _stash(basename, size):
    return {
        "id": "5",
        "title": "t",
        "created_at": "2024-01-01T00:00:00",
        "visual_files": [{"basename": basename, "size": size}],
    }


def test_stash_small_gif_gets_gif_url():
    item = stash_library.image_item(_stash("a.gif", 500))
    assert item.gif_url == "/api/media/stash/images/5/full"


def test_stash_big_gif_plays():
    item = stash_library.image_item(_stash("a.gif", 120 * 1024 * 1024))
    assert item.gif_url == "/api/media/stash/images/5/full"


def test_stash_gif_without_size_plays():
    assert stash_library.image_item(_stash("a.gif", None)).gif_url is not None


def test_web_big_gif_stays_still():
    assert grid_gif_reject("a.gif", 120 * 1024 * 1024) == "too_big"
    assert not grid_gif_ok("a.gif", 120 * 1024 * 1024)


def test_stash_jpg_has_no_gif_url():
    assert stash_library.image_item(_stash("a.jpg", 500)).gif_url is None


def _post(**over):
    d = {"id": 1, "file_url": "https://h/a.gif", "image_width": 1, "image_height": 1}
    d.update(over)
    return Danbooru._to_post(SimpleNamespace(_base_url="https://h"), d)  # type: ignore[arg-type]


def test_danbooru_file_size_read():
    assert _post(file_size=1234).file_size == 1234


def test_danbooru_file_size_missing_or_bad():
    assert _post().file_size is None
    assert _post(file_size="12").file_size is None


def test_stash_image_query_reads_video_file_fields():
    from app.targets.stash_client import IMAGE_FIELDS

    assert "... on VideoFile { basename width height size }" in IMAGE_FIELDS
    assert "... on ImageFile { basename width height size }" in IMAGE_FIELDS


def test_stash_gif_stored_as_video_file_plays():
    dto = _stash("clip.GIF", 500)
    dto["visual_files"][0].update(width=10, height=20)  # VideoFile shape: same keys
    assert stash_library.image_item(dto).gif_url == "/api/media/stash/images/5/full"


def test_gif_gate_reject_counts_logged(caplog):
    import logging

    dtos = [_stash("a.gif", 500), _stash("b.gif", None), _stash("e.jpg", 1), _stash("f.png", 1)]
    with caplog.at_level(logging.DEBUG, logger="app.targets.stash_library"):
        stash_library.log_gif_rejects(dtos)
    msg = caplog.messages[-1]
    assert "4 images" in msg and "not_gif=2" in msg
    assert "no_size" not in msg and "too_big" not in msg
    assert ".gif" not in msg and ".jpg" not in msg
