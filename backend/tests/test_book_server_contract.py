"""One contract suite for every `BookServer`: the Komga adapter (mock HTTP) and the fake."""

from __future__ import annotations

import json
import re

import httpx
import pytest

from app.bookserver.base import BookServerError, LibraryDTO, MetadataPatch
from app.bookserver.komga import KomgaBookServer, book_dto, series_dto
from app.komga import Komga, KomgaError
from tests.fake_book_server import FakeBookServer


def _book(i: int, series: str = "s1", deleted: bool = False) -> dict:
    return {
        "id": f"b{i}",
        "seriesId": series,
        "libraryId": "L1",
        "name": f"Book {i}",
        "url": f"/data/s/book{i}.cbz",
        "created": f"2026-01-0{i}T00:00:00Z",
        "deleted": deleted,
        "media": {"pagesCount": 5},
        "readProgress": None,
        "metadata": {"title": f"Book {i}", "tags": ["x"], "summary": "", "links": []},
    }


def _series() -> dict:
    return {
        "id": "s1",
        "libraryId": "L1",
        "name": "Series",
        "url": "/data/s",
        "created": "2026-01-01T00:00:00Z",
        "booksCount": 3,
        "booksReadCount": 0,
        "metadata": {"title": "Series", "tags": []},
        "booksMetadata": {"tags": ["y"]},
    }


BOOKS = [_book(1), _book(2), _book(3), _book(4, deleted=True)]
LIBS = [{"id": "L1", "name": "Lib", "root": "/data", "oneshotsDirectory": "oneshots"}]


class _MockKomga:
    """Just enough Komga REST over httpx.MockTransport; records the calls."""

    def __init__(self) -> None:
        self.books = {b["id"]: json.loads(json.dumps(b)) for b in BOOKS}
        self.calls: list[tuple[str, str, dict]] = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        path, method = req.url.path, req.method
        body = json.loads(req.content) if req.content else {}
        self.calls.append((method, str(req.url.query, "ascii"), body))
        if path == "/api/v1/libraries":
            return httpx.Response(200, json=LIBS)
        if method == "POST" and path.endswith("/scan"):
            return httpx.Response(202)
        if method == "POST" and path.endswith("/empty-trash"):
            return httpx.Response(202)
        if method == "POST" and path in ("/api/v1/books/list", "/api/v1/series/list"):
            return self._list(path, req, body)
        m = re.fullmatch(r"/api/v1/(books|series)/(\w+)", path)
        if m and method == "GET":
            rows = self.books if m[1] == "books" else {"s1": _series()}
            row = rows.get(m[2])
            return httpx.Response(200, json=row) if row else httpx.Response(404)
        if method == "PATCH":
            rp = re.fullmatch(r"/api/v1/books/(\w+)/read-progress", path)
            if rp:
                self.books[rp[1]]["readProgress"] = {
                    "page": body["page"],
                    "completed": body["completed"],
                }
                return httpx.Response(204)
            md = re.fullmatch(r"/api/v1/(books|series)/(\w+)/metadata", path)
            if md and md[2] in self.books:
                self.books[md[2]]["metadata"].update(
                    {k: v for k, v in body.items() if not k.endswith("Lock")}
                )
                return httpx.Response(204)
            return httpx.Response(404)
        if "/pages/" in path or path.endswith("/thumbnail"):
            if "/b9" in path:
                return httpx.Response(404)
            return httpx.Response(200, content=b"jpg", headers={"content-type": "image/jpeg"})
        return httpx.Response(500)

    def _list(self, path: str, req: httpx.Request, body: dict) -> httpx.Response:
        page, size = int(req.url.params["page"]), int(req.url.params["size"])
        cond = json.dumps(body.get("condition", {}))
        if path.endswith("series/list"):
            rows = [_series()]
        elif "isTrue" in cond:
            rows = [b for b in self.books.values() if b["deleted"]]
        else:
            q = body.get("fullTextSearch", "").lower()
            rows = [
                b
                for b in self.books.values()
                if not b["deleted"] and q in b["metadata"]["title"].lower()
            ]
        part = rows[page * size : (page + 1) * size]
        pages = max(1, -(-len(rows) // size))
        return httpx.Response(
            200,
            json={
                "content": part,
                "totalPages": pages,
                "totalElements": len(rows),
                "last": page + 1 >= pages,
            },
        )


def _komga() -> KomgaBookServer:
    mock = _MockKomga()
    client = httpx.Client(base_url="http://komga", transport=httpx.MockTransport(mock))
    server = KomgaBookServer(Komga("http://komga", "k", client))
    server.mock = mock  # type: ignore[attr-defined]
    return server


def _fake() -> FakeBookServer:
    return FakeBookServer(
        libraries=[LibraryDTO("L1", "Lib", "/data", "oneshots")],
        series=[series_dto(_series())],
        books=[book_dto(b) for b in BOOKS],
    )


@pytest.fixture(params=["komga", "fake"])
def server(request):  # noqa: ANN001, ANN201
    return _komga() if request.param == "komga" else _fake()


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


def test_komga_error_is_a_book_server_error() -> None:
    assert issubclass(KomgaError, BookServerError)


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
        _komga().set_metadata("books", "b1", MetadataPatch())
    assert err.value.code == "bad_request"


def test_find_by_path_skips_deleted(server) -> None:  # noqa: ANN001
    found = server.find_by_path("books", "L1", "/data/s/book2.cbz", "Book 2")
    assert found is not None and found.id == "b2"
    assert server.find_by_path("books", "L1", "/data/s/book4.cbz", "Book 4") is None


def test_series_books(server) -> None:  # noqa: ANN001
    books, truncated = server.series_books("s1")
    assert truncated is False and {b.id for b in books} >= {"b1", "b2", "b3"}


def test_scan_and_trash(server) -> None:  # noqa: ANN001
    server.scan_library("L1")
    assert [b.id for b in server.list_deleted("books", "L1")] == ["b4"]
    server.purge_deleted("L1")


def test_images(server) -> None:  # noqa: ANN001
    for img in (
        server.open_thumb("books", "b1"),
        server.open_page("b1", 1),
        server.open_page_thumb("b1", 1, 200),
    ):
        assert img.content_type.startswith("image/")
        assert b"".join(img.iter_bytes()) == b"jpg"
        img.close()


def test_image_not_found(server) -> None:  # noqa: ANN001
    with pytest.raises(BookServerError) as err:
        server.open_page("b9", 1)
    assert err.value.code == "not_found"


def test_valid_id(server) -> None:  # noqa: ANN001
    assert server.valid_id("abc123") and not server.valid_id("../x")


def test_ping(server) -> None:  # noqa: ANN001
    server.ping()


def test_komga_adapter_maps_page_base_and_sort() -> None:
    server = _komga()
    server.list_books(2, 2, "", "created_desc")
    # the Komga page index is 0-based; Pearlie page 2 -> 1
    _method, query, _body = server.mock.calls[-1]  # type: ignore[attr-defined]
    assert "page=1" in query and "size=2" in query and "sort=createdDate%2Cdesc" in query
