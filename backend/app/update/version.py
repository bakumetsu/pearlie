"""Version detection for Pearlie update checks."""

import json
import re
import subprocess
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


def _git(root: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip()


def _git_dev_count(root: Path) -> tuple[int | None, str | None]:
    """Commits since the highest release tag, and HEAD, from a git checkout."""
    if not (root / ".git").exists():
        return None, None
    tags = _git(root, "tag", "--list", "v*")
    commit = _git(root, "rev-parse", "HEAD")
    if not tags or not commit:
        return None, None
    best: tuple[tuple[int, int, int], str] | None = None
    for tag in tags.splitlines():
        ver = parse_semver(tag[1:]) if tag.startswith("v") else None
        if ver is not None and (best is None or ver > best[0]):
            best = (ver, tag)
    if best is None:
        return None, None
    count = _git(root, "rev-list", "--count", f"{best[1]}..HEAD")
    if count is None or not count.isdigit():
        return None, None
    return int(count), commit


def base_version() -> str:
    """Version in pyproject.toml: the next release, the base of every dev build."""
    try:
        with open(Path(__file__).parents[2] / "pyproject.toml", "rb") as f:
            v = tomllib.load(f)["project"]["version"]
    except (OSError, tomllib.TOMLDecodeError, KeyError, TypeError):
        return "0.0.0"
    return v if isinstance(v, str) else "0.0.0"


def dev_version(n: int) -> str:
    return f"{base_version()}-dev.{n}"


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
    n, commit = _git_dev_count(Path(__file__).parents[3])
    if n is None:
        return Installed(f"{base_version()}-dev", "dev", None)
    return Installed(dev_version(n), "dev", commit)


def short_label(installed: Installed) -> str:
    return installed.version
