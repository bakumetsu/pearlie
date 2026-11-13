"""Filesystem and systemd side of the update feature under /opt/pearlie.

systemd-run (see start_update) creates a transient unit that survives
`systemctl stop pearlie` because it is not a child of the pearlie unit.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

LAYOUT_ROOT: Path = Path("/opt/pearlie")
STATES: tuple[str, ...] = (
    "idle",
    "running",
    "done",
    "rolled_back",
    "reverted",
    "failed",
    "failed_rollback",
)
CHANNELS: tuple[str, ...] = ("main", "dev")


def supported(root: Path = LAYOUT_ROOT) -> bool:
    """True when the current symlink exists and its target resolves."""
    return (root / "current").exists()


def read_status(root: Path = LAYOUT_ROOT) -> dict[str, str | None]:
    idle: dict[str, str | None] = {"state": "idle", "step": None, "error": None}
    try:
        raw = (root / "update-status.json").read_text()
    except (OSError, UnicodeDecodeError):
        return idle
    try:
        data: Any = json.loads(raw)
    except json.JSONDecodeError:
        return idle
    if not isinstance(data, dict):
        return idle
    state = data.get("state")
    if state == "current":
        state = "idle"
    if state not in STATES:
        return idle
    step = data.get("step")
    error = data.get("error")
    return {
        "state": state,
        "step": step if isinstance(step, str) else None,
        "error": error if isinstance(error, str) else None,
    }


def read_conf(root: Path = LAYOUT_ROOT) -> dict[str, str]:
    try:
        text = (root / "update.conf").read_text()
    except OSError:
        return {}
    conf: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        conf[key] = value
    return conf


def write_conf(
    root: Path,
    *,
    channel: str | None = None,
    check: str | None = None,
) -> None:
    if channel is not None and channel not in CHANNELS:
        msg = f"channel must be one of {CHANNELS}, got {channel!r}"
        raise ValueError(msg)
    if check is not None and check not in ("on", "off"):
        msg = f"check must be 'on' or 'off', got {check!r}"
        raise ValueError(msg)

    path = root / "update.conf"
    try:
        lines: list[str] = path.read_text().splitlines(keepends=True)
    except FileNotFoundError:
        lines = []

    updates: dict[str, str] = {}
    if channel is not None:
        updates["channel"] = channel
    if check is not None:
        updates["check"] = check

    consumed: set[str] = set()
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.partition("=")[0]
            if key in updates:
                new_lines.append(f"{key}={updates[key]}\n")
                consumed.add(key)
                continue
        new_lines.append(line)

    # append keys that had no existing line
    for key, value in updates.items():
        if key not in consumed:
            new_lines.append(f"{key}={value}\n")

    tmp = root / f"update.conf.{os.getpid()}.{threading.get_ident()}.tmp"
    tmp.write_text("".join(new_lines))
    os.replace(tmp, path)


def is_running(
    run: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
) -> bool:
    try:
        result = run(
            ["systemctl", "is-active", "--quiet", "pearlie-update"],
            check=False,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def start_update(
    run: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
) -> bool:
    try:
        result = run(
            [
                "systemd-run",
                "--unit=pearlie-update",
                "--collect",
                "--no-block",
                "/usr/local/bin/pearlie-update",
                "--from-ui",
            ],
            check=False,
            capture_output=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _start_unit(
    args: list[str],
    run: Callable[..., subprocess.CompletedProcess[bytes]],
) -> bool:
    try:
        result = run(args, check=False, capture_output=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def start_rollback(
    restore_db: bool,
    run: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
) -> bool:
    args = [
        "systemd-run",
        "--unit=pearlie-update",
        "--collect",
        "--no-block",
        "/usr/local/bin/pearlie-update",
        "--rollback",
    ]
    if restore_db:
        args.append("--restore-db")
    args.append("--from-ui")
    return _start_unit(args, run)


def start_restart(
    run: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
) -> bool:
    return _start_unit(
        [
            "systemd-run",
            "--unit=pearlie-restart",
            "--collect",
            "--no-block",
            "systemctl",
            "restart",
            "pearlie",
        ],
        run,
    )


def read_previous(root: Path = LAYOUT_ROOT) -> tuple[str, int | None, str | None] | None:
    """(version, schema or None when unknown, backup mtime ISO or None), or None
    when no previous release is kept."""
    try:
        data: Any = json.loads((root / "previous" / "app" / "VERSION.json").read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("version"), str):
        return None
    schema = data.get("schema")
    backup_at: str | None = None
    try:
        backup = root / "backups" / (root / "current").resolve().name
        stamp = backup.stat().st_mtime
        backup_at = datetime.fromtimestamp(stamp, UTC).isoformat(timespec="seconds")
    except OSError:
        pass
    return (
        data["version"].split("+", 1)[0],
        schema if isinstance(schema, int) and not isinstance(schema, bool) else None,
        backup_at,
    )
