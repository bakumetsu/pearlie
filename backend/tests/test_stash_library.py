"""Tests for Stash library mapping and StashClient read methods."""

from __future__ import annotations

import json

import httpx
import pytest

from app.targets import stash_library
from app.targets.stash_client import StashClient, StashError

URL = "http://stash.test"
API_KEY = "k"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def image_dto(id="1", **over):
    """Return a minimal valid Stash image DTO."""
    d = {
        "id": id,
        "title": "Test Image",
        "rating100": 80,
        "created_at": "2024-01-01T00:00:00Z",
        "urls": ["https://example.com/src.jpg"],
        "tags": [{"name": "tag_b"}, {"name": "tag_a"}],
        "visual_files": [
            {"basename": "photo.jpg", "width": 1920, "height": 1080, "size": 1234},
        ],
    }
    d.update(over)
    return d


def scene_dto(id="2", **over):
    """Return a minimal valid Stash scene (video) DTO."""
    d = {
        "id": id,
        "title": "Test Scene",
        "rating100": 60,
        "created_at": "2024-02-01T00:00:00Z",
        "urls": ["https://example.com/scene.mp4"],
        "tags": [{"name": "tag_b"}, {"name": "tag_a"}],
        "files": [
            {
                "basename": "clip.mp4",
                "width": 1920,
                "height": 1080,
                "duration": 120.0,
                "video_codec": "h264",
                "size": 5678,
            },
        ],
    }
    d.update(over)
    return d


def make_stash_client(handler) -> StashClient:
    """Build a StashClient backed by an httpx.MockTransport."""
    return StashClient(
        URL,
        API_KEY,
        client=httpx.Client(base_url=URL, transport=httpx.MockTransport(handler)),
    )


# ---------------------------------------------------------------------------
# stash_library pure-function tests
# ---------------------------------------------------------------------------


def test_rating_from_100():
    """rating_from_100 converts 0-100 to 1-5 scale; None/0 yield None."""
    cases = [
        (None, None),
        (0, None),
        (1, 1),
        (20, 1),
        (21, 2),
        (40, 2),
        (41, 3),
        (100, 5),
    ]
    for r, expected in cases:
        assert stash_library.rating_from_100(r) == expected, f"rating_from_100({r!r})"


def test_valid_id():
    """valid_id accepts only non-empty ASCII digit strings."""
    assert stash_library.valid_id("12") is True
    assert stash_library.valid_id("") is False
    assert stash_library.valid_id("1a") is False
    assert stash_library.valid_id("../x") is False
    assert stash_library.valid_id("\u0661\u0662") is False  # arabic-indic digits


def test_stash_sort():
    """stash_sort maps UI sort keys to (field, direction)."""
    assert stash_library.stash_sort("newest") == ("created_at", "DESC")
    assert stash_library.stash_sort("rating") == ("rating", "DESC")
    assert stash_library.stash_sort("random", 123) == ("random_123", "DESC")
    field, direction = stash_library.stash_sort("random")
    assert field.startswith("random_")
    assert direction == "DESC"


def test_image_item():
    """image_item maps a Stash image DTO to a LibraryItem with correct fields."""
    item = stash_library.image_item(image_dto())
    assert item.title == "Test Image"
    assert item.tags == ["tag_a", "tag_b"]
    assert item.width == 1920
    assert item.height == 1080
    assert item.thumb_url == "/api/media/stash/images/1/thumb"
    assert item.added_at == "2024-01-01T00:00:00Z"

    # title empty -> stem of first file basename
    item2 = stash_library.image_item(image_dto(title=""))
    assert item2.title == "photo"

    # no title and no files -> fallback "Image <id>"
    item3 = stash_library.image_item(image_dto(title="", visual_files=[]))
    assert item3.title == "Image 1"

    # missing created_at maps with added_at == ""
    no_date = image_dto()
    del no_date["created_at"]
    item_no_date = stash_library.image_item(no_date)
    assert item_no_date.added_at == ""

    # dto without "id" still raises KeyError
    no_id = image_dto()
    del no_id["id"]
    with pytest.raises(KeyError):
        stash_library.image_item(no_id)


def test_video_item():
    """video_item maps a Stash scene DTO with poster URL and duration."""
    item = stash_library.video_item(scene_dto())
    assert item.thumb_url == "/api/media/stash/videos/2/poster"
    assert item.duration_s == 120.0

    # width/height None when files is empty
    item_empty = stash_library.video_item(scene_dto(files=[]))
    assert item_empty.width is None
    assert item_empty.height is None
    assert item_empty.duration_s is None


def test_video_item_duration_per_scene():
    """video_item reads duration from the scene's files entry, not a constant."""
    item_a = stash_library.video_item(
        scene_dto(id="2", files=[{
            "basename": "clip.mp4",
            "width": 1920,
            "height": 1080,
            "duration": 61.5,
            "video_codec": "h264",
            "size": 5678,
        }])
    )
    item_b = stash_library.video_item(
        scene_dto(id="3", files=[{
            "basename": "clip.mp4",
            "width": 1920,
            "height": 1080,
            "duration": 3725.0,
            "video_codec": "h264",
            "size": 5678,
        }])
    )
    assert item_a.duration_s == 61.5
    assert item_b.duration_s == 3725.0


def test_image_detail():
    """image_detail produces full_url, mime, Tag objects, and source_url_text."""
    det = stash_library.image_detail(image_dto())
    assert det.full_url == "/api/media/stash/images/1/full"
    assert det.mime == "image/jpeg"
    assert len(det.tags) == 2
    assert det.tags[0].name == "tag_a"
    assert det.tags[1].name == "tag_b"
    assert det.source_url_text == "https://example.com/src.jpg"

    # urls empty -> source_url_text is None
    det_no_url = stash_library.image_detail(image_dto(urls=[]))
    assert det_no_url.source_url_text is None


def test_video_detail():
    """video_detail produces stream_url, mime, and video_codec."""
    det = stash_library.video_detail(scene_dto())
    assert det.stream_url == "/api/media/stash/videos/2/stream"
    assert det.mime == "video/mp4"
    assert det.video_codec == "h264"

    # .mkv -> video/x-matroska
    det_mkv = stash_library.video_detail(
        scene_dto(
            files=[
                {
                    "basename": "clip.mkv",
                    "width": 1920,
                    "height": 1080,
                    "duration": 60.0,
                    "video_codec": "h265",
                    "size": 999,
                },
            ]
        )
    )
    assert det_mkv.mime == "video/x-matroska"
    assert det_mkv.video_codec == "h265"


def test_map_items():
    """map_items collects good items and bad ids; missing/None id yields 'unknown'."""
    good = image_dto(id="1")
    bad = image_dto(id="9")
    del bad["id"]

    items, bad_ids = stash_library.map_items([good, bad], stash_library.image_item)
    assert len(items) == 1
    assert items[0].id == "1"
    assert bad_ids == ["unknown"]

    # non-dict entry produces "unknown"
    items2, bad_ids2 = stash_library.map_items(["not_a_dict"], stash_library.image_item)  # pyright: ignore[reportArgumentType]
    assert items2 == []
    assert bad_ids2 == ["unknown"]


def test_list_notice():
    """list_notice builds a Problem for unsupported options; None when clean."""
    # Nothing -> None
    assert stash_library.list_notice(None, []) is None

    # favorite only -> option_ignored
    p = stash_library.list_notice(True, [])
    assert p is not None
    assert p.code == "option_ignored"

    # bad ids + favorite -> code items_unreadable, both messages "; " joined
    p2 = stash_library.list_notice(True, ["9", "8"])
    assert p2 is not None
    assert p2.code == "items_unreadable"
    assert "item(s) could not be read" in p2.message
    assert "favorite=true" in p2.message
    assert "; " in p2.message

    # more than 10 bad ids -> only first 10 listed
    many = [f"bad{i:02d}" for i in range(15)]
    p3 = stash_library.list_notice(None, many)
    assert p3 is not None
    assert p3.code == "items_unreadable"
    for i in range(10):
        assert f"bad{i:02d}" in p3.message
    for i in range(10, 15):
        assert f"bad{i:02d}" not in p3.message


# ---------------------------------------------------------------------------
# StashClient read-method tests (MockTransport, no real server)
# ---------------------------------------------------------------------------


def test_stash_client_list_images():
    """list_images sends correct variables and returns (images, count, agg)."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "data": {
                    "findImages": {
                        "count": 7,
                        "megapixels": 12.5,
                        "filesize": 4096,
                        "images": [image_dto()],
                    }
                }
            },
        )

    client = make_stash_client(handler)
    images, count, agg = client.list_images(
        page=2, per_page=5, q="x", sort="created_at", direction="DESC"
    )
    assert count == 7
    assert len(images) == 1
    assert images[0]["id"] == "1"
    assert agg == {"megapixels": 12.5, "size_bytes": 4096}
    assert "megapixels filesize" in captured["body"]["query"]
    assert captured["body"]["variables"] == {
        "f": {"page": 2, "per_page": 5, "q": "x", "sort": "created_at", "direction": "DESC"},
    }


def test_stash_client_get_image_none():
    """get_image returns None when Stash returns findImage: null."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"findImage": None}})

    client = make_stash_client(handler)
    assert client.get_image("99") is None


def test_stash_client_list_scenes():
    """list_scenes sends correct variables and returns (scenes, count, agg)."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "data": {
                    "findScenes": {
                        "count": 3,
                        "filesize": 999,
                        "scenes": [scene_dto()],
                    }
                }
            },
        )

    client = make_stash_client(handler)
    scenes, count, agg = client.list_scenes(
        page=1, per_page=10, q="", sort="rating", direction="DESC"
    )
    assert count == 3
    assert len(scenes) == 1
    assert scenes[0]["id"] == "2"
    assert agg == {"megapixels": None, "size_bytes": 999}
    assert captured["body"]["variables"]["f"]["sort"] == "rating"


def test_stash_client_get_scene_none():
    """get_scene returns None when Stash returns findScene: null."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"findScene": None}})

    client = make_stash_client(handler)
    assert client.get_scene("99") is None


def test_stash_client_graphql_errors():
    """A GraphQL errors response raises StashError with code 'upstream_error'."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"errors": [{"message": "Validation failed"}]}
        )

    client = make_stash_client(handler)
    with pytest.raises(StashError) as exc:
        client.list_images(page=1, per_page=10, q="", sort="created_at", direction="DESC")
    assert exc.value.code == "upstream_error"
