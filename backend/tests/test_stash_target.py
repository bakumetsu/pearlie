from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.db import connect, init_db
from app.sources.base import Post, SearchPage, Source
from app.targets import stash
from app.targets.stash import StashTarget
from app.targets.stash_client import StashClient
from app.sources.throttle import Throttle

MD5 = hashlib.md5(b"pngbytes").hexdigest()
URL = "http://img.example/a/file.png"
SECRET = "secret"


class FakeSource:
    id: str = "fake"
    target: str = "stash"
    file_hosts: tuple[str, ...] = ("img.example",)

    def search(self, tags: list[str], page: int = 1, page_size: int | None = None) -> SearchPage:
        raise NotImplementedError

    def get_post(self, post_id: str) -> Post:
        raise NotImplementedError


def make_graphql_handler(
    calls: list[tuple[str, dict]],
    checksum_ids: Sequence[str] = (),
    path_ids: Sequence[str] = ("7",),
    job_status: str = "FINISHED",
    tag_hits: Sequence[list[dict]] = (),
    tag_create_error: bool = False,
    image_update_error: bool = False,
) -> Callable[[httpx.Request], httpx.Response]:
    _tag_hit_idx: list[int] = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        query = str(body.get("query", ""))
        variables = body.get("variables") or {}
        calls.append((query, variables))

        if "metadataScan" in query:
            return httpx.Response(200, json={"data": {"metadataScan": "job1"}})

        if "findJob" in query:
            return httpx.Response(
                200,
                json={
                    "data": {
                        "findJob": {
                            "id": "job1",
                            "status": job_status,
                            "error": None,
                        }
                    }
                },
            )

        if "findImages" in query:
            if "checksum" in query:
                images = [{"id": cid} for cid in checksum_ids]
            elif "path" in query:
                images = [{"id": pid} for pid in path_ids]
            else:
                images = []
            return httpx.Response(
                200, json={"data": {"findImages": {"images": images}}}
            )

        if "findTags" in query:
            if tag_hits:
                idx = min(_tag_hit_idx[0], len(tag_hits) - 1)
                tags = tag_hits[idx]
                _tag_hit_idx[0] += 1
            else:
                tags = [{"id": "t1", "name": "x"}]
            return httpx.Response(
                200, json={"data": {"findTags": {"tags": tags}}}
            )

        if "tagCreate" in query:
            if tag_create_error:
                return httpx.Response(
                    200, json={"errors": [{"message": "x"}]}
                )
            return httpx.Response(
                200, json={"data": {"tagCreate": {"id": "t9"}}}
            )

        if "imageUpdate" in query:
            image_id = str((variables.get("i") or {}).get("id", "7"))
            if image_update_error:
                return httpx.Response(
                    200, json={"errors": [{"message": "x"}]}
                )
            return httpx.Response(
                200, json={"data": {"imageUpdate": {"id": image_id}}}
            )

        if "stashes" in query:
            return httpx.Response(
                200,
                json={
                    "data": {
                        "configuration": {
                            "general": {"stashes": [{"path": "/lib"}]}
                        }
                    }
                },
            )

        return httpx.Response(400, json={"errors": [{"message": query}]})

    return handler


def make_site_handler(
    requests: list[httpx.Request],
    content: bytes = b"pngbytes",
    content_length: int | None = None,
) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        headers: dict[str, str] = {}
        if content_length is not None:
            headers["content-length"] = str(content_length)
        return httpx.Response(200, content=content, headers=headers)

    return handler


def make_post(md5: str = MD5) -> Post:
    return Post(
        source="fake",
        post_id="42",
        md5=md5,
        file_url=URL,
        source_url="http://site/post/42",
    )


def patch_folder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        stash.destinations,
        "validate_folder",
        lambda folder, libs, pp="", ps="": folder,
    )


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    init_db(tmp_path / "p.db")
    return Settings(
        mode="fixture",
        db_path=tmp_path / "p.db",
        stash_temp_dir=tmp_path / "temp",
        stash_default_dir=tmp_path / "other",
        stash_scan_timeout_s=5.0,
        stash_api_key=SECRET,
        _env_file=None,  # pyright: ignore[reportCallIssue]
    )


@pytest.fixture()
def graphql_calls() -> list[tuple[str, dict]]:
    return []


@pytest.fixture()
def site_requests() -> list[httpx.Request]:
    return []


@pytest.fixture()
def make_target(
    settings: Settings,
    graphql_calls: list[tuple[str, dict]],
    site_requests: list[httpx.Request],
):
    def _make(
        checksum_ids: Sequence[str] = (),
        path_ids: Sequence[str] = ("7",),
        content: bytes = b"pngbytes",
        content_length: int | None = None,
        job_status: str = "FINISHED",
        tag_hits: Sequence[list[dict]] = (),
        tag_create_error: bool = False,
        image_update_error: bool = False,
        api_key: str = "k",
        clock: Callable[[], float] | None = None,
    ) -> StashTarget:
        graphql = httpx.MockTransport(
            make_graphql_handler(
                graphql_calls,
                checksum_ids,
                path_ids,
                job_status=job_status,
                tag_hits=tag_hits,
                tag_create_error=tag_create_error,
                image_update_error=image_update_error,
            )
        )
        site = httpx.MockTransport(
            make_site_handler(site_requests, content, content_length)
        )
        client = StashClient(
            base_url="http://stash",
            api_key=api_key,
            client=httpx.Client(base_url="http://stash", transport=graphql),
        )
        http = httpx.Client(base_url="http://site", transport=site)
        sources: dict[str, Source] = {"fake": FakeSource()}
        return StashTarget(
            settings,
            client,
            http,
            sources,
            sleep=lambda _s: None,
            clock=clock if clock is not None else (lambda: 0.0),
        )

    return _make


@pytest.fixture()
def saved_item(settings: Settings) -> None:
    conn = connect(settings.db_path)
    conn.execute(
        "INSERT OR IGNORE INTO saved_items "
        "(source, post_id, md5, target, image_id) "
        "VALUES (?, ?, ?, 'stash', ?)",
        ("fake", "42", MD5, "7"),
    )
    conn.commit()
    conn.close()


def op_name(query: str) -> str:
    if "checksum" in query:
        return "checksum"
    if "findImages" in query:
        return "path"
    for name in ("stashes", "metadataScan", "findJob", "findTags", "tagCreate", "imageUpdate"):
        if name in query:
            return name
    return query


def test_happy_path(
    settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    make_target,
    graphql_calls: list[tuple[str, dict]],
    site_requests: list[httpx.Request],
) -> None:
    patch_folder(monkeypatch)
    target = make_target()
    result = target.save(make_post(), ["blue_hair", "Blue Hair"])

    assert result.status == "saved"
    assert result.image_id == "7"
    assert result.dest_path == (tmp_path / "other" / "fake_42.png").as_posix()
    assert (tmp_path / "other" / "fake_42.png").read_bytes() == b"pngbytes"
    assert len(site_requests) == 1
    assert list((tmp_path / "temp").glob("*")) == []
    assert any(
        n.code == "tags_created" and n.message == "created tags: blue hair"
        for n in result.notices
    )

    conn = connect(settings.db_path)
    row = conn.execute(
        "SELECT source, post_id, md5, target, image_id FROM saved_items "
        "WHERE source = ? AND post_id = ?",
        ("fake", "42"),
    ).fetchone()
    conn.close()
    assert dict(row) == {
        "source": "fake",
        "post_id": "42",
        "md5": MD5,
        "target": "stash",
        "image_id": "7",
    }

    op_names = [
        "checksum",
        "stashes",
        "metadataScan",
        "findJob",
        "path",
        "findTags",
        "tagCreate",
        "imageUpdate",
    ]
    assert [op_name(q) for q, _ in graphql_calls] == op_names

    stash_path = (tmp_path / "other" / "fake_42.png").as_posix()
    assert graphql_calls[0][1] == {"v": MD5}
    assert graphql_calls[2][1] == {"p": [stash_path]}
    assert graphql_calls[4][1] == {"v": stash_path}
    assert graphql_calls[5][1] == {"v": "blue hair"}
    assert graphql_calls[6][1] == {"n": "blue hair"}
    assert graphql_calls[7][1] == {
        "i": {
            "id": "7",
            "tag_ids": ["t9"],
            "urls": ["http://site/post/42"],
        }
    }


def test_duplicate_saved_items_post(
    settings: Settings,
    make_target,
    site_requests: list[httpx.Request],
) -> None:
    conn = connect(settings.db_path)
    conn.execute(
        "INSERT INTO saved_items "
        "(source, post_id, md5, target, image_id) "
        "VALUES (?, ?, ?, 'stash', ?)",
        ("fake", "42", MD5, "7"),
    )
    conn.commit()
    conn.close()

    target = make_target()
    result = target.save(make_post(), [])

    assert result.status == "duplicate"
    assert result.image_id == "7"
    assert site_requests == []
    assert len(result.notices) == 1
    assert result.notices[0].code == "duplicate"
    assert "saved_items by post" in result.notices[0].message


def test_duplicate_saved_items_md5_other_post(
    settings: Settings,
    make_target,
    site_requests: list[httpx.Request],
) -> None:
    conn = connect(settings.db_path)
    conn.execute(
        "INSERT INTO saved_items "
        "(source, post_id, md5, target, image_id) "
        "VALUES (?, ?, ?, 'stash', ?)",
        ("fake", "99", MD5, "8"),
    )
    conn.commit()
    conn.close()

    target = make_target()
    result = target.save(make_post(), [])

    assert result.status == "duplicate"
    assert result.image_id == "8"
    assert site_requests == []
    assert len(result.notices) == 1
    assert result.notices[0].code == "duplicate"
    assert "saved_items by md5" in result.notices[0].message


def test_duplicate_stash_checksum(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    make_target,
    site_requests: list[httpx.Request],
) -> None:
    patch_folder(monkeypatch)
    target = make_target(checksum_ids=("5",))
    result = target.save(make_post(), [])

    assert result.status == "duplicate"
    assert result.image_id == "5"
    assert site_requests == []
    assert len(result.notices) == 1
    assert result.notices[0].code == "duplicate"
    assert "Stash checksum" in result.notices[0].message

    conn = connect(settings.db_path)
    row = conn.execute(
        "SELECT source, post_id, md5, target, image_id FROM saved_items "
        "WHERE source = ? AND post_id = ?",
        ("fake", "42"),
    ).fetchone()
    conn.close()
    assert dict(row) == {
        "source": "fake",
        "post_id": "42",
        "md5": MD5,
        "target": "stash",
        "image_id": "5",
    }


def test_site_destination_beats_default(
    settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    make_target,
) -> None:
    patch_folder(monkeypatch)
    site_dir = tmp_path / "site"
    site_dir.mkdir()

    conn = connect(settings.db_path)
    conn.execute(
        "INSERT INTO destinations (site, folder) VALUES (?, ?)",
        ("fake", site_dir.as_posix()),
    )
    conn.commit()
    conn.close()

    target = make_target()
    result = target.save(make_post(), [])

    assert result.status == "saved"
    assert result.dest_path == (site_dir / "fake_42.png").as_posix()
    assert (site_dir / "fake_42.png").read_bytes() == b"pngbytes"


def test_name_clash_creates_numbered_file(
    settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    make_target,
) -> None:
    patch_folder(monkeypatch)
    folder = tmp_path / "other"
    folder.mkdir()
    (folder / "fake_42.png").write_bytes(b"old")

    target = make_target()
    result = target.save(make_post(), [])

    assert result.status == "saved"
    assert [n.code for n in result.notices] == ["name_clash"]
    assert (folder / "fake_42_2.png").read_bytes() == b"pngbytes"
    assert (folder / "fake_42.png").read_bytes() == b"old"


def test_same_md5_existing_file_resumes(
    settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    make_target,
    site_requests: list[httpx.Request],
) -> None:
    patch_folder(monkeypatch)
    folder = tmp_path / "other"
    folder.mkdir()
    (folder / "fake_42.png").write_bytes(b"pngbytes")

    target = make_target()
    result = target.save(make_post(), [])

    assert result.status == "saved"
    assert result.dest_path == (folder / "fake_42.png").as_posix()
    assert (folder / "fake_42.png").read_bytes() == b"pngbytes"
    assert not (folder / "fake_42_2.png").exists()
    assert len(site_requests) == 1

def test_size_mismatch(
    settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    make_target,
) -> None:
    patch_folder(monkeypatch)
    target = make_target(content_length=999)
    post = make_post()
    with pytest.raises(stash.SaveError) as exc:
        target.save(post, [])
    assert exc.value.code == "size_mismatch"
    assert list((tmp_path / "temp").glob("*.part")) == []


def test_md5_mismatch(
    settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    make_target,
) -> None:
    patch_folder(monkeypatch)
    target = make_target()
    post = make_post(md5="0" * 32)
    with pytest.raises(stash.SaveError) as exc:
        target.save(post, [])
    assert exc.value.code == "md5_mismatch"


def test_host_not_allowed(
    settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    make_target,
    site_requests: list[httpx.Request],
) -> None:
    patch_folder(monkeypatch)
    target = make_target()
    post = make_post().model_copy(update={"file_url": "http://evil.example/a/file.png"})
    with pytest.raises(stash.SaveError) as exc:
        target.save(post, [])
    assert exc.value.code == "host_not_allowed"
    assert site_requests == []


def test_scan_failed(
    settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    make_target,
) -> None:
    patch_folder(monkeypatch)
    target = make_target(job_status="FAILED")
    post = make_post()
    with pytest.raises(stash.SaveError) as exc:
        target.save(post, [])
    assert exc.value.code == "scan_failed"


def test_scan_timeout(
    settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    make_target,
) -> None:
    patch_folder(monkeypatch)
    state = [0.0]

    def clock() -> float:
        state[0] += 1.0
        return state[0]

    target = make_target(job_status="RUNNING", clock=clock)
    post = make_post()
    with pytest.raises(stash.SaveError) as exc:
        target.save(post, [])
    assert exc.value.code == "scan_timeout"


def test_image_not_found(
    settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    make_target,
) -> None:
    patch_folder(monkeypatch)
    target = make_target(path_ids=())
    post = make_post()
    with pytest.raises(stash.SaveError) as exc:
        target.save(post, [])
    assert exc.value.code == "image_not_found"

def _graphql_ops(graphql_calls: list[tuple[str, dict]]) -> list[str]:
    return [op_name(query) for query, _ in graphql_calls]


def _graphql_data(
    graphql_calls: list[tuple[str, dict]],
    op: str,
) -> list[dict]:
    return [data for query, data in graphql_calls if op_name(query) == op]


def _image_update_tag_ids(graphql_calls: list[tuple[str, dict]]) -> list[str]:
    ids: list[str] = []
    for data in _graphql_data(graphql_calls, "imageUpdate"):
        if isinstance(data, dict):
            for value in data.values():
                if isinstance(value, list):
                    ids.extend(str(item) for item in value)
                elif isinstance(value, dict):
                    ids.extend(
                        str(item)
                        for key, tag_value in value.items()
                        if key in {"tags", "tag_ids", "tagIds"}
                        and isinstance(tag_value, list)
                        for item in tag_value
                    )
    return ids




def test_tag_exists(
    settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    make_target: Callable[..., StashTarget],
    graphql_calls: list[tuple[str, dict]],
) -> None:
    patch_folder(monkeypatch)
    target = make_target(tag_hits=([{"id": "t1", "name": "Blue Hair"}],))
    tag_id, created = target._tag_id("blue hair")
    assert tag_id == "t1"
    assert created is False
    assert "tagCreate" not in _graphql_ops(graphql_calls)
    assert "findTags" in _graphql_ops(graphql_calls)


def test_tag_wildcard_exact_pick(
    settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    make_target: Callable[..., StashTarget],
    graphql_calls: list[tuple[str, dict]],
) -> None:
    patch_folder(monkeypatch)
    target = make_target(
        tag_hits=
            (
                [
                    {"id": "t2", "name": "blue hair extra"},
                    {"id": "t3", "name": "blue hair"},
                ],
            ),
    )
    tag_id, created = target._tag_id("blue hair")
    assert tag_id == "t3"
    assert created is False
    assert "tagCreate" not in _graphql_ops(graphql_calls)


def test_tag_create_race_retries_find_tags(
    settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    make_target: Callable[..., StashTarget],
    graphql_calls: list[tuple[str, dict]],
) -> None:
    patch_folder(monkeypatch)
    target = make_target(
        tag_hits=(
            [],
            [{"id": "t4", "name": "blue hair"}],
        ),
        tag_create_error=True,
    )
    result = target.save(make_post(), ["blue hair"])
    assert result.image_id == "7"
    assert "tagCreate" in _graphql_ops(graphql_calls)
    assert _image_update_tag_ids(graphql_calls) == ["t4"]


def test_image_update_failure_notice(
    settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    make_target: Callable[..., StashTarget],
) -> None:
    patch_folder(monkeypatch)
    target = make_target(image_update_error=True)
    result = target.save(make_post(), ["blue hair"])
    assert result.image_id == "7"
    assert [n.code for n in result.notices] == ["tags_not_applied", "tags_created"]
    conn = connect(settings.db_path)
    row = conn.execute(
        "SELECT source, post_id, md5, target, image_id FROM saved_items "
        "WHERE source = ? AND post_id = ?",
        ("fake", "42"),
    ).fetchone()
    conn.close()
    assert tuple(row) == ("fake", "42", MD5, "stash", "7")


def test_cleanup_temp(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    make_target: Callable[..., StashTarget],
) -> None:
    patch_folder(monkeypatch)
    temp_dir = settings.stash_temp_dir
    temp_dir.mkdir(parents=True, exist_ok=True)
    part_path = temp_dir / f"pearlie-fake-1-{MD5}.png.part"
    orphan_path = temp_dir / f"pearlie-fake-2-{MD5}.png"
    running_path = temp_dir / f"pearlie-fake-3-{MD5}.png"
    foreign_path = temp_dir / "foreign.txt"
    for path in (part_path, orphan_path, running_path, foreign_path):
        path.write_text("x")

    conn = connect(settings.db_path)
    conn.execute(
        "INSERT INTO jobs (source, post_id, status) VALUES (?, ?, ?)",
        ("fake", "3", "running"),
    )
    conn.commit()
    conn.close()

    target = make_target()
    target.cleanup_temp()

    assert not part_path.exists()
    assert not orphan_path.exists()
    assert running_path.exists()
    assert foreign_path.exists()


def test_api_key_not_logged(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    make_target: Callable[..., StashTarget],
) -> None:
    patch_folder(monkeypatch)
    sentinel = "SENTINEL-SECRET-KEY"
    caplog.set_level("DEBUG")

    make_target(api_key=sentinel).save(make_post(), ["blue hair"])

    with pytest.raises(stash.SaveError) as scan:
        make_target(api_key=sentinel, job_status="FAILED", content=b"third").save(
            make_post().model_copy(update={"post_id": "9", "md5": None}), []
        )
    assert scan.value.code == "scan_failed"
    assert sentinel not in str(scan.value)

    result = make_target(
        api_key=sentinel, image_update_error=True, content=b"other"
    ).save(
        make_post().model_copy(update={"post_id": "10", "md5": None}),
        ["blue hair"],
    )
    assert "tags_not_applied" in [n.code for n in result.notices]

    assert sentinel not in caplog.text


def test_download_waits_on_site_throttle(
    settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_folder(monkeypatch)
    now = [0.0]
    sleeps: list[float] = []

    def sleep(s: float) -> None:
        sleeps.append(s)
        now[0] += s

    throttle = Throttle(2.0, clock=lambda: now[0], sleep=sleep)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"pngbytes")

    def _no_graphql(request: httpx.Request) -> httpx.Response:
        raise AssertionError("graphql should not be called in _download")

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = StashClient(
        base_url="http://stash",
        api_key=SECRET,
        client=httpx.Client(
            base_url="http://stash",
            transport=httpx.MockTransport(_no_graphql),
        ),
    )
    sources: dict[str, Source] = {"fake": FakeSource()}
    target = StashTarget(
        settings,
        client,
        http,
        sources,
        sleep=sleep,
        clock=lambda: now[0],
        throttles={"fake": throttle},
    )

    target._download(URL, make_post(), ".png")
    target._download(URL, make_post(), ".png")

    assert sleeps == [2.0]


def test_download_429_slows_next_request(
    settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_folder(monkeypatch)
    now = [0.0]
    sleeps: list[float] = []

    def sleep(s: float) -> None:
        sleeps.append(s)
        now[0] += s

    throttle = Throttle(2.0, clock=lambda: now[0], sleep=sleep)
    state = {"status": 429}

    def handler(request: httpx.Request) -> httpx.Response:
        if state["status"] == 429:
            return httpx.Response(429, headers={"Retry-After": "30"})
        return httpx.Response(200, content=b"pngbytes")

    def _no_graphql(request: httpx.Request) -> httpx.Response:
        raise AssertionError("graphql should not be called in _download")

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = StashClient(
        base_url="http://stash",
        api_key=SECRET,
        client=httpx.Client(
            base_url="http://stash",
            transport=httpx.MockTransport(_no_graphql),
        ),
    )
    sources: dict[str, Source] = {"fake": FakeSource()}
    target = StashTarget(
        settings,
        client,
        http,
        sources,
        sleep=sleep,
        clock=lambda: now[0],
        throttles={"fake": throttle},
    )

    with pytest.raises(stash.SaveError) as exc:
        target._download(URL, make_post(), ".png")
    assert exc.value.code == "download_failed"
    assert throttle.backing_off is True

    state["status"] = 200
    target._download(URL, make_post(), ".png")

    assert sleeps[-1] == pytest.approx(30.0)
