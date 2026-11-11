"""Tests for Throttle pace / back-off / ease-in."""
from __future__ import annotations

import httpx
import pytest

from app.sources.base import SourceError
from app.sources.danbooru import Danbooru
from app.sources.throttle import EASE_AFTER, MAX_WAIT, Throttle


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, dt: float) -> None:
        self.now += dt


class FakeSleep:
    def __init__(self, clock: FakeClock) -> None:
        self._clock = clock
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
        self._clock.advance(seconds)


def make_throttle(min_interval: float = 1.0) -> tuple[Throttle, FakeClock, FakeSleep]:
    clock = FakeClock()
    sleep = FakeSleep(clock)
    t = Throttle(min_interval, clock=clock, sleep=sleep)
    return t, clock, sleep


# -- back-off (429/503) -----------------------------------------------------

def test_429_doubles():
    t, _, _ = make_throttle(1.0)
    assert not t.backing_off
    t.report(429)
    assert t._current == 2.0
    assert t.backing_off
    t.report(429)
    assert t._current == 4.0


def test_caps_at_max_wait():
    t, _, _ = make_throttle(1.0)
    t._current = 200.0
    t.report(429)
    assert t._current == MAX_WAIT  # 400 -> 300


def test_retry_after_used_as_given():
    t, _, _ = make_throttle(1.0)
    t.report(429, retry_after=7.0)
    assert t._current == 7.0


def test_retry_after_capped():
    t, _, _ = make_throttle(1.0)
    t.report(503, retry_after=9999.0)
    assert t._current == MAX_WAIT


def test_retry_below_user_keeps_user():
    t, _, _ = make_throttle(2.0)
    t.report(429, retry_after=1.0)
    assert t._current == 2.0


# -- ease-in (clean reports) -------------------------------------------------

def test_clean_reports_halt_once():
    t, _, _ = make_throttle(1.0)
    t._current = 8.0
    for _ in range(EASE_AFTER - 1):
        t.report(200)
    assert t._current == 8.0
    t.report(200)
    assert t._current == 4.0


def test_never_below_user():
    t, _, _ = make_throttle(2.0)
    t._current = 3.0
    for _ in range(EASE_AFTER):
        t.report(200)
    assert t._current == 2.0  # max(2.0, 1.5)


def test_backing_off_flag():
    t, _, _ = make_throttle(1.0)
    assert not t.backing_off
    t.report(429)
    assert t.backing_off
    t._current = 2.0
    for _ in range(EASE_AFTER):
        t.report(200)
    assert t._current == 1.0
    assert not t.backing_off


# -- set_interval ------------------------------------------------------------

def test_set_interval_while_backing_off_keeps_higher():
    t, _, _ = make_throttle(1.0)
    t.report(429)
    assert t._current == 2.0
    t.set_interval(1.5)
    assert t.interval == 1.5
    assert t._current == 2.0
    assert t.backing_off


def test_set_interval_while_backing_off_raises_user():
    t, _, _ = make_throttle(1.0)
    t.report(429)
    assert t._current == 2.0
    t.set_interval(3.0)
    assert t.interval == 3.0
    assert t._current == 3.0
    assert not t.backing_off


def test_set_interval_not_backing_off():
    t, _, _ = make_throttle(1.0)
    t.set_interval(5.0)
    assert t.interval == 5.0
    assert t._current == 5.0


# -- Danbooru._get integration (MockTransport, no real I/O) ------------------

def test_danbooru_429_with_retry_after():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "5"}, json={})

    t, _, _ = make_throttle(1.0)
    d = Danbooru(throttle=t)
    d._client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(SourceError):
        d._get("/posts.json")

    assert t._current == 5.0
    assert t.backing_off


def test_danbooru_503_no_retry_after():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={})

    t, _, _ = make_throttle(1.0)
    d = Danbooru(throttle=t)
    d._client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(SourceError):
        d._get("/posts.json")

    assert t._current == 2.0
    assert t.backing_off


def test_danbooru_200_eases():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"posts": []})

    t, _, _ = make_throttle(1.0)
    d = Danbooru(throttle=t)
    d._client = httpx.Client(transport=httpx.MockTransport(handler))

    d._get("/posts.json")
    assert not t.backing_off
