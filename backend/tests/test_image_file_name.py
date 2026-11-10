# Tests for LibraryItem.file_name (T-64).

import pytest

from app.targets import stash_library


def test_image_item_file_name():
    dto = {
        "id": "1",
        "title": "photo",
        "created_at": "2024-01-01T00:00:00",
        "visual_files": [{"basename": "photo.jpg"}],
    }
    assert stash_library.image_item(dto).file_name == "photo.jpg"


def test_image_detail_file_name():
    dto = {
        "id": "1",
        "title": "photo",
        "created_at": "2024-01-01T00:00:00",
        "visual_files": [{"basename": "photo.jpg"}],
    }
    assert stash_library.image_detail(dto).file_name == "photo.jpg"


def test_image_item_empty_visual_files():
    dto = {
        "id": "1",
        "title": "photo",
        "created_at": "2024-01-01T00:00:00",
        "visual_files": [],
    }
    assert stash_library.image_item(dto).file_name is None


def test_video_item_no_file_name():
    dto = {
        "id": "1",
        "title": "clip",
        "created_at": "2024-01-01T00:00:00",
        "files": [{"basename": "clip.mp4", "duration": 1.0}],
    }
    assert stash_library.video_item(dto).file_name is None


@pytest.fixture(autouse=True)
def _reset(client):
    client.post("/api/_fixture/reset")
    yield
    client.post("/api/_fixture/reset")


def test_fixture_images_have_extension(client):
    items = client.get("/api/library/stash/images").json()["items"]
    assert items
    for item in items:
        fn = item.get("file_name")
        assert fn is not None and "." in fn


def test_fixture_videos_books_series_no_file_name(client):
    for path in (
        "/api/library/stash/videos",
        "/api/library/komga/books",
        "/api/library/komga/series",
    ):
        for item in client.get(path).json()["items"]:
            assert item.get("file_name") is None


def test_fixture_image_detail_file_name(client):
    assert client.get("/api/library/images/0").json()["file_name"] == "image-0.jpg"
