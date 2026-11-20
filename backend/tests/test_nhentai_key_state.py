"""nhentai key state, /user check, guest fallback, path buckets and RateLimit headers (mocked)."""

from __future__ import annotations

import logging

import httpx
import pytest

from app.sources.base import SourceError
from app.sources.nhentai import NHentai, bucket_of
from app.sources.throttle import Throttle

KEY = "sekret-key-123"
OK = {"result": [], "num_pages": 1, "per_page": 25}


class Site:
    """A fake nhentai: `/user` and the API answer from `user` and `api` status codes."""

    def __init__(self, user: int = 200, api: int = 200, headers: dict[str, str] | None = None):
        self.user, self.api, self.headers = user, api, headers or {}
        self.calls: list[httpx.Request] = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.calls.append(req)
        authed = req.headers.get("authorization") == f"Key {KEY}"
        if req.url.path == "/api/v2/user":
            return httpx.Response(self.user, json={"email": "a@b.c"})
        if self.api in (401, 403) and authed:
            return httpx.Response(self.api, json={})
        code = 200 if self.api in (401, 403) else self.api
        return httpx.Response(code, json=OK, headers=self.headers)

    def paths(self) -> list[str]:
        return [r.url.path for r in self.calls]


def _src(
    site: Site,
    key: str = KEY,
    now: list[float] | None = None,
    paced: bool = False,
) -> NHentai:
    clock = now if now is not None else [0.0]
    thr = Throttle(0.0, clock=lambda: clock[0], sleep=lambda d: None, site="nhentai")
    src = NHentai(
        client=httpx.Client(transport=httpx.MockTransport(site)),
        throttle=thr,
        credentials=lambda: {"api_key": key} if key else {},
        paced=paced,
    )
    src._spawn = lambda fn: None  # no background thread: tests call check_key themselves
    return src


def test_bucket_of_matches_exact_segments() -> None:
    assert bucket_of("/api/v2/search") == "search"
    assert bucket_of("/api/v2/search/foo") == "search"
    assert bucket_of("/api/v2/galleries") == "list"
    assert bucket_of("/api/v2/galleries/123") == "detail"
    assert bucket_of("/api/v2/galleries/123/related") == "related"
    assert bucket_of("/api/v2/user") == "user"
    assert bucket_of("/api/v2/galleries/12x") == "other"
    assert bucket_of("/api/v2/searching") == "other"
    assert bucket_of("/api/v2/galleries/1/related/x") == "other"


def test_state_unset_unchecked_ok() -> None:
    assert _src(Site(), key="").key_state == ("unset", "")
    src = _src(Site())
    assert src.key_state == ("unchecked", "")
    assert src.check_key() == ("ok", "")


def test_user_401_marks_invalid_and_search_runs_as_guest() -> None:
    site = Site(user=401)
    src = _src(site)
    assert src.check_key() == ("failed", "invalid")
    src.search(["a"])
    assert "authorization" not in site.calls[-1].headers


def test_search_401_with_key_retries_once_as_guest() -> None:
    site = Site(api=401)
    src = _src(site)
    src.search(["a"])
    api_calls = [r for r in site.calls if r.url.path == "/api/v2/search"]
    assert len(api_calls) == 2
    assert "authorization" in api_calls[0].headers
    assert "authorization" not in api_calls[1].headers
    assert src.key_state == ("failed", "invalid")


def test_403_with_good_key_is_a_site_block_not_retried() -> None:
    site = Site(user=200, api=403)
    src = _src(site)
    with pytest.raises(SourceError) as e:
        src.search(["a"])
    assert e.value.status == 403
    assert site.paths().count("/api/v2/search") == 1
    assert src.key_state == ("ok", "")


def test_403_with_failing_user_check_drops_key_and_retries_as_guest() -> None:
    site = Site(user=403, api=403)
    src = _src(site)
    src.search(["a"])
    assert src.key_state == ("failed", "blocked")
    assert "authorization" not in site.calls[-1].headers


def test_403_with_user_401_is_invalid() -> None:
    site = Site(user=401, api=403)
    src = _src(site)
    src.search(["a"])
    assert src.key_state == ("failed", "invalid")


def test_429_and_503_never_fail_the_key() -> None:
    for code in (429, 503):
        src = _src(Site(api=code))
        with pytest.raises(SourceError):
            src.search(["a"])
        assert src.key_state[0] == "unchecked"


def test_network_error_on_check_leaves_state() -> None:
    def boom(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    src = NHentai(
        client=httpx.Client(transport=httpx.MockTransport(boom)),
        throttle=Throttle(0.0),
        credentials=lambda: {"api_key": KEY},
    )
    assert src.check_key() == ("unchecked", "")


def test_new_key_resets_state() -> None:
    keys = [KEY]
    site = Site(user=401)
    src = NHentai(
        client=httpx.Client(transport=httpx.MockTransport(site)),
        throttle=Throttle(0.0),
        credentials=lambda: {"api_key": keys[0]},
    )
    assert src.check_key() == ("failed", "invalid")
    keys[0] = "other"
    assert src.key_state == ("unchecked", "")
    keys[0] = ""
    assert src.key_state == ("unset", "")


def test_periodic_check_runs_once_per_ten_minutes(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.sources import nhentai as mod

    t = [1000.0]
    monkeypatch.setattr(mod.time, "monotonic", lambda: t[0])
    src = _src(Site())
    runs: list[int] = []
    src._spawn = lambda fn: runs.append(1)
    src.search(["a"])
    src.search(["a"])
    assert len(runs) == 1  # first call only
    t[0] += 601
    src.search(["a"])
    assert len(runs) == 2


def test_blocked_key_is_retried_after_ten_minutes(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.sources import nhentai as mod

    t = [1000.0]
    monkeypatch.setattr(mod.time, "monotonic", lambda: t[0])
    src = _src(Site(user=403))
    src.check_key()
    assert src.key_state == ("failed", "blocked")
    runs: list[int] = []
    src._spawn = lambda fn: runs.append(1)
    src._maybe_check()
    assert runs == [] and src.key_state[0] == "failed"
    t[0] += 601
    src._maybe_check()
    assert runs == [1] and src.key_state[0] == "unchecked"


def test_invalid_key_is_not_rechecked_by_the_timer(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.sources import nhentai as mod

    t = [1000.0]
    monkeypatch.setattr(mod.time, "monotonic", lambda: t[0])
    src = _src(Site(user=401))
    src.check_key()
    runs: list[int] = []
    src._spawn = lambda fn: runs.append(1)
    t[0] += 5000
    src._maybe_check()
    assert runs == []


def test_pace_floor_guest_and_key() -> None:
    for key, search, detail in (("", 6.5, 3.2), (KEY, 3.2, 1.5)):
        slept: list[float] = []
        clock = [0.0]
        thr = Throttle(0.0, clock=lambda c=clock: c[0], sleep=slept.append)
        src = NHentai(
            client=httpx.Client(transport=httpx.MockTransport(Site())),
            throttle=thr,
            credentials=lambda key=key: {"api_key": key} if key else {},
        )
        src._spawn = lambda fn: None
        src._get("/api/v2/search")
        src._get("/api/v2/search")
        src._get("/api/v2/galleries/5")  # own bucket: no wait
        src._get("/api/v2/galleries/6")
        assert slept == [pytest.approx(search), pytest.approx(detail)]


def test_setting_cannot_go_below_floor_but_can_raise_it() -> None:
    slept: list[float] = []
    clock = [0.0]
    thr = Throttle(10.0, clock=lambda: clock[0], sleep=slept.append)
    src = NHentai(
        client=httpx.Client(transport=httpx.MockTransport(Site())),
        throttle=thr,
        credentials=lambda: {},
    )
    src._get("/api/v2/search")
    src._get("/api/v2/search")
    assert slept == [pytest.approx(10.0)]  # setting 10 s beats the 6.5 s floor
    slept.clear()
    low = Throttle(1.0, clock=lambda: clock[0], sleep=slept.append)
    src2 = NHentai(
        client=httpx.Client(transport=httpx.MockTransport(Site())),
        throttle=low,
        credentials=lambda: {},
    )
    src2._get("/api/v2/search")
    src2._get("/api/v2/search")
    assert slept == [pytest.approx(6.5)]  # setting 1 s cannot go under the floor


def test_user_check_takes_no_bucket_slot() -> None:
    slept: list[float] = []
    thr = Throttle(0.0, sleep=slept.append)
    src = NHentai(
        client=httpx.Client(transport=httpx.MockTransport(Site())),
        throttle=thr,
        credentials=lambda: {"api_key": KEY},
    )
    src.check_key()
    src.check_key()
    assert slept == []


def test_backoff_doubles_from_floor_and_never_eases_below_it() -> None:
    clock = [0.0]
    thr = Throttle(0.0, clock=lambda: clock[0], sleep=lambda d: None)
    thr.report(429, None, floor=6.5)
    assert thr.reserve(6.5, "search") == pytest.approx(13.0)
    clock[0] = 100.0
    for _ in range(40):
        thr.report(200, None, 6.5)
    clock[0] = 1000.0
    thr.reserve(6.5, "search")
    clock[0] = 1000.0
    assert thr.reserve(6.5, "search") == pytest.approx(6.5)


def test_ratelimit_remaining_zero_waits_for_next_window() -> None:
    slept: list[float] = []
    clock = [0.0]
    thr = Throttle(0.0, clock=lambda: clock[0], sleep=slept.append)
    site = Site(headers={"X-RateLimit-Remaining": "0", "Retry-After": "42"})
    src = NHentai(
        client=httpx.Client(transport=httpx.MockTransport(site)),
        throttle=thr,
        credentials=lambda: {},
        paced=False,
    )
    src._get("/api/v2/search")
    src._get("/api/v2/search")
    assert slept == [pytest.approx(42.0)]


def test_ratelimit_remaining_zero_without_retry_after_uses_a_minute() -> None:
    clock = [0.0]
    thr = Throttle(0.0, clock=lambda: clock[0], sleep=lambda d: None)
    site = Site(headers={"X-RateLimit-Remaining": "0"})
    src = NHentai(
        client=httpx.Client(transport=httpx.MockTransport(site)),
        throttle=thr,
        credentials=lambda: {},
        paced=False,
    )
    src._get("/api/v2/search")
    assert thr.reserve_within(8.0, 0.0, "search") is None


def test_key_never_in_logs(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    for site in (Site(user=401), Site(api=401), Site(user=403, api=403), Site(api=429)):
        src = _src(site)
        src.check_key()
        try:
            src.search(["a"])
        except SourceError:
            pass
    assert KEY not in caplog.text
    assert "a@b.c" not in caplog.text
