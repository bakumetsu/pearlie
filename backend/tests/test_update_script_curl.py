"""deploy/pearlie-update.sh: GitHub calls must be https only."""

from __future__ import annotations

import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "deploy" / "pearlie-update.sh"


def test_github_curl_calls_restrict_protocol() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    calls = [ln for ln in text.splitlines() if re.search(r"\bcurl\b.*-fsSL", ln)]
    assert len(calls) == 2  # the API call and the tarball download
    for ln in calls:
        assert '--proto "$CURL_PROTO"' in ln and '--proto-redir "$CURL_PROTO"' in ln


def test_protocol_default_is_https_only() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'CURL_PROTO="=https"' in text
    # a non-GitHub base (the local test server) is the only way to allow plain http
    m = re.search(
        r'if \[\[ -n "\$\{PEARLIE_UPDATE_API_BASE:-\}.*\n\s*CURL_PROTO="=http,https"', text
    )
    assert m


def _run_counter(tmp_path: Path, tags: str, compare: str, fail: bool = False) -> str:
    """Run dev_counter from the script with a stubbed http_get."""
    text = SCRIPT.read_text(encoding="utf-8")

    def grab(name: str) -> str:
        m = re.search(rf"^{name}\(\) \{{\n.*?^\}}\n", text, re.S | re.M)
        assert m
        return m.group(0)

    tags_cmd = "return 1" if fail else "cat " + shlex.quote(str(tmp_path / "tags"))
    cmp_cmd = "return 1" if fail else "cat " + shlex.quote(str(tmp_path / "cmp"))
    stub = (
        "http_get() {\n"
        '  case "$1" in\n'
        f"    */tags) {tags_cmd} ;;\n"
        f"    */compare/*) {cmp_cmd} ;;\n"
        "  esac\n}\n"
    )
    (tmp_path / "tags").write_text(tags, encoding="utf-8")
    (tmp_path / "cmp").write_text(compare, encoding="utf-8")
    script = (
        f"JSON_PY={shlex.quote(sys.executable)}\nAPI=x\nTARGET_COMMIT={'a' * 40}\n"
        + stub
        + grab("highest_tag")
        + grab("dev_counter")
        + "dev_counter\n"
    )
    out = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=True)
    return out.stdout


_TAGS = '[{"name":"v0.6.0-dev"},{"name":"v0.5.0"},{"name":"v0.6.0"}]'


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash missing")
@pytest.mark.parametrize("n", [0, 9])
def test_dev_counter_uses_ahead_by(tmp_path: Path, n: int) -> None:
    assert _run_counter(tmp_path, _TAGS, f'{{"ahead_by":{n}}}') == f".{n}"


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash missing")
@pytest.mark.parametrize("compare", ["{}", "nope", '{"ahead_by":"3"}', '{"ahead_by":-1}'])
def test_dev_counter_bad_compare_is_empty(tmp_path: Path, compare: str) -> None:
    assert _run_counter(tmp_path, _TAGS, compare) == ""


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash missing")
def test_dev_counter_api_failure_is_empty(tmp_path: Path) -> None:
    assert _run_counter(tmp_path, _TAGS, '{"ahead_by":4}', fail=True) == ""
