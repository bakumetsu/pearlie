from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from app.db import init_db
from app.update.changelog import Changelog, build_block, parse_subject
from app.update.repo import API_BASE, TAGS_URL

SHA_A = "a" * 40
SHA_B = "b" * 40


def _c(msg: str, parents: int = 1) -> dict[str, Any]:
    return {"commit": {"message": msg}, "parents": [{}] * parents}


def _tags(*names: str) -> list[dict[str, Any]]:
    return [{"name": n, "commit": {"sha": "0" * 40}} for n in names]


def _mk(
    tmp_path: Path, routes: dict[str, Any], seen: list[str] | None = None
) -> Changelog:
    db = tmp_path / "p.db"
    init_db(db)

    def h(req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        if seen is not None:
            seen.append(url)
        assert url.startswith("https://api.github.com/"), url
        if url not in routes:
            return httpx.Response(404)
        body = routes[url]
        if isinstance(body, httpx.Response):
            return body
        return httpx.Response(200, json=body)

    return Changelog(httpx.Client(transport=httpx.MockTransport(h)), db, "t")


def _cmp(base: str, head: str) -> str:
    return f"{API_BASE}/compare/{base}...{head}"


# oldest first, as the compare API returns them
_REL = {
    TAGS_URL: _tags("v0.3.0", "v0.4.0", "v0.5.0", "junk"),
    _cmp("v0.4.0", "v0.5.0"): {
        "commits": [_c("fix(a): stop crash"), _c("feat(b): add thing"), _c("docs: words")]
    },
    _cmp("v0.3.0", "v0.4.0"): {"commits": [_c("perf: faster")]},
    f"{API_BASE}/commits?sha=v0.3.0&per_page=100": [_c("feat: first")],
}


def _get(cl: Changelog, channel: str = "main", **kw: Any) -> dict[str, Any]:
    args: dict[str, Any] = {
        "installed_version": "0.4.0",
        "installed_commit": None,
        "installed_known": True,
        "latest_ref": "0.5.0",
        "enabled": True,
        "force": False,
    }
    args.update(kw)
    return cl.get(channel, **args)


def test_parse_subject_maps_and_strips_scope() -> None:
    assert parse_subject("feat(search): add x") == ("Added", "Add x")
    assert parse_subject("fix: bug\n\nbody") == ("Fixed", "Bug")
    assert parse_subject("refactor(a)!: tidy") == ("Reworked", "Tidy")
    assert parse_subject("perf: quick") == ("Reworked", "Quick")


def test_parse_subject_hides_other_types() -> None:
    for s in ("docs: a", "test: a", "chore: a", "kit: a", "Merge branch 'x'", "feat add"):
        assert parse_subject(s) is None


def test_build_block_groups_and_skips_merges() -> None:
    commits = [
        _c("fix: b"),
        _c("feat: a"),
        _c("feat: merged", parents=2),
        _c("chore: no"),
        _c("refactor: c"),
    ]
    b = build_block("T", commits, None)
    assert [(g["kind"], g["items"]) for g in b["groups"]] == [
        ("Added", ["A"]),
        ("Fixed", ["B"]),
        ("Reworked", ["C"]),
    ]
    assert b["total"] == 3 and b["more"] == 0


def test_build_block_caps_at_50_with_more_link() -> None:
    b = build_block("T", [_c(f"feat: item {i}") for i in range(60)], "https://x/c")
    assert sum(len(g["items"]) for g in b["groups"]) == 50
    assert b["more"] == 10 and b["more_url"] == "https://x/c"


def test_main_one_entry_per_tag_newest_first(tmp_path: Path) -> None:
    out = _get(_mk(tmp_path, _REL))
    titles = [b["title"] for b in out["history"]]
    assert titles == ["v0.5.0", "v0.4.0", "v0.3.0"]
    v5 = out["history"][0]
    assert [g["kind"] for g in v5["groups"]] == ["Added", "Fixed"]
    assert out["history"][1]["groups"][0]["kind"] == "Reworked"
    assert out["history"][2]["groups"][0]["items"] == ["First"]
    assert out["unavailable"] is False


def test_main_whats_new_covers_installed_to_latest(tmp_path: Path) -> None:
    out = _get(_mk(tmp_path, _REL), installed_version="0.3.0")
    wn = out["whats_new"]
    assert wn["range"] == "0.3.0 → 0.5.0"
    kinds = {g["kind"]: g["items"] for g in wn["groups"]}
    assert kinds == {"Added": ["Add thing"], "Fixed": ["Stop crash"], "Reworked": ["Faster"]}


def test_main_up_to_date_has_no_whats_new(tmp_path: Path) -> None:
    out = _get(_mk(tmp_path, _REL), installed_version="0.5.0")
    assert out["whats_new"] is None
    assert len(out["history"]) == 3


def test_unknown_build_gets_history_only(tmp_path: Path) -> None:
    out = _get(_mk(tmp_path, _REL), installed_version="0.1.0-dev", installed_known=False)
    assert out["whats_new"] is None
    assert out["history"]


_DEV = {
    **_REL,
    _cmp("v0.5.0", "dev"): {"commits": [_c("feat: older"), _c("fix: newer")]},
    _cmp(SHA_A, SHA_B): {"commits": [_c("feat: x")]},
}


def test_dev_flat_list_since_last_tag_then_releases(tmp_path: Path) -> None:
    out = _get(_mk(tmp_path, _DEV), "dev", latest_ref=SHA_B, installed_commit=SHA_A)
    assert [b["title"] for b in out["history"]] == ["Since v0.5.0", "v0.5.0", "v0.4.0", "v0.3.0"]
    assert [g["kind"] for g in out["history"][0]["groups"]] == ["Added", "Fixed"]
    wn = out["whats_new"]
    assert wn["range"] == f"{SHA_A[:7]} → {SHA_B[:7]}"
    assert wn["groups"][0]["items"] == ["X"]


def test_dev_without_installed_commit_has_no_whats_new(tmp_path: Path) -> None:
    out = _get(_mk(tmp_path, _DEV), "dev", latest_ref=SHA_B, installed_commit=None)
    assert out["whats_new"] is None
    assert out["history"][0]["title"] == "Since v0.5.0"


def test_cache_serves_second_call_without_fetch(tmp_path: Path) -> None:
    seen: list[str] = []
    cl = _mk(tmp_path, _REL, seen)
    _get(cl)
    n = len(seen)
    assert n > 0
    _get(cl)
    assert len(seen) == n


def test_cache_survives_restart_via_db(tmp_path: Path) -> None:
    seen: list[str] = []
    _get(_mk(tmp_path, _REL, seen))
    n = len(seen)
    out = _get(_mk(tmp_path, _REL, seen))
    assert len(seen) == n
    assert len(out["history"]) == 3


def test_check_now_refetches(tmp_path: Path) -> None:
    seen: list[str] = []
    cl = _mk(tmp_path, _REL, seen)
    _get(cl)
    n = len(seen)
    _get(cl, force=True)
    assert len(seen) > n


def test_new_latest_refetches_when_checks_on(tmp_path: Path) -> None:
    seen: list[str] = []
    cl = _mk(tmp_path, _REL, seen)
    _get(cl, latest_ref="0.4.0")
    n = len(seen)
    _get(cl, latest_ref="0.5.0")
    assert len(seen) > n


def test_check_off_makes_no_fetch(tmp_path: Path) -> None:
    seen: list[str] = []
    out = _get(_mk(tmp_path, _REL, seen), enabled=False)
    assert seen == []
    assert out["unavailable"] is True and out["history"] == []


def test_check_off_still_shows_cache_and_check_now_fetches(tmp_path: Path) -> None:
    seen: list[str] = []
    cl = _mk(tmp_path, _REL, seen)
    _get(cl)
    n = len(seen)
    out = _get(cl, enabled=False, latest_ref="0.6.0")
    assert len(seen) == n and len(out["history"]) == 3
    _get(cl, enabled=False, force=True)
    assert len(seen) > n


def test_github_down_serves_cached_copy(tmp_path: Path) -> None:
    cl = _mk(tmp_path, _REL)
    _get(cl)
    cl._client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    out = _get(cl, force=True)
    assert out["stale"] is True
    assert len(out["history"]) == 3


def test_github_down_without_cache_is_unavailable(tmp_path: Path) -> None:
    def boom(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("x")

    db = tmp_path / "p.db"
    init_db(db)
    cl = Changelog(httpx.Client(transport=httpx.MockTransport(boom)), db, "t")
    out = _get(cl)
    assert out["unavailable"] is True and out["history"] == []


def test_api_check_off_no_fetch(client: Any) -> None:
    from typing import cast

    from fastapi import FastAPI

    app = cast(FastAPI, client.app)
    calls: list[dict[str, Any]] = []

    class _Spy:
        def get(self, channel: str, **kw: Any) -> dict[str, Any]:
            calls.append(kw)
            return {
                "channel": channel,
                "unavailable": True,
                "stale": False,
                "whats_new": None,
                "history": [],
            }

    app.state.update_changelog = _Spy()
    assert client.put("/api/update/settings", json={"check_enabled": False}).status_code == 200
    r = client.get("/api/update/changelog")
    assert r.status_code == 200 and r.json()["unavailable"] is True
    assert calls[-1]["enabled"] is False and calls[-1]["force"] is False
    client.get("/api/update/changelog?refresh=1&channel=dev")
    assert calls[-1]["force"] is True

