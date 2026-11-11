"""Filesystem and systemd side of the update feature under /opt/pearlie.

systemd-run (see start_update) creates a transient unit that survives
`systemctl stop pearlie` because it is not a child of the pearlie unit.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

LAYOUT_ROOT: Path = Path("/opt/pearlie")
STATES: tuple[str, ...] = (
    "idle",
    "running",
    "done",
    "rolled_back",
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

    tmp = root / "update.conf.tmp"
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
