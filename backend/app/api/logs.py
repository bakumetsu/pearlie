"""Log inspection and download endpoints."""

import re
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, StrictBool

from app import logs
from app.api.errors import ApiError
from app.api.guard import write_guard
from app.db import connect

router = APIRouter(prefix="/api/logs")

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_LINE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) ([A-Z]+)  (\S+)  (.*)$")
_LEVEL_RANK: dict[str, int] = {"debug": 0, "info": 1, "warning": 2, "error": 3}
_CHUNK = 64 * 1024


class DebugBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    debug: StrictBool


def _validate_date(date: str) -> None:
    if not _DATE_RE.match(date):
        raise ApiError(404, "not_found", "No log for that day")
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise ApiError(404, "not_found", "No log for that day") from None


def _log_file(log_dir: Path, date: str) -> Path:
    path = log_dir / f"pearlie-{date}.log"
    if not path.is_file():
        raise ApiError(404, "not_found", "No log for that day")
    return path


def _count_lines(path: Path) -> int:
    count = 0
    last: bytes = b""
    with path.open("rb") as fh:
        while chunk := fh.read(_CHUNK):
            count += chunk.count(b"\n")
            last = chunk[-1:]
    if last and last != b"\n":
        count += 1
    return count


def _iter_lines_backwards(fh: BinaryIO, end: int) -> Iterator[tuple[int, bytes]]:
    pos = end
    buf = b""
    while pos > 0:
        n = min(_CHUNK, pos)
        pos -= n
        fh.seek(pos)
        buf = fh.read(n) + buf
        parts = buf.split(b"\n")
        if pos > 0:
            first = parts[0]
            rest = parts[1:]
            base = pos + len(first) + 1
            buf = first
        else:
            rest = parts
            base = 0
            buf = b""
        lines: list[tuple[int, bytes]] = []
        offset = base
        for part in rest:
            if part:
                lines.append((offset, part))
            offset += len(part) + 1
        for start, part in reversed(lines):
            yield start, part


def _parse_line(raw: str) -> tuple[str, str, str, str]:
    m = _LINE_RE.match(raw)
    if m:
        ts, level, logger, text = m.groups()
        lvl = level.lower()
        if lvl not in _LEVEL_RANK:
            lvl = "error"
        return ts, lvl, logger, logs.scrub(text)
    return "", "info", "", logs.scrub(raw)


def _line_rank(level: str) -> int:
    if level == "critical":
        return _LEVEL_RANK["error"]
    return _LEVEL_RANK.get(level, _LEVEL_RANK["info"])


def _check_level(level: str) -> int:
    if level not in _LEVEL_RANK:
        raise ApiError(422, "invalid", "level must be debug, info, warning, or error")
    return _LEVEL_RANK[level]


@router.get("")
def list_logs() -> dict:
    log_dir = logs.log_dir()
    if log_dir is None:
        return {
            "debug": logs.is_debug(),
            "keep_days": logs.LOG_KEEP_DAYS,
            "dir_name": "logs",
            "files": [],
            "cap_bytes": logs.DAY_CAP,
        }
    logs.purge_old(log_dir)
    files: list[dict] = []
    try:
        entries = sorted(log_dir.iterdir())
    except OSError:
        return {
            "debug": logs.is_debug(),
            "keep_days": logs.LOG_KEEP_DAYS,
            "dir_name": "logs",
            "files": [],
            "cap_bytes": logs.DAY_CAP,
        }
    for entry in entries:
        if not entry.is_file():
            continue
        m = logs.FILE_RE.fullmatch(entry.name)
        if m is None:
            continue
        files.append(
            {
                "date": f"{m[1]}-{m[2]}-{m[3]}",
                "size_bytes": entry.stat().st_size,
                "lines": _count_lines(entry),
            }
        )
    files.sort(key=lambda f: f["date"], reverse=True)
    return {
        "debug": logs.is_debug(),
        "keep_days": logs.LOG_KEEP_DAYS,
        "dir_name": "logs",
        "files": files,
        "cap_bytes": logs.DAY_CAP,
    }


@router.get("/settings")
def get_settings() -> dict:
    return {"debug": logs.is_debug()}


@router.put("/settings", dependencies=[Depends(write_guard)])
def put_settings(request: Request, body: DebugBody) -> dict:
    v = body.debug
    conn = connect(request.app.state.settings.db_path)
    try:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (logs.SETTING_KEY, "1" if v else "0"),
        )
        conn.commit()
    finally:
        conn.close()
    logs.set_debug(v)
    return {"debug": v}


@router.get("/{date}/download")
def download_log(date: str, level: str | None = None) -> StreamingResponse:
    log_dir = logs.log_dir()
    if log_dir is None:
        raise ApiError(404, "not_found", "No log for that day")
    _validate_date(date)
    path = _log_file(log_dir, date)
    min_rank = _check_level(level.lower()) if level else 0

    def _stream() -> Iterator[str]:
        with path.open("rb") as fh:
            for line in fh:
                text = line.decode("utf-8", errors="replace").rstrip("\n")
                if min_rank > 0:
                    _ts, lvl, _logger, _txt = _parse_line(text)
                    if _line_rank(lvl) < min_rank:
                        continue
                yield logs.scrub(text) + "\n"

    return StreamingResponse(
        _stream(),
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="pearlie-{date}.log"',
        },
    )


@router.get("/{date}")
def get_log_lines(
    date: str,
    level: str = "info",
    limit: int = 200,
    cursor: str | None = None,
    q: str | None = None,
) -> dict:
    log_dir = logs.log_dir()
    if log_dir is None:
        raise ApiError(404, "not_found", "No log for that day")
    _validate_date(date)
    path = _log_file(log_dir, date)
    level = level.lower()
    min_rank = _check_level(level)
    if not 1 <= limit <= 1000:
        raise ApiError(422, "invalid", "limit must be between 1 and 1000")
    end = path.stat().st_size
    if cursor is not None:
        try:
            end = int(cursor)
        except ValueError:
            raise ApiError(422, "invalid", "invalid cursor") from None
        if not 0 <= end <= path.stat().st_size:
            raise ApiError(422, "invalid", "invalid cursor")

    q_lower = q.lower() if q else None
    results: list[dict] = []
    last_start: int | None = None

    with path.open("rb") as fh:
        for start, raw in _iter_lines_backwards(fh, end):
            last_start = start
            text = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            ts, lvl, logger, scrubbed_text = _parse_line(text)
            if _line_rank(lvl) < min_rank:
                continue
            if q_lower is not None and q_lower not in scrubbed_text.lower():
                continue
            results.append({"ts": ts, "level": lvl, "logger": logger, "text": scrubbed_text})
            if len(results) >= limit:
                break

    next_cursor: str | None = None
    if last_start is not None and last_start > 0:
        next_cursor = str(last_start)

    return {
        "date": date,
        "level": level,
        "lines": results,
        "next_cursor": next_cursor,
    }
