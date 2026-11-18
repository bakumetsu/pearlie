"""Stump client and adapter: GraphQL error map, pagination, search, page thumbs, key hygiene."""

from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from PIL import Image
from pydantic import SecretStr

from app import stump as stump_mod
from app.bookserver.base import BookServerError
from app.bookserver.factory import book_server_of
from app.bookserver.stump import StumpBookServer, book_dto
from app.stump import Stump, StumpError
from app.thumbcache import PAGE_THUMB_SOURCE, ThumbCache
from tests import stump_mock

KEY = "sk-secret-key-123"


def _server(
    books: list | None = None, cache: ThumbCache | None = None, page: bytes | None = None
) -> tuple[StumpBookServer, stump_mock.MockStump]:
    mock = stump_mock.MockStump(
        [stump_mock.lib()],
        [stump_mock.series()],
        books if books is not None else [stump_mock.book(i) for i in (1, 2, 3)],
        page,
    )
    http = httpx.Client(
        base_url="http://stump",
        headers={"Authorization": f"Bearer {KEY}"},
        transport=httpx.MockTransport(mock),
    )
    return StumpBookServer(Stump("http://stump", KEY, http, sleep=lambda _s: None), cache), mock


def _client(handler) -> Stump:  # noqa: ANN001
    http = httpx.Client(base_url="http://stump", transport=httpx.MockTransport(handler))
    return Stump("http://stump", KEY, http, sleep=lambda _s: None)


def _ops(mock: stump_mock.MockStump, name: str) -> list[dict]:
    return [b for _m, _p, b in mock.calls if b.get("operationName") == name]


def test_queries_have_balanced_braces() -> None:
    names = [n for n in dir(stump_mod) if n.startswith("Q_")]
    assert names
    for name in names:
        q = getattr(stump_mod, name)
        assert q.count("{") == q.count("}") and q.count("(") == q.count(")"), name


def test_bearer_header_is_sent() -> None:
    server, mock = _server()
    server.list_libraries()
    assert mock.headers[-1]["authorization"] == f"Bearer {KEY}"


def test_graphql_not_found_in_http_200() -> None:
    c = _client(lambda r: httpx.Response(200, json={"errors": [{"message": "Media not found"}]}))
    with pytest.raises(StumpError) as err:
        c.gql("X", "query X { a }")
    assert (err.value.code, err.value.status) == ("not_found", 404)


def test_graphql_other_error_hides_server_text() -> None:
    c = _client(lambda r: httpx.Response(200, json={"errors": [{"message": f"boom {KEY}"}]}))
    with pytest.raises(StumpError) as err:
        c.gql("X", "query X { a }")
    assert err.value.code == "upstream_error" and KEY not in str(err.value)


def test_http_and_transport_errors() -> None:
    with pytest.raises(StumpError) as err:
        _client(lambda r: httpx.Response(500)).gql("X", "q")
    assert err.value.code == "upstream_error"

    def boom(_r: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    with pytest.raises(StumpError) as err2:
        _client(boom).gql("X", "q")
    assert (err2.value.code, err2.value.status) == ("upstream_error", 502)
    with pytest.raises(StumpError) as err3:
        _client(lambda r: httpx.Response(200, json={"data": None})).gql("X", "q")
    assert err3.value.code == "upstream_error"


def test_get_missing_is_not_found() -> None:
    server, _ = _server()
    for call in (server.get_book, server.get_series):
        with pytest.raises(BookServerError) as err:
            call("nope")
        assert err.value.code == "not_found"


def test_search_filter_and_name_order() -> None:
    server, mock = _server()
    hit = server.list_books(1, 10, "book 2", "created_desc")
    assert [b.id for b in hit.items] == ["b2"]
    v = _ops(mock, "MediaList")[-1]["variables"]
    assert [next(iter(x)) for x in v["filter"]["_or"]] == ["name", "metadata", "path"]
    assert v["order"] == [{"field": "NAME", "direction": "ASC"}]
    assert (v["page"], v["size"]) == (1, 10)


def test_library_and_series_filters_combine() -> None:
    server, mock = _server()
    server.list_books(1, 10, "", "created_desc", series_id="s1", library_id="L1")
    v = _ops(mock, "MediaList")[-1]["variables"]
    assert v["filter"] == {"_and": [{"seriesId": {"eq": "s1"}}, {"libraryId": {"eq": "L1"}}]}
    assert v["order"] == [{"field": "CREATED_AT", "direction": "DESC"}]


def test_series_books_pages_of_100() -> None:
    many = [dict(stump_mock.book(1), id=f"x{i}", name=f"N{i:03}") for i in range(230)]
    server, mock = _server(many)
    out, truncated = server.series_books("s1")
    assert len(out) == 230 and truncated is False
    assert {b["variables"]["size"] for b in _ops(mock, "MediaList")} == {100}
    assert len(_ops(mock, "MediaList")) == 3


def test_missing_status_counts_as_deleted() -> None:
    server, _ = _server([stump_mock.book(1, gone=True)])
    assert server.get_book("b1").deleted is True


def test_find_by_path_series_and_miss() -> None:
    server, _ = _server()
    found = server.find_by_path("series", "L1", "/data/s", "")
    assert found is not None and found.id == "s1"
    assert server.find_by_path("series", "L1", "/data/zzz", "") is None
    assert server.find_by_path("books", "L1", "/data/nope.cbz", "") is None


def test_oneshots_dir_blank_is_none() -> None:
    server, mock = _server()
    mock.libs[0]["config"]["oneshotsDirectory"] = ""
    assert server.list_libraries()[0].oneshots_dir is None


def test_page_number_is_checked() -> None:
    server, mock = _server()
    for n in (0, -1):
        with pytest.raises(BookServerError) as err:
            server.open_page("b1", n)
        assert err.value.code == "bad_request"
    with pytest.raises(BookServerError):
        server.open_page_thumb("b1", 0, 100)
    assert not [c for c in mock.calls if "/page/" in c[1]]
    server.open_page("b1", 1).close()
    assert mock.calls[-1][1] == "/api/v2/media/b1/page/1"


def test_cover_routes() -> None:
    server, mock = _server()
    server.open_thumb("series", "s1").close()
    server.open_thumb("books", "b1").close()
    assert [c[1] for c in mock.calls] == [
        "/api/v2/series/s1/thumbnail",
        "/api/v2/media/b1/thumbnail",
    ]


def test_page_thumb_downscales_and_caches(tmp_path: Path) -> None:
    cache = ThumbCache(tmp_path / "tc")
    server, mock = _server(cache=cache)
    img = server.open_page_thumb("b1", 2, 100)
    data = b"".join(img.iter_bytes())
    assert img.content_type == "image/jpeg" and img.content_length == str(len(data))
    assert Image.open(io.BytesIO(data)).size == (100, 150)
    assert (tmp_path / "tc" / PAGE_THUMB_SOURCE).is_dir()
    before = len(mock.calls)
    again = b"".join(server.open_page_thumb("b1", 2, 100).iter_bytes())
    assert again == data and len(mock.calls) == before  # served from the disk cache
    cache.wait_idle()
    cache.rescan()
    assert cache.stats()["files"] == 1


def test_page_thumb_never_enlarges() -> None:
    server, _ = _server(page=stump_mock.png(50, 80))
    data = b"".join(server.open_page_thumb("b1", 1, 500).iter_bytes())
    assert Image.open(io.BytesIO(data)).size == (50, 80)


def test_page_thumb_bad_image_is_upstream_error() -> None:
    server, _ = _server(page=b"not an image")
    with pytest.raises(BookServerError) as err:
        server.open_page_thumb("b1", 1, 100)
    assert err.value.code == "upstream_error"


def test_page_thumb_works_without_cache() -> None:
    server, _ = _server(cache=None)
    assert b"".join(server.open_page_thumb("b1", 1, 100).iter_bytes()).startswith(b"\xff\xd8")


def test_wait_job_polls_until_completed() -> None:
    server, mock = _server()
    server.client.wait_job("j1")
    assert len(_ops(mock, "Job")) == 2


def test_wait_job_failed_and_timeout() -> None:
    server, mock = _server()
    mock.job_status = ["FAILED"]
    with pytest.raises(StumpError) as err:
        server.client.wait_job("j1")
    assert err.value.code == "upstream_error"
    mock.job_status = ["RUNNING"]
    with pytest.raises(StumpError) as err2:
        server.client.wait_job("j1", timeout=0)
    assert err2.value.status == 504


@pytest.mark.parametrize(
    "call",
    [
        lambda s: s.scan_library("L1"),
        lambda s: s.list_deleted("books", "L1"),
        lambda s: s.purge_deleted("L1"),
        lambda s: s.set_tags("books", "b1", ["a"]),
        lambda s: s.set_progress("b1", 1, False),
    ],
)
def test_write_stubs_raise_not_supported(call) -> None:  # noqa: ANN001
    server, _ = _server()
    with pytest.raises(BookServerError) as err:
        call(server)
    assert err.value.code == "not_supported"


def test_ids_allow_cuid_chars_only() -> None:
    server, _ = _server()
    assert server.valid_id("cl9x2A_-1") and not server.valid_id("../x") and not server.valid_id("")


def test_dto_mapping() -> None:
    d = stump_mock.book(1)
    d["metadata"].update(writers=["W"], links=["http://a"], title=None)
    d["readProgress"] = {"page": 3, "isCompleted": True}
    b = book_dto(d)
    assert (b.title, b.read_page, b.read_done, b.writers, b.tags) == (
        "Book 1",
        3,
        True,
        ["W"],
        ["x"],
    )
    assert b.links == [("http://a", "http://a")] and b.page_count == 5


def _app(url: str) -> SimpleNamespace:
    st = SimpleNamespace(book_server="stump", stump_url=url, stump_api_key=SecretStr(KEY))
    return SimpleNamespace(state=SimpleNamespace(settings=st, komga=None, books=None))


def test_factory_picks_stump_and_caches() -> None:
    app = _app("http://stump")
    first = book_server_of(app)
    assert first.kind == "stump" and book_server_of(app) is first
    with pytest.raises(BookServerError) as err:
        book_server_of(_app(""))
    assert err.value.code == "not_configured"


def test_error_text_holds_no_key() -> None:
    server, _ = _server()
    with pytest.raises(BookServerError) as err:
        server.get_book("nope")
    assert KEY not in repr(err.value) and KEY not in err.value.message
