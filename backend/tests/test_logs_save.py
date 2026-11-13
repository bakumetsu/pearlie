from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
from test_stash_target import (  # noqa: F401  (pytest fixtures)
    MD5,
    graphql_calls,
    make_post,
    make_target,
    patch_folder,
    saved_item,
    settings,
    site_requests,
)

from app import logs
from app.targets.stash import SaveError

SENTINEL = "SENTINEL-KEY-5d2e88b1"


@pytest.fixture()
def log_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    patch_folder(monkeypatch)
    logs.clear_secrets()
    logs.register_secret(SENTINEL)
    h = logs.setup_logging(tmp_path / "logs", debug=True)
    yield tmp_path / "logs"
    logging.getLogger().removeHandler(h)
    h.close()
    logs._handler = None
    logs.clear_secrets()


def checksum_after_dedupe(target, answers: list) -> None:
    """First checksum query is the dedupe check (miss); later ones answer from `answers`."""
    calls = iter(answers)

    def find(_md5: str) -> str | None:
        item = next(calls)
        if isinstance(item, Exception):
            raise item
        return item

    target._client.find_image_by_checksum = find


def text(d: Path) -> str:
    return "".join(f.read_text(encoding="utf-8") for f in sorted(d.glob("*.log")))


def test_save_writes_every_step(make_target, log_dir: Path) -> None:  # noqa: F811
    token = logs.set_job("41", "fake", "42")
    try:
        make_target().save(make_post(), ["a_tag"])
    finally:
        logs.reset_job(token)
    out = text(log_dir)
    for step in ("download", "move", "path_sent", "scan", "lookup", "tags", "record"):
        assert f"step={step}" in out, step
    assert "job=41 fake/42" in out
    assert f"md5_got={MD5}" in out
    assert "result=7" in out


def test_lookup_miss_writes_evidence(make_target, log_dir: Path) -> None:  # noqa: F811
    target = make_target(path_ids=())
    checksum_after_dedupe(target, [None, "99"])
    with pytest.raises(SaveError) as exc:
        target.save(make_post(), [])
    assert exc.value.code == "image_not_found"
    out = text(log_dir)
    assert "result=none" in out
    assert "exists_on_disk=yes" in out
    assert "stash_library_paths=['/lib']" in out
    assert "found_elsewhere=99" in out
    assert "WARNING" in out and "ERROR" in out
    assert "code=image_not_found" in out


def test_lookup_miss_survives_failing_checksum_query(
    make_target, log_dir: Path  # noqa: F811
) -> None:
    target = make_target(path_ids=())
    checksum_after_dedupe(target, [None, RuntimeError("down")])
    with pytest.raises(SaveError) as exc:
        target.save(make_post(), [])
    assert exc.value.code == "image_not_found"
    assert "checksum query failed" in text(log_dir)


def test_download_failure_logged_with_code(make_target, log_dir: Path) -> None:  # noqa: F811
    with pytest.raises(SaveError):
        make_target(content=b"other").save(make_post(), [])
    out = text(log_dir)
    assert "code=md5_mismatch" in out
    assert "ERROR" in out


def test_tag_failure_logged_as_warning(make_target, log_dir: Path) -> None:  # noqa: F811
    make_target(image_update_error=True).save(make_post(), ["x"])
    out = text(log_dir)
    assert "WARNING" in out and "imageUpdate=failed" in out


def test_no_sentinel_on_any_pipeline_path(make_target, log_dir: Path) -> None:  # noqa: F811
    log = logging.getLogger("pearlie.jobs")
    with pytest.raises(SaveError):
        make_target(path_ids=()).save(make_post(), [])
    make_target(api_key=SENTINEL).save(make_post(), ["x"])
    try:
        raise RuntimeError(f"failed api_key={SENTINEL} cookie=zz")
    except RuntimeError:
        log.error("job 1 failed", exc_info=True)
    log.info("url https://host/x?api_key=%s", SENTINEL)
    assert SENTINEL not in text(log_dir)
