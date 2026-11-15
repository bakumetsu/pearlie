"""deploy/pearlie-update.sh: GitHub calls must be https only."""

from __future__ import annotations

import re
from pathlib import Path

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
