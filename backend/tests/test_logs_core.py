from __future__ import annotations

import base64
import logging
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote

import pytest

from app import logs

SENTINEL = "SENTINEL-KEY-9f3a1c77"


@pytest.fixture(autouse=True)
def _clean_registry() -> Iterator[None]:
    logs.clear_secrets()
    yield
    logs.clear_secrets()


@pytest.fixture()
def handler(tmp_path: Path) -> Iterator[logs.DailyFileHandler]:
    h = logs.setup_logging(tmp_path / "logs")
    yield h
    logging.getLogger().removeHandler(h)
    h.close()
    logs._handler = None


def read_all(directory: Path) -> str:
    return "".join(f.read_text(encoding="utf-8") for f in sorted(directory.glob("*.log")))


SECRET_LINES = [
    f"api_key={SENTINEL}",
    f"apikey={SENTINEL}",
    f"x-api-key: {SENTINEL}",
    f"X-API-Key: {SENTINEL}",
    f"ApiKey: {SENTINEL}",
    f"Authorization: Bearer {SENTINEL}",
    f"Authorization: Basic {SENTINEL}",
    f"Cookie: sessionid={SENTINEL}; csrftoken=abc",
    f"Set-Cookie: sid={SENTINEL}; Path=/",
    f"Bearer {SENTINEL}",
    f"refresh_token={SENTINEL}",
    f"token: {SENTINEL}",
    f"password={SENTINEL}",
    f"passwd={SENTINEL}",
    f"secret={SENTINEL}",
    f"session={SENTINEL}",
    f'cookie="{SENTINEL}"',
    f"https://host/path?api_key={SENTINEL}&user_id=1",
    f"https://host/path?x=1#{SENTINEL}",
    f"https://user:{SENTINEL}@host/path",
    f"GET https://gelbooru.com/index.php?page=dapi&api_key={SENTINEL}&user_id=42 failed",
    f"key={SENTINEL}",
    f"{SENTINEL}",
    quote(SENTINEL, safe=""),
    base64.b64encode(SENTINEL.encode()).decode(),
    base64.urlsafe_b64encode(SENTINEL.encode()).decode().rstrip("="),
    "a" * 20 + "0" * 25,
    "ZXhhbXBsZXRva2VuMTIzNDU2Nzg5MGFiY2RlZmdoaWprbG1ub3A",
    f"nested: failed with 'token={SENTINEL}' in message",
    f"cookie={SENTINEL}",
]


@pytest.mark.parametrize("text", SECRET_LINES)
def test_secret_shapes_are_scrubbed(text: str) -> None:
    logs.register_secret(SENTINEL)
    out = logs.scrub(text)
    assert SENTINEL not in out
    assert quote(SENTINEL, safe="") not in out
    assert base64.b64encode(SENTINEL.encode()).decode() not in out
    assert "ZXhhbXBsZXRva2VuMTIzNDU2Nzg5MGFiY2RlZmdoaWprbG1ub3A" not in out
    assert "0" * 25 not in out


def test_pattern_filter_works_without_registry() -> None:
    for text in SECRET_LINES[:22]:
        assert SENTINEL not in logs.scrub(text)


NORMAL_LINES = [
    "author=bob",
    "monkey=1",
    "keyframes=24",
    "sessions=3",
    "status=200",
    "md5=" + "ab12" * 8,
    "checksum=" + "cd34" * 8,
    "dest=/mnt/media/stash/Other/rule34_19328710.jpg",
    "host.example/path/to/file.png",
    "temp=pearlie-rule34-19328710-" + "ef56" * 8 + ".jpg",
    "step=download status=200 bytes=482113 ms=910",
    "/mnt/media/stash/Some/Very/Long/Folder/Structure/Of/The/Library/2026",
]


@pytest.mark.parametrize("text", NORMAL_LINES)
def test_normal_fields_stay_readable(text: str) -> None:
    assert logs.scrub(text) == text


def test_short_secret_ignored_and_runtime_registration() -> None:
    logs.register_secret("abc")
    assert logs.scrub("abc def") == "abc def"
    assert SENTINEL in logs.scrub(f"late {SENTINEL}")
    logs.register_secret(SENTINEL)
    assert SENTINEL not in logs.scrub(f"late {SENTINEL}")


def test_safe_url() -> None:
    assert logs.safe_url("https://u:p@h.example:8080/a/b?api_key=x#f") == "h.example:8080/a/b"
    assert logs.safe_url("http://h.example/a.png") == "h.example/a.png"


def test_filter_covers_args_and_traceback(handler: logs.DailyFileHandler, tmp_path: Path) -> None:
    logs.register_secret(SENTINEL)
    log = logging.getLogger("pearlie.test")
    log.info("value %s", SENTINEL)
    try:
        raise RuntimeError(f"boom {SENTINEL}")
    except RuntimeError:
        log.error("failed", exc_info=True)
    text = read_all(tmp_path / "logs")
    assert SENTINEL not in text
    assert "value ***" in text
    assert text.count("\n") == 2  # traceback stays on one line


def test_debug_switch_and_name_filter(handler: logs.DailyFileHandler, tmp_path: Path) -> None:
    log = logging.getLogger("pearlie.test")
    log.debug("quiet")
    logging.getLogger("uvicorn.access").warning("access noise")
    logging.getLogger("httpx").warning("httpx noise")
    logging.getLogger("app.x").info("kept app")
    logs.set_debug(True)
    log.debug("loud")
    logs.set_debug(False)
    log.debug("quiet again")
    text = read_all(tmp_path / "logs")
    assert "loud" in text and "kept app" in text
    assert "quiet" not in text
    assert "noise" not in text


def test_line_cap(handler: logs.DailyFileHandler, tmp_path: Path) -> None:
    logging.getLogger("pearlie.test").info("x" * 5000)
    line = read_all(tmp_path / "logs").rstrip("\n")
    assert len(line) == logs.MAX_LINE
    assert line.endswith(logs.CUT_MARK)


def test_day_cap_drops_lines_but_keeps_errors(tmp_path: Path) -> None:
    h = logs.DailyFileHandler(tmp_path / "logs", day_cap=600, error_cap=1200)
    log = logging.Logger("pearlie.cap")
    log.addHandler(h)
    for i in range(50):
        log.info("line %d %s", i, "y" * 40)
    capped = read_all(tmp_path / "logs")
    assert capped.count(logs.CAP_LINE) == 1
    size = len(capped.encode())
    assert size < 900
    log.error("must survive")
    assert "must survive" in read_all(tmp_path / "logs")
    h.close()


def test_purge_old_keeps_other_files(tmp_path: Path) -> None:
    d = tmp_path / "logs"
    d.mkdir()
    today = date.today()
    old = d / f"pearlie-{today - timedelta(days=8):%Y-%m-%d}.log"
    keep = d / f"pearlie-{today - timedelta(days=7):%Y-%m-%d}.log"
    fresh = d / f"pearlie-{today:%Y-%m-%d}.log"
    other = d / "notes.txt"
    near = d / "pearlie-2020-01-01.log.bak"
    for f in (old, keep, fresh, other, near):
        f.write_text("x")
    removed = logs.purge_old(d, 7)
    assert removed == [old.name]
    assert not old.exists()
    assert keep.exists() and fresh.exists() and other.exists() and near.exists()


def test_handler_purges_at_startup(tmp_path: Path) -> None:
    d = tmp_path / "logs"
    d.mkdir()
    old = d / "pearlie-2001-01-01.log"
    old.write_text("x")
    logs.DailyFileHandler(d).close()
    assert not old.exists()


def test_write_failure_never_raises(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    h = logs.DailyFileHandler(tmp_path / "logs")
    (tmp_path / "logs").rmdir()
    log = logging.Logger("pearlie.fail")
    log.addHandler(h)
    log.info("a")
    log.info("b")
    assert capsys.readouterr().err.count("pearlie log:") == 1


def test_daily_file_follows_record_date(handler: logs.DailyFileHandler, tmp_path: Path) -> None:
    logging.getLogger("pearlie.test").info("today")
    names = [f.name for f in (tmp_path / "logs").glob("*.log")]
    assert names == [f"pearlie-{date.today():%Y-%m-%d}.log"]
