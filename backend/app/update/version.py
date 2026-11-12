"""Version detection for Pearlie update checks."""

import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def parse_semver(text: str) -> tuple[int, int, int] | None:
    if SEMVER.match(text) is None:
        return None
    a, b, c = text.split(".")
    return int(a), int(b), int(c)


def is_newer(latest: str, installed: str, channel: str) -> bool:
    if channel == "main":
        for i, ch in enumerate(installed):
            if ch in "-+":
                installed = installed[:i]
                break
        lt = parse_semver(latest)
        it = parse_semver(installed)
        if lt is None or it is None:
            return False
        return lt > it
    if channel == "dev":
        return latest != "" and installed != "" and latest != installed
    return False


@dataclass(frozen=True)
class Installed:
    version: str
    channel: str
    commit: str | None


def current_version(roots: tuple[Path, ...] | None = None) -> Installed:
    if roots is None:
        roots = (Path(__file__).parents[3], Path("/opt/pearlie/current/app"))
    for root in roots:
        try:
            data = json.loads((root / "VERSION.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        version = data.get("version")
        channel = data.get("channel")
        commit = data.get("commit")
        if not isinstance(version, str):
            continue
        if channel not in ("main", "dev"):
            continue
        if not isinstance(commit, str):
            commit = None
        return Installed(version=version.split("+", 1)[0], channel=channel, commit=commit)
    base = "0.0.0"
    try:
        with open(Path(__file__).parents[2] / "pyproject.toml", "rb") as f:
            toml_data = tomllib.load(f)
        v = toml_data["project"]["version"]
        if isinstance(v, str):
            base = v
    except (OSError, tomllib.TOMLDecodeError, KeyError, TypeError):
        pass
    return Installed(f"{base}-dev", "dev", None)


def short_label(installed: Installed) -> str:
    return installed.version
