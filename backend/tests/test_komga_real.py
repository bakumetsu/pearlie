"""Tests for the real-mode Komga library endpoints."""

from __future__ import annotations

import inspect
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import ConfigError, Settings
from app.komga import Komga
from app.main import create_app

KEY = "k-secret-123"
URL = "http://komga.test"


def make_client(tmp_path, handler):
    """Build a TestClient with a mock-backed Komga client."""
    app = create_app(
        Settings(
            mode="real",
            real="library_komga,media_komga",
            komga_url=URL,
            db_path=tmp_path / "p.db",
            static_dir=tmp_path / "nostatic",
            _env_file=None,  # pyright: ignore[reportCallIssue]
        )
    )
    app.state.komga = Komga(
        URL,
        KEY,
        client=httpx.Client(base_url=URL, transport=httpx.MockTransport(handler)),
    )
    return TestClient(app)


def book_dto(id: str = "b1", pages: int = 5) -> dict:
    """Return a minimal Komga BookDto."""
    return {
        "id": id,
        "name": "Book",
        "created": "2026-01-01T00:00:00Z",
        "media": {"pagesCount": pages},
        "metadata": {"title": "Book One", "tags": ["x"]},
        "readProgress": None,
    }


def series_dto(id: str = "s1") -> dict:
    """Return a minimal Komga SeriesDto."""
    return {
        "id": id,
        "name": "Series",
        "created": "2026-01-01T00:00:00Z",
        "booksCount": 2,
        "booksReadCount": 1,
        "metadata": {"title": "Series One", "tags": []},
    }


def page_of(content, last: bool = True, total=None) -> dict:
    """Wrap *content* in a Komga page envelope."""
    return {
        "content": content,
        "last": last,
        "totalElements": total if total is not None else len(content),
    }


def test_series_list_page_index(tmp_path):
    """page=1 maps to Komga page 0; always POST /api/v1/series/list."""
    calls: list[tuple] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path, dict(request.url.params)))
        return httpx.Response(200, json=page_of([series_dto()]))

    client = make_client(tmp_path, handler)
    r = client.get("/api/library/komga/series?page=1")
    assert r.status_code == 200
    assert r.json()["page"] == 1
    assert r.json()["items"][0]["id"] == "s1"
    assert calls[0][0] == "POST"
    assert calls[0][1] == "/api/v1/series/list"
    assert calls[0][2]["page"] == "0"

    r = client.get("/api/library/komga/series?page=2")
    assert r.status_code == 200
    assert r.json()["page"] == 2
    assert calls[1][0] == "POST"
    assert calls[1][1] == "/api/v1/series/list"
    assert calls[1][2]["page"] == "1"


def test_series_search_body(tmp_path):
    """q param is sent as fullTextSearch in the POST JSON body."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=page_of([series_dto()]))

    client = make_client(tmp_path, handler)
    client.get("/api/library/komga/series?q=hello")
    assert captured["body"] == {"fullTextSearch": "hello"}


def test_option_ignored_notice(tmp_path):
    """Unsupported sort/favorite params produce an option_ignored notice."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=page_of([series_dto()]))

    client = make_client(tmp_path, handler)
    r = client.get("/api/library/komga/series?sort=rating&favorite=true")
    assert r.status_code == 200
    assert r.json()["notice"]["code"] == "option_ignored"

    r = client.get("/api/library/komga/series")
    assert r.status_code == 200
    assert r.json()["notice"] is None


def test_series_detail_loops_pages(tmp_path):
    """Series detail fetches all book pages via paginated POST /api/v1/books/list."""
    book_list_calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/api/v1/series/s1":
            return httpx.Response(200, json=series_dto())
        if request.method == "POST" and request.url.path == "/api/v1/books/list":
            page = request.url.params["page"]
            book_list_calls.append(page)
            if page == "0":
                return httpx.Response(
                    200,
                    json=page_of([book_dto("b1"), book_dto("b2")], last=False),
                )
            return httpx.Response(200, json=page_of([book_dto("b3")], last=True))
        return httpx.Response(404)

    client = make_client(tmp_path, handler)
    r = client.get("/api/library/series/s1")
    assert r.status_code == 200
    assert [b["id"] for b in r.json()["books"]] == ["b1", "b2", "b3"]
    assert book_list_calls == ["0", "1"]


def test_series_detail_truncated_notice(tmp_path, monkeypatch):
    """When the page cap is hit, a truncated notice is returned."""
    monkeypatch.setattr("app.komga.SERIES_BOOKS_PAGES", 2)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/api/v1/series/s1":
            return httpx.Response(200, json=series_dto())
        if request.method == "POST" and request.url.path == "/api/v1/books/list":
            return httpx.Response(200, json=page_of([book_dto("b1")], last=False))
        return httpx.Response(404)

    client = make_client(tmp_path, handler)
    r = client.get("/api/library/series/s1")
    assert r.status_code == 200
    assert r.json()["notice"]["code"] == "truncated"
    assert len(r.json()["books"]) == 2


def test_series_detail_no_notice_when_complete(tmp_path):
    """When all pages fit within the cap, no notice is returned."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/api/v1/series/s1":
            return httpx.Response(200, json=series_dto())
        if request.method == "POST" and request.url.path == "/api/v1/books/list":
            return httpx.Response(200, json=page_of([book_dto("b1")], last=True))
        return httpx.Response(404)

    client = make_client(tmp_path, handler)
    r = client.get("/api/library/series/s1")
    assert r.status_code == 200
    assert r.json()["notice"] is None


def test_book_detail_page_url(tmp_path):
    """Book detail exposes page_count, page_url, and page_thumb_url templates."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/api/v1/books/b1":
            return httpx.Response(200, json=book_dto(pages=7))
        return httpx.Response(404)

    client = make_client(tmp_path, handler)
    r = client.get("/api/library/books/b1")
    assert r.status_code == 200
    assert r.json()["page_count"] == 7
    assert r.json()["page_url"] == "/api/media/komga/books/b1/pages/{n}"
    assert r.json()["page_thumb_url"] == "/api/media/komga/books/b1/pages/{n}/thumb"


def test_progress_completed_flag(tmp_path):
    """Progress POST marks completed when page equals page_count."""
    recorded: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/api/v1/books/b1":
            return httpx.Response(200, json=book_dto(pages=5))
        if request.method == "PATCH" and request.url.path == "/api/v1/books/b1/read-progress":
            recorded.append(json.loads(request.content))
            return httpx.Response(204)
        return httpx.Response(404)

    client = make_client(tmp_path, handler)
    r = client.post("/api/library/komga/books/b1/progress", json={"page": 1})
    assert r.status_code == 200
    assert r.json() == {"page": 1, "completed": False}
    assert recorded[-1] == {"page": 1, "completed": False}

    r = client.post("/api/library/komga/books/b1/progress", json={"page": 5})
    assert r.json()["completed"] is True
    assert recorded[-1]["completed"] is True


def test_progress_out_of_range(tmp_path):
    """Progress page out of range returns 422 without calling Komga."""
    recorded: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/api/v1/books/b1":
            return httpx.Response(200, json=book_dto(pages=5))
        if request.method == "PATCH" and request.url.path == "/api/v1/books/b1/read-progress":
            recorded.append(json.loads(request.content))
            return httpx.Response(204)
        return httpx.Response(404)

    client = make_client(tmp_path, handler)
    r = client.post("/api/library/komga/books/b1/progress", json={"page": 6})
    assert r.status_code == 422
    r = client.post("/api/library/komga/books/b1/progress", json={"page": 0})
    assert r.status_code == 422
    assert len(recorded) == 0


def test_patch_delete_not_supported(tmp_path):
    """PATCH/DELETE on library endpoints return 501 not_supported."""
    called: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        called.append(request.url.path)
        return httpx.Response(500)

    client = make_client(tmp_path, handler)
    r = client.patch("/api/library/books/b1", json={})
    assert r.status_code == 501
    assert r.json()["code"] == "not_supported"
    r = client.delete("/api/library/books/b1")
    assert r.status_code == 501
    assert r.json()["code"] == "not_supported"
    r = client.delete("/api/library/series/s1")
    assert r.status_code == 501
    assert r.json()["code"] == "not_supported"


def test_page_stream_large_body(tmp_path):
    """Large image body is streamed intact with correct headers and upstream path."""
    body = bytes(range(256)) * 1172 + b"x"
    recorded: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        recorded.append(str(request.url))
        return httpx.Response(
            200,
            content=body,
            headers={"content-type": "image/jpeg"},
        )

    client = make_client(tmp_path, handler)
    r = client.get("/api/media/komga/books/b1/pages/3")
    assert r.status_code == 200
    assert r.content == body
    assert r.headers["content-type"] == "image/jpeg"
    assert r.headers["content-length"] == str(len(body))
    assert len(body) > 65536
    u = httpx.URL(recorded[0])
    assert u.path == "/api/v1/books/b1/pages/3"
    assert u.params["zero_based"] == "false"


def test_page_thumb_relay(tmp_path):
    """Page thumbnail relay returns JPEG with cache headers and correct upstream path."""
    body = b"\xff\xd8\xff\xe0fakejpegdata"
    recorded: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        recorded.append(str(request.url))
        return httpx.Response(
            200,
            content=body,
            headers={"content-type": "image/jpeg"},
        )

    client = make_client(tmp_path, handler)
    r = client.get("/api/media/komga/books/b1/pages/3/thumb")
    assert r.status_code == 200
    assert r.content == body
    assert r.headers["content-type"] == "image/jpeg"
    assert r.headers["cache-control"] == "private, max-age=86400"
    u = httpx.URL(recorded[0])
    assert u.path == "/api/v1/books/b1/pages/3/thumbnail"
    assert u.params["zero_based"] == "false"


def test_page_zero_is_404(tmp_path):
    """Page number 0 is rejected with 404 before reaching Komga."""
    called: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        called.append(str(request.url))
        return httpx.Response(500)

    client = make_client(tmp_path, handler)
    r = client.get("/api/media/komga/books/b1/pages/0")
    assert r.status_code == 404
    assert called == []


def test_page_thumb_zero_is_404(tmp_path):
    """Page number 0 on the thumbnail route is rejected with 404 before reaching Komga."""
    called: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        called.append(str(request.url))
        return httpx.Response(500)

    client = make_client(tmp_path, handler)
    r = client.get("/api/media/komga/books/b1/pages/0/thumb")
    assert r.status_code == 404
    assert called == []


def test_page_thumb_upstream_404(tmp_path):
    """Upstream 404 on the page thumbnail route passes through as 404."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    client = make_client(tmp_path, handler)
    r = client.get("/api/media/komga/books/b1/pages/3/thumb")
    assert r.status_code == 404
    assert KEY not in r.text


def test_upstream_errors(tmp_path):
    """Upstream 404 passes through; 500 and connection errors become 502 without leaking KEY."""

    def make_handler(status: int = 500, exc: Exception | None = None):
        def handler(request: httpx.Request) -> httpx.Response:
            if exc is not None:
                raise exc
            return httpx.Response(status)

        return handler

    # a) upstream 404 passes through
    client = make_client(tmp_path, make_handler(status=404))
    r = client.get("/api/library/books/b1")
    assert r.status_code == 404
    assert KEY not in r.text
    r = client.get("/api/media/komga/books/b1/thumb")
    assert r.status_code == 404
    assert KEY not in r.text

    # b) upstream 500 becomes 502
    client = make_client(tmp_path, make_handler(status=500))
    r = client.get("/api/library/books/b1")
    assert r.status_code == 502
    assert KEY not in r.text
    r = client.get("/api/media/komga/books/b1/thumb")
    assert r.status_code == 502
    assert KEY not in r.text

    # c) ConnectError becomes 502
    client = make_client(tmp_path, make_handler(exc=httpx.ConnectError("boom")))
    r = client.get("/api/library/books/b1")
    assert r.status_code == 502
    assert KEY not in r.text
    r = client.get("/api/media/komga/books/b1/thumb")
    assert r.status_code == 502
    assert KEY not in r.text


def test_missing_komga_url_is_config_error(tmp_path):
    """Empty komga_url raises ConfigError at app creation."""
    with pytest.raises(ConfigError):
        create_app(
            Settings(
                mode="real",
                real="library_komga",
                komga_url="",
                db_path=tmp_path / "p.db",
                static_dir=tmp_path / "nostatic",
                _env_file=None,  # pyright: ignore[reportCallIssue]
            )
        )


def test_komga_routes_are_sync():
    """Sync routes run in the threadpool; async ones would block on the sync httpx client."""
    from app.api import library_komga_real, media_komga_real

    for router in (library_komga_real.router, media_komga_real.router):
        for route in router.routes:
            endpoint = getattr(route, "endpoint", None)
            if endpoint is not None:
                assert not inspect.iscoroutinefunction(endpoint)
