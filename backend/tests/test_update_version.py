from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.update import version as version_mod
from app.update.version import Installed, current_version, is_newer, parse_semver


def test_parse_semver_valid() -> None:
    assert parse_semver("1.2.3") == (1, 2, 3)


def test_parse_semver_invalid() -> None:
    assert parse_semver("v1.2.3") is None
    assert parse_semver("1.2") is None
    assert parse_semver("1.2.3-x") is None


def test_is_newer_main() -> None:
    assert is_newer("1.2.4", "1.2.3", "main") is True
    assert is_newer("1.2.3", "1.2.3", "main") is False
    assert is_newer("1.2.4", "1.2.3-dev+local", "main") is True
    assert is_newer("garbage", "1.2.3", "main") is False
    assert is_newer("1.2.4", "garbage", "main") is False


def test_is_newer_dev() -> None:
    assert is_newer("abc", "def", "dev") is True
    assert is_newer("abc", "abc", "dev") is False
    assert is_newer("", "abc", "dev") is False
    assert is_newer("abc", "", "dev") is False


def test_current_version_valid_main(tmp_path: Path) -> None:
    (tmp_path / "VERSION.json").write_text(
        json.dumps({"version": "1.0.0", "channel": "main", "commit": "abc"}),
        encoding="utf-8",
    )
    assert current_version(roots=(tmp_path,)) == Installed("1.0.0", "main", "abc")


@pytest.mark.parametrize(
    "content",
    [
        "{",
        json.dumps([1, 2, 3]),
        json.dumps({"version": "1.0.0", "channel": "beta", "commit": "abc"}),
    ],
)
def test_current_version_invalid_falls_back(
    tmp_path: Path, content: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(version_mod, "_git_dev_count", lambda _r: (None, None))
    (tmp_path / "VERSION.json").write_text(content, encoding="utf-8")
    result = current_version(roots=(tmp_path,))
    assert result.version.endswith("-dev")
    assert "+" not in result.version
    assert result.channel == "dev"
    assert result.commit is None


def test_current_version_strips_build_suffix_keeps_commit(tmp_path: Path) -> None:
    (tmp_path / "VERSION.json").write_text(
        json.dumps({"version": "0.4.0-dev+abc1234", "channel": "dev", "commit": "abc1234def"}),
        encoding="utf-8",
    )
    assert current_version(roots=(tmp_path,)) == Installed("0.4.0-dev", "dev", "abc1234def")


def test_current_version_commit_non_string_is_none(tmp_path: Path) -> None:
    (tmp_path / "VERSION.json").write_text(
        json.dumps({"version": "1.0.0", "channel": "main", "commit": 123}),
        encoding="utf-8",
    )
    assert current_version(roots=(tmp_path,)) == Installed("1.0.0", "main", None)


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t", *args],
        check=True,
        capture_output=True,
    )


def _repo_with_commits(root: Path, after_tag: int) -> None:
    _git(root, "init", "-q")
    _git(root, "commit", "-q", "--allow-empty", "-m", "c0")
    _git(root, "tag", "v0.6.0")
    _git(root, "tag", "v0.6.0-dev")
    for i in range(after_tag):
        _git(root, "commit", "-q", "--allow-empty", "-m", f"c{i + 1}")


@pytest.mark.skipif(shutil.which("git") is None, reason="git missing")
@pytest.mark.parametrize("n", [0, 9])
def test_fallback_counts_commits_since_last_tag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, n: int
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _repo_with_commits(repo, n)
    monkeypatch.setattr(
        version_mod, "_git_dev_count", lambda _r, real=version_mod._git_dev_count: real(repo)
    )
    result = current_version(roots=(tmp_path / "none",))
    base = version_mod.tomllib.load(
        open(Path(version_mod.__file__).parents[2] / "pyproject.toml", "rb")
    )["project"]["version"]
    assert result.version == f"{base}-dev.{n}"
    assert result.channel == "dev"
    assert result.commit is not None and len(result.commit) == 40


def test_fallback_without_git_is_plain_dev(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert version_mod._git_dev_count(tmp_path) == (None, None)
    monkeypatch.setattr(version_mod, "_git_dev_count", lambda _r: (None, None))
    result = current_version(roots=(tmp_path,))
    assert result.version.endswith("-dev")
    assert result.commit is None
