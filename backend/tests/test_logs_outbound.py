"""Outbound HTTP hooks: one status line per call, no secrets (design 4.2, 4.3, 5)."""

from __future__ import annotations

import ast
import logging
from pathlib import Path

import httpx
import pytest

from app import logs
from app.komga import Komga
from app.sources.dapi import Rule34
from app.sources.nhentai import NHentai
from app.sources.throttle import Throttle
from app.targets.stash_client import StashClient, StashError

SENTINEL = "SENTINEL-KEY-0123456789abcdef"


class Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.lines: list[str] = []
        self.levels: list[int] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(record.getMessage())
        self.levels.append(record.levelno)


@pytest.fixture
def cap():
    handler = Capture()
    root = logging.getLogger("pearlie")
    old_level = root.level
    root.setLevel(logging.DEBUG)
    root.addHandler(handler)
    yield handler
    root.removeHandler(handler)
    root.setLevel(old_level)


def hooked(handler, site: str, save: bool = False) -> httpx.Client:
    return logs.install_http_hooks(
        httpx.Client(transport=httpx.MockTransport(handler), base_url="http://x.test"),
        site,
        save=save,
    )


def test_status_line_with_query_stripped(cap):
    client = hooked(lambda r: httpx.Response(200, json=[]), "rule34")
    client.get("/index.php", params={"api_key": SENTINEL, "user_id": "42"})
    (line,) = cap.lines
    assert line.startswith("OUT site=rule34 GET x.test/index.php status=200 ms=")
    assert SENTINEL not in line and "api_key" not in line


def test_nhentai_403_logs_status_and_whitelisted_headers(cap):
    def handler(request):
        return httpx.Response(
            403,
            headers={
                "server": "cloudflare",
                "cf-mitigated": "challenge",
                "set-cookie": f"cf={SENTINEL}",
                "content-type": "text/html",
            },
            text="blocked",
        )

    client = hooked(handler, "nhentai")
    client.get("/api/v2/search")
    (line,) = cap.lines
    assert "status=403" in line and "server='cloudflare'" in line
    assert "cf-mitigated='challenge'" in line
    assert "set-cookie" not in line and SENTINEL not in line
    assert "body='blocked'" in line  # DEBUG detail, first 200 chars


def test_retry_after_header_logged(cap):
    client = hooked(lambda r: httpx.Response(429, headers={"retry-after": "30"}), "danbooru")
    client.get("/posts.json")
    assert "status=429" in cap.lines[0] and "retry-after='30'" in cap.lines[0]


def test_connect_error_logs_class_name_only(cap):
    def handler(request):
        raise httpx.ConnectError(f"cannot connect with {SENTINEL}")

    client = hooked(handler, "komga")
    with pytest.raises(httpx.ConnectError):
        client.get("/api/v1/libraries?api_key=" + SENTINEL)
    (line,) = cap.lines
    assert "error=ConnectError" in line
    assert SENTINEL not in line and "cannot connect" not in line
    assert cap.levels == [logging.WARNING]


def test_2xx_is_debug_and_save_calls_are_info(cap):
    hooked(lambda r: httpx.Response(200), "icon").get("/a")
    hooked(lambda r: httpx.Response(200), "download", save=True).get("/a")
    hooked(lambda r: httpx.Response(500), "icon").get("/a")
    assert cap.levels == [logging.DEBUG, logging.INFO, logging.INFO]


def test_stash_line_has_operation_and_graphql_error(cap):
    def handler(request):
        return httpx.Response(200, json={"errors": [{"message": "bad thing"}]})

    client = hooked(handler, "stash")
    client.post("/graphql", json={"query": "mutation ImageUpdate($i: ID!) { x }"})
    client.post("/graphql", json={"query": "query($v: String!) { findImages { id } }"})
    assert "op=ImageUpdate" in cap.lines[0] and "gql_error='bad thing'" in cap.lines[0]
    assert "op=findImages" in cap.lines[1]


def test_stash_streamed_media_body_survives_hooks(cap):
    """The hooks must not consume streamed media (thumb, poster, stream)."""
    body = b"\x89PNG-" + b"x" * 4096

    def handler(request):
        if request.url.path == "/graphql":
            return httpx.Response(200, json={"errors": [{"message": "bad thing"}]})
        if request.url.path == "/scene/9/missing":
            return httpx.Response(500, content=body)
        return httpx.Response(200, content=body, headers={"content-type": "image/png"})

    stash = StashClient("http://x.test", SENTINEL, client=hooked(handler, "stash"))
    for path in ("/scene/9/screenshot", "/scene/9/webp", "/scene/9/stream"):
        resp = stash.open_media(path)
        try:
            assert b"".join(resp.iter_bytes()) == body
        finally:
            resp.close()
    # a failed stream is not read by the hook either
    with pytest.raises(StashError):
        stash.open_media("/scene/9/missing")
    stash._client.post("/graphql", json={"query": "query { findScenes { id } }"})
    gql_lines = [x for x in cap.lines if "/graphql" in x]
    assert "gql_error='bad thing'" in gql_lines[0]
    media_lines = [x for x in cap.lines if "/scene/" in x]
    assert media_lines and all("op=" not in x and "body=" not in x for x in media_lines)


def test_default_clients_are_hooked():
    assert StashClient("http://stash.test", SENTINEL)._client.event_hooks["response"]
    assert Komga("http://komga.test", SENTINEL)._client.event_hooks["response"]
    for src in (Rule34(), NHentai()):
        assert src._client.event_hooks["response"]


def test_sentinel_over_all_hooked_clients(cap):
    """Every kind of real client, secrets in query, header and cookie."""

    def handler(request):
        return httpx.Response(
            401,
            headers={"www-authenticate": f"Bearer {SENTINEL}", "server": "x"},
            json={"errors": [{"message": "no"}]},
        )

    for site in ("danbooru", "gelbooru", "rule34", "nhentai", "stash", "komga", "update", "icon"):
        client = hooked(handler, site)
        client.get(
            f"/p?api_key={SENTINEL}&user_id=1",
            headers={"Authorization": f"Bearer {SENTINEL}", "Cookie": f"s={SENTINEL}"},
        )
    assert len(cap.lines) == 8
    for line in cap.lines:
        assert SENTINEL not in line
        assert "api_key" not in line and "Cookie" not in line


@pytest.mark.skipif(not hasattr(logs, "ScrubFilter"), reason="needs feat-logs-core")
def test_sentinel_in_body_removed_by_scrub_filter(cap):
    logs.register_secret(SENTINEL)
    client = hooked(lambda r: httpx.Response(403, text=f"denied {SENTINEL}"), "nhentai")
    client.get("/x")
    rec = logging.LogRecord("pearlie.out", logging.INFO, "", 0, cap.lines[0], None, None)
    logs.ScrubFilter().filter(rec)
    assert SENTINEL not in rec.getMessage()


def test_throttle_backoff_is_warning_and_wait_is_debug(caplog):
    clock = [0.0]
    t = Throttle(1.0, clock=lambda: clock[0], sleep=lambda s: None, site="nhentai")
    with caplog.at_level(logging.DEBUG, logger="pearlie.throttle"):
        t.wait()
        t.wait()
        t.report(429, 12.0)
    recs = [(r.levelno, r.getMessage()) for r in caplog.records]
    assert (logging.DEBUG, "THROTTLE site=nhentai wait=1.0s") in recs
    warn = [m for lv, m in recs if lv == logging.WARNING]
    assert warn == ["THROTTLE site=nhentai backoff status=429 retry_after=12.0s wait=12.0s"]


def test_no_logger_call_passes_forbidden_objects():
    """Layer 1 (design 5): log calls never take headers, params or settings objects."""
    banned = {"headers", "cookies", "params", "request", "settings"}
    root = Path(__file__).resolve().parents[1] / "app"
    for rel in ("logs.py", "sources/throttle.py", "targets/komga.py"):
        tree = ast.parse((root / rel).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"debug", "info", "warning", "error", "log"}
            ):
                names = {a.id for a in node.args if isinstance(a, ast.Name)}
                assert not names & banned, (rel, node.lineno, names & banned)
