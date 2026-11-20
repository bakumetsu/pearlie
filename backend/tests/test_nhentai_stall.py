"""nhentai search never stalls: bounded slot wait, timeouts, recovery (mocked, no network)."""

from __future__ import annotations

import httpx
import pytest

from app.sources.base import SourceError
from app.sources.nhentai import NHentai
from app.sources.throttle import Throttle

OK = {"result": [], "num_pages": 1, "per_page": 25}
GALLERY = {
    "id": 123,
    "media_id": "9123",
    "title": {"english": "Eng", "pretty": "Pretty"},
    "cover": {"path": "galleries/9123/cover.jpg", "width": 350, "height": 500},
    "thumbnail": {"path": "galleries/9123/thumb.jpg", "width": 250, "height": 350},
    "pages": [{"number": 1, "path": "galleries/9123/1.jpg", "width": 1, "height": 1}],
    "tags": [],
    "num_pages": 1,
    "upload_date": 1700000000,
}


def _src(handler, thr: Throttle) -> NHentai:
    return NHentai(
        client=httpx.Client(transport=httpx.MockTransport(handler)), throttle=thr, paced=False
    )


def test_429_retry_after_fails_fast_and_takes_no_slot() -> None:
    """After a 429 with Retry-After 60, searches fail at once instead of queueing for minutes."""
    calls: list[int] = []
    slept: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(429, headers={"Retry-After": "60"}, json={"error": "x"})

    now = [0.0]
    thr = Throttle(2.0, clock=lambda: now[0], sleep=slept.append, site="nhentai")
    src = _src(handler, thr)
    for _ in range(6):
        with pytest.raises(SourceError) as e:
            src.search(["a"])
        assert e.value.code == "rate_limited"
    assert len(calls) == 1  # the burst never reached the site
    assert slept == []  # nobody slept for the pause


def test_hung_connection_times_out_and_next_call_works() -> None:
    answers = iter([httpx.ReadTimeout("hung"), None])

    def handler(request: httpx.Request) -> httpx.Response:
        a = next(answers)
        if a is not None:
            raise a
        return httpx.Response(200, json=OK)

    src = _src(handler, Throttle(0.0))
    with pytest.raises(SourceError) as e:
        src.search(["a"])
    assert e.value.code == "upstream_error"
    assert src.search(["a"]).posts == []  # the failed call left no stuck state


def test_recovers_after_pause() -> None:
    n = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        n[0] += 1
        if n[0] == 1:
            return httpx.Response(429, headers={"Retry-After": "10"}, json={})
        return httpx.Response(200, json=OK)

    now = [0.0]

    def sleep(d: float) -> None:
        now[0] += d

    src = _src(handler, Throttle(2.0, clock=lambda: now[0], sleep=sleep))
    with pytest.raises(SourceError):
        src.search(["a"])
    with pytest.raises(SourceError):  # 10 s pause is above the 8 s limit
        src.search(["a"])
    now[0] += 5.0  # 5 s left: the call waits, then answers
    assert src.search(["a"]).posts == []
    assert n[0] == 2


def test_save_job_get_post_waits_during_pause() -> None:
    """get_post (save jobs) waits for its slot during a 429 pause; it does not fail."""
    n = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        n[0] += 1
        if n[0] == 1:
            return httpx.Response(429, headers={"Retry-After": "60"}, json={})
        return httpx.Response(200, json=GALLERY)

    now = [0.0]
    slept: list[float] = []

    def sleep(d: float) -> None:
        slept.append(d)
        now[0] += d

    src = _src(handler, Throttle(2.0, clock=lambda: now[0], sleep=sleep))
    with pytest.raises(SourceError):
        src.search(["a"])
    post = src.get_post("123")  # pause is 60 s: waits it out instead of raising
    assert post.post_id == "123"
    assert sum(slept) >= 59
