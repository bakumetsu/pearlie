"""Tolerance tests: stash_library mapping tolerates missing/null DTO fields."""

from __future__ import annotations

import logging

import pytest

from app.targets import stash_library
from tests.test_stash_library import image_dto, scene_dto

_IMG_KEYS = (
    "title", "rating100", "created_at", "urls", "tags", "visual_files",
)
_SCN_KEYS = (
    "title", "rating100", "created_at", "urls", "tags",
    "files", "sceneStreams", "studio", "date",
)


@pytest.mark.parametrize(
    "mapper", [stash_library.image_item, stash_library.image_detail]
)
@pytest.mark.parametrize("key", _IMG_KEYS)
def test_image_optional_key_deleted(mapper, key) -> None:
    """Deleting an optional image DTO key still yields a mapped object."""
    dto = image_dto()
    dto.pop(key, None)
    assert mapper(dto) is not None


@pytest.mark.parametrize(
    "mapper", [stash_library.image_item, stash_library.image_detail]
)
@pytest.mark.parametrize("key", _IMG_KEYS)
def test_image_optional_key_none(mapper, key) -> None:
    """Setting an optional image DTO key to None still yields a mapped object."""
    dto = image_dto()
    dto[key] = None
    assert mapper(dto) is not None


@pytest.mark.parametrize(
    "mapper", [stash_library.video_item, stash_library.video_detail]
)
@pytest.mark.parametrize("key", _SCN_KEYS)
def test_scene_optional_key_deleted(mapper, key) -> None:
    """Deleting an optional scene DTO key still yields a mapped object."""
    dto = scene_dto()
    dto.pop(key, None)
    assert mapper(dto) is not None


@pytest.mark.parametrize(
    "mapper", [stash_library.video_item, stash_library.video_detail]
)
@pytest.mark.parametrize("key", _SCN_KEYS)
def test_scene_optional_key_none(mapper, key) -> None:
    """Setting an optional scene DTO key to None still yields a mapped object."""
    dto = scene_dto()
    dto[key] = None
    assert mapper(dto) is not None


def test_empty_lists_and_none_dims() -> None:
    """Empty tag/url/file lists and None dimensions map without error."""
    img = image_dto(tags=[], urls=[], visual_files=[])
    item = stash_library.image_item(img)
    assert item.width is None
    assert item.height is None

    img2 = image_dto(title="", visual_files=[])
    assert stash_library.image_item(img2).title == "Image 1"

    scn = scene_dto(tags=[], urls=[], files=[])
    vitem = stash_library.video_item(scn)
    assert vitem.width is None
    assert vitem.height is None
    assert vitem.duration_s is None

    scn2 = scene_dto(title="", files=[])
    assert stash_library.video_item(scn2).title == "Video 2"


def test_nested_nulls_tolerated() -> None:
    """Nested null/malformed entries in files, tags, studio are tolerated."""
    assert stash_library.video_item(scene_dto(files=[None])) is not None
    assert (
        stash_library.image_item(image_dto(visual_files=[None])) is not None
    )
    assert stash_library.video_item(scene_dto(files=[{}])) is not None
    assert stash_library.video_item(scene_dto(files="oops")) is not None

    bad_tags = [None, {"name": None}, {"name": ""}, {}, {"name": "ok"}]
    item = stash_library.image_item(image_dto(tags=bad_tags))
    assert item.tags == ["ok"]

    assert stash_library.video_detail(scene_dto(studio=None)) is not None
    assert (
        stash_library.video_detail(
            scene_dto(studio={"name": None})
        )
        is not None
    )

    null_dur = scene_dto(
        files=[
            {
                "basename": "c.mp4",
                "width": 100,
                "height": 100,
                "duration": None,
                "size": 10,
            },
        ],
    )
    assert stash_library.video_item(null_dur).duration_s is None

    null_bn = scene_dto(
        title="",
        files=[
            {
                "basename": None,
                "width": 100,
                "height": 100,
                "duration": 10.0,
                "size": 10,
            },
        ],
    )
    assert stash_library.video_item(null_bn).title == "Video 2"


def test_scene_streams_filtering() -> None:
    """Invalid sceneStreams yield no StreamOption; valid ones do."""
    bad = scene_dto(
        sceneStreams=[None, {"label": "x"}, {"url": None}]
    )
    assert stash_library.video_detail(bad).fallback_streams == []

    good = scene_dto(
        sceneStreams=[
            {"url": "http://h/scene/1/stream.mp4?resolution=ORIGINAL"},
        ],
    )
    streams = stash_library.video_detail(good).fallback_streams
    assert len(streams) == 1


def test_map_items_bad_entries_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """map_items logs warnings for bad entries without leaking URLs."""
    good = image_dto(id="1")
    all_none = image_dto(id="2")
    for k in ("title", "rating100", "created_at", "urls", "tags",
              "visual_files"):
        all_none[k] = None
    no_id = image_dto(id="3")
    del no_id["id"]

    entries = [good, all_none, no_id, {"id": None}, "not a dict"]
    with caplog.at_level(logging.WARNING):
        items, bad_ids = stash_library.map_items(entries,
                                                 stash_library.image_item)

    assert len(items) == 2
    assert bad_ids == ["unknown", "unknown", "unknown"]

    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(warnings) == 3
    for rec in warnings:
        msg = rec.getMessage()
        assert "unknown" in msg
        assert "Error" in msg or "Exception" in msg
        assert "example.com" not in msg
        assert "http" not in msg


def test_added_at_empty_sorts_first() -> None:
    """Item with empty added_at sorts before a dated item without raising."""
    no_date = image_dto(id="1")
    del no_date["created_at"]
    item_empty = stash_library.image_item(no_date)
    assert item_empty.added_at == ""

    item_date = stash_library.image_item(image_dto(id="2"))
    ordered = sorted(
        [item_empty, item_date], key=lambda i: i.added_at
    )
    assert ordered[0].added_at == ""
    assert ordered[1].added_at != ""
