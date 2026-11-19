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
from app.bookserver.base import BookServerError, MetadataPatch
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


def test_graphql_error_is_logged_scrubbed_and_truncated(caplog: pytest.LogCaptureFixture) -> None:
    errors = [
        {"message": "no field x Bearer abcdefgh12345678", "path": ["media", 0, "x"]},
        {"message": "y" * 2000},
    ]
    c = _client(lambda r: httpx.Response(200, json={"errors": errors}))
    with caplog.at_level("WARNING", logger="app.stump"), pytest.raises(StumpError):
        c.gql("MediaList", "query MediaList { a }")
    (rec,) = [r for r in caplog.records if r.name == "app.stump"]
    text = rec.getMessage()
    assert text.startswith("Stump MediaList failed: no field x")
    assert "[media.0.x]" in text and "abcdefgh12345678" not in text
    assert len(text) < 560


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
    assert v["filter"] == {
        "_or": [{"name": {"contains": "book 2"}}, {"metadata": {"title": {"contains": "book 2"}}}]
    }
    assert v["order"] == [{"media": {"field": "NAME", "direction": "ASC"}}]
    assert (v["page"], v["size"]) == (1, 10)


def test_library_and_series_filters_combine() -> None:
    server, mock = _server()
    server.list_books(1, 10, "", "created_desc", series_id="s1", library_id="L1")
    v = _ops(mock, "MediaList")[-1]["variables"]
    assert v["filter"] == {
        "_and": [{"seriesId": {"eq": "s1"}}, {"series": {"libraryId": {"eq": "L1"}}}]
    }
    assert v["order"] == [{"media": {"field": "CREATED_AT", "direction": "DESC"}}]


def test_exact_variables_of_each_list_call() -> None:
    server, mock = _server()
    server.list_series(2, 20, "", "created_desc", library_id="L1")
    server.list_books(1, 20, "", "created_desc", library_id="L1")
    server.series_books("s1")
    server.list_series(1, 20, "ab", "created_desc")
    series_calls = _ops(mock, "SeriesList")
    media_calls = _ops(mock, "MediaList")
    assert series_calls[0]["variables"] == {
        "filter": {"libraryId": {"eq": "L1"}},
        "order": [{"series": {"field": "CREATED_AT", "direction": "DESC"}}],
        "page": 2,
        "size": 20,
    }
    assert media_calls[0]["variables"]["filter"] == {"series": {"libraryId": {"eq": "L1"}}}
    assert media_calls[0]["variables"]["order"] == [
        {"media": {"field": "CREATED_AT", "direction": "DESC"}}
    ]
    assert media_calls[1]["variables"]["filter"] == {"seriesId": {"eq": "s1"}}
    assert media_calls[1]["variables"]["order"] == [
        {"media": {"field": "NAME", "direction": "ASC"}}
    ]
    assert series_calls[1]["variables"]["filter"] == {
        "_or": [{"name": {"contains": "ab"}}, {"metadata": {"title": {"contains": "ab"}}}]
    }
    assert series_calls[1]["variables"]["order"] == [
        {"series": {"field": "NAME", "direction": "ASC"}}
    ]


def test_no_condition_sends_an_empty_filter_object() -> None:
    server, mock = _server()
    server.list_series(1, 10, "", "created_desc")
    server.list_books(1, 10, "", "created_desc")
    assert _ops(mock, "SeriesList")[-1]["variables"]["filter"] == {}
    assert _ops(mock, "MediaList")[-1]["variables"]["filter"] == {}
    assert "$filter: SeriesFilterInput!" in _ops(mock, "SeriesList")[-1]["query"]
    assert "$filter: MediaFilterInput!" in _ops(mock, "MediaList")[-1]["query"]


def test_library_listing_passes_the_strict_mock() -> None:
    server, _ = _server()
    sl = server.list_series(1, 10, "", "created_desc", library_id="L1")
    assert [s.id for s in sl.items] == ["s1"]
    assert server.list_books(1, 10, "", "created_desc", library_id="L1").items
    assert not server.list_books(1, 10, "", "created_desc", library_id="L2").items


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


def test_list_deleted_reads_missing_and_purge_cleans_library() -> None:
    server, mock = _server()
    mock.books.append(stump_mock.book(7, gone=True))
    assert [b.id for b in server.list_deleted("books", "L1") if b.id == "b7"] == ["b7"]
    assert server.list_deleted("series", "L1") == []
    server.purge_deleted("L1")
    assert mock.cleaned == ["L1"]
    assert all(b["status"] != "MISSING" for b in mock.books)


def test_set_tags_writes_and_locks() -> None:
    server, mock = _server()
    server.set_tags("books", "b1", ["b", "a"])
    server.set_tags("series", "s1", ["z"])
    assert _ops(mock, "SetMediaTags")[0]["variables"] == {"id": "b1", "tags": ["b", "a"]}
    assert _ops(mock, "SetSeriesTags")[0]["variables"] == {"id": "s1", "tags": ["z"]}
    assert mock.locks == [
        ("setMediaLockedFields", "b1", ["TAGS"]),
        ("setSeriesLockedFields", "s1", ["TAGS"]),
    ]


def test_set_metadata_maps_fields_and_locks() -> None:
    server, mock = _server()
    patch = MetadataPatch(
        title="T", summary="S", links=[("a", "http://a")], writers=["W"], tags=["t"]
    )
    server.set_metadata("books", "b1", patch)
    sent = _ops(mock, "UpdateMediaMetadata")[0]["variables"]["input"]
    assert sent == {"title": "T", "summary": "S", "links": ["http://a"], "writers": ["W"]}
    assert mock.locks == [
        ("setMediaLockedFields", "b1", ["TITLE", "SUMMARY", "LINKS", "WRITERS", "TAGS"])
    ]
    assert [t["name"] for t in mock.books[0]["tags"]] == ["t"]


def test_set_metadata_series_skips_writers_and_empty_patch_is_refused() -> None:
    server, mock = _server()
    server.set_metadata("series", "s1", MetadataPatch(title="T", writers=["W"]))
    assert _ops(mock, "UpdateSeriesMetadata")[0]["variables"]["input"] == {"title": "T"}
    with pytest.raises(BookServerError) as err:
        server.set_metadata("books", "b1", MetadataPatch())
    assert err.value.code == "bad_request"


def test_progress_update_and_finish() -> None:
    server, mock = _server()
    server.set_progress("b1", 3, False)
    assert _ops(mock, "UpdateMediaProgress")[0]["variables"]["input"] == {"paged": {"page": 3}}
    assert server.get_book("b1").read_page == 3
    server.set_progress("b1", 5, True)
    assert _ops(mock, "FinishMediaProgress")[0]["variables"] == {"id": "b1"}
    assert server.get_book("b1").read_done is True
    with pytest.raises(BookServerError):
        server.set_progress("b1", 0, False)


def test_ids_allow_cuid_chars_only() -> None:
    server, _ = _server()
    assert server.valid_id("cl9x2A_-1") and not server.valid_id("../x") and not server.valid_id("")


def test_dto_mapping() -> None:
    d = stump_mock.book(1)
    d["metadata"].update(writers=["W"], links=["http://a"], title=None)
    d["readProgress"] = {"page": 3}
    d["readHistory"] = [{"completedAt": "2026-01-02T00:00:00Z"}]
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
    st = SimpleNamespace(stump_url=url, stump_api_key=SecretStr(KEY))
    return SimpleNamespace(state=SimpleNamespace(settings=st, stump=None, books=None))


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


LOCKED = "Query Error: error returned from database: (code: 5) database is locked"


def _progress_calls(mock: stump_mock.MockStump) -> int:
    return len(_ops(mock, "UpdateMediaProgress"))


def test_progress_retries_when_database_is_locked_once() -> None:
    server, mock = _server()
    mock.progress_errors = [LOCKED]
    server.set_progress("b1", 3, False)
    assert _progress_calls(mock) == 2
    assert server.get_book("b1").read_page == 3


def test_progress_fails_after_three_locked_tries() -> None:
    server, mock = _server()
    mock.progress_errors = [LOCKED, LOCKED, LOCKED]
    with pytest.raises(BookServerError) as err:
        server.set_progress("b1", 3, False)
    assert err.value.code == "upstream_error"
    assert _progress_calls(mock) == 3


def test_progress_does_not_retry_other_errors() -> None:
    server, mock = _server()
    mock.progress_errors = ["Something else broke"]
    with pytest.raises(BookServerError):
        server.set_progress("b1", 3, False)
    assert _progress_calls(mock) == 1


def test_lock_sends_the_shape_of_stumps_own_client() -> None:
    server, mock = _server()
    server.set_tags("books", "b1", ["a"])
    server.set_tags("series", "s1", ["a"])
    media, series = _ops(mock, "SetMediaLockedFields")[0], _ops(mock, "SetSeriesLockedFields")[0]
    assert media["variables"] == {"mediaId": "b1", "lockedFields": ["TAGS"]}
    assert series["variables"] == {"seriesId": "s1", "lockedFields": ["TAGS"]}
    assert (
        "setMediaLockedFields(mediaId: $mediaId, lockedFields: $lockedFields) { id }"
        in (media["query"])
    )
    assert "$lockedFields: [MetadataField!]!" in series["query"]
    assert "finishMediaProgress(id: $id) }" in stump_mod.M_FINISH_PROGRESS
