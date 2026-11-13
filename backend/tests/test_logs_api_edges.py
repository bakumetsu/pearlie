"""Edge cases of /api/logs: GET never deletes or re-reads, cursor snaps to a line start."""

from __future__ import annotations

from typing import Any

import pytest

from app.api import logs as logs_api
from tests.test_logs_api import _line, _log_dir, day_file

DATE = "2026-11-13"


def _lines(n: int) -> list[str]:
    return [_line(f"{DATE} 10:00:{i:02d}.000", "INFO", "pearlie.app", f"line-{i:02d}") for i in range(n)]


def test_listing_does_not_delete_old_files(client: Any) -> None:
    ld = _log_dir(client)
    ld.mkdir(parents=True, exist_ok=True)
    day_file(ld, DATE, _lines(2))
    old = day_file(ld, "2026-11-01", _lines(1))
    body = client.get("/api/logs").json()
    assert [f["date"] for f in body["files"]] == [DATE]
    assert old.exists()


def test_listing_counts_unchanged_file_once(client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    ld = _log_dir(client)
    ld.mkdir(parents=True, exist_ok=True)
    day_file(ld, DATE, _lines(3))
    calls: list[str] = []
    real = logs_api._count_lines

    def counting(path: Any) -> int:
        calls.append(path.name)
        return real(path)

    monkeypatch.setattr(logs_api, "_count_lines", counting)
    logs_api._line_counts.clear()
    assert client.get("/api/logs").json()["files"][0]["lines"] == 3
    assert client.get("/api/logs").json()["files"][0]["lines"] == 3
    assert len(calls) == 1


def test_mid_line_cursor_snaps_to_line_start(client: Any) -> None:
    ld = _log_dir(client)
    ld.mkdir(parents=True, exist_ok=True)
    lines = _lines(5)
    path = day_file(ld, DATE, lines)
    data = path.read_bytes()
    third_start = len((lines[0] + "\n" + lines[1] + "\n").encode())
    mid = third_start + 10  # inside line-02
    assert data[mid - 1 : mid] != b"\n"
    body = client.get(f"/api/logs/{DATE}", params={"cursor": str(mid), "level": "debug"}).json()
    assert [ln["text"] for ln in body["lines"]] == ["line-01", "line-00"]
