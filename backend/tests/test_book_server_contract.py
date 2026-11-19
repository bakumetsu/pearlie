"""One contract suite for every `BookServer`: the Stump adapter (mock HTTP) and the fake."""

from __future__ import annotations

import httpx
import pytest

from app.bookserver.base import BookServerError, LibraryDTO, MetadataPatch
from app.bookserver.stump import StumpBookServer, book_dto, series_dto
from app.stump import Stump, StumpError
from tests import stump_mock
from tests.fake_book_server import FakeBookServer


def _stump() -> StumpBookServer:
    mock = stump_mock.MockStump(
        [stump_mock.lib()],
        [stump_mock.series()],
        [stump_mock.book(1), stump_mock.book(2), stump_mock.book(3), stump_mock.book(4, gone=True)],
    )
    client = httpx.Client(base_url="http://stump", transport=httpx.MockTransport(mock))
    server = StumpBookServer(Stump("http://stump", "k", client))
    server.mock = mock  # type: ignore[attr-defined]
    return server


def _fake() -> FakeBookServer:
    return FakeBookServer(
        libraries=[LibraryDTO("L1", "Lib", "/data", "oneshots")],
        series=[series_dto(stump_mock.series())],
        books=[book_dto(stump_mock.book(i, gone=i == 4)) for i in (1, 2, 3, 4)],
    )


@pytest.fixture(params=["stump", "fake"])
def server(request):  # noqa: ANN001, ANN201
    return {"stump": _stump, "fake": _fake}[request.param]()


def test_list_libraries(server) -> None:  # noqa: ANN001
    libs = server.list_libraries()
    assert [(x.id, x.root, x.oneshots_dir) for x in libs] == [("L1", "/data", "oneshots")]


def test_list_books_is_one_based_and_hides_deleted(server) -> None:  # noqa: ANN001
    first = server.list_books(1, 2, "", "created_desc")
    assert (first.page, first.size, first.total_pages, first.total_items) == (1, 2, 2, 3)
    assert not first.last and len(first.items) == 2
    second = server.list_books(2, 2, "", "created_desc")
    assert second.last and [b.id for b in second.items] == ["b3"]
    assert all(not b.deleted for b in first.items + second.items)


def test_search_narrows(server) -> None:  # noqa: ANN001
    hit = server.list_books(1, 10, "book 2", "created_desc")
    assert [b.id for b in hit.items] == ["b2"]


def test_series_list_and_tags_union(server) -> None:  # noqa: ANN001
    page = server.list_series(1, 10, "", "created_desc")
    assert [s.id for s in page.items] == ["s1"]
    assert page.items[0].tags == ["y"]


def test_get_not_found_is_neutral(server) -> None:  # noqa: ANN001
    with pytest.raises(BookServerError) as err:
        server.get_book("nope")
    assert (err.value.code, err.value.status) == ("not_found", 404)


def test_stump_error_is_a_book_server_error() -> None:
    assert issubclass(StumpError, BookServerError)


def test_progress_round_trip(server) -> None:  # noqa: ANN001
    server.set_progress("b1", 3, False)
    book = server.get_book("b1")
    assert (book.read_page, book.read_done) == (3, False)
    server.set_progress("b1", 5, True)
    assert server.get_book("b1").read_done is True


def test_tags_and_metadata(server) -> None:  # noqa: ANN001
    server.set_tags("books", "b1", ["b", "a"])
    assert sorted(server.get_book("b1").tags) == ["a", "b"]
    server.set_metadata("books", "b1", MetadataPatch(title="New", summary="S"))
    book = server.get_book("b1")
    assert (book.title, book.summary) == ("New", "S")


def test_empty_patch_is_bad_request() -> None:
    with pytest.raises(BookServerError) as err:
        _stump().set_metadata("books", "b1", MetadataPatch())
    assert err.value.code == "bad_request"


def test_find_by_path_skips_deleted(server) -> None:  # noqa: ANN001
    found = server.find_by_path("books", "L1", "/data/s/book2.cbz", "Book 2")
    assert found is not None and found.id == "b2"
    assert server.find_by_path("books", "L1", "/data/s/book4.cbz", "Book 4") is None


def test_series_books(server) -> None:  # noqa: ANN001
    books, truncated = server.series_books("s1")
    assert truncated is False and {b.id for b in books} >= {"b1", "b2", "b3"}


def test_scan(server) -> None:  # noqa: ANN001
    server.scan_library("L1")


def test_trash(server) -> None:  # noqa: ANN001
    assert [b.id for b in server.list_deleted("books", "L1")] == ["b4"]
    server.purge_deleted("L1")


def test_images(server) -> None:  # noqa: ANN001
    stump = server.kind == "stump"
    cases = (
        (server.open_thumb("books", "b1"), b"jpg", False),
        (server.open_page("b1", 1), stump_mock.png() if stump else b"jpg", False),
        (server.open_page_thumb("b1", 1, 200), b"jpg", stump),
    )
    for img, want, made_here in cases:
        assert img.content_type.startswith("image/")
        body = b"".join(img.iter_bytes())
        if made_here:
            assert body.startswith(b"\xff\xd8")  # Pearlie downscaled the page itself
        else:
            assert body == want
        img.close()


def test_image_not_found(server) -> None:  # noqa: ANN001
    with pytest.raises(BookServerError) as err:
        server.open_page("b9", 1)
    assert err.value.code == "not_found"


def test_valid_id(server) -> None:  # noqa: ANN001
    assert server.valid_id("abc123") and not server.valid_id("../x")


def test_ping(server) -> None:  # noqa: ANN001
    server.ping()

