from __future__ import annotations

from collections.abc import Iterator

import pytest

from app import logs

SENTINEL = "SENTINEL-KEY-9f3a1c77"


@pytest.fixture(autouse=True)
def _clean_registry() -> Iterator[None]:
    logs.clear_secrets()
    yield
    logs.clear_secrets()


@pytest.mark.parametrize(
    "text",
    [
        f'{{"api_key": "{SENTINEL}"}}',
        f"{{'token':'{SENTINEL}'}}",
        f'"password": "{SENTINEL} with spaces"',
        f'payload {{"secret":"{SENTINEL}","x":1}}',
        f'{{"Authorization": "Basic {SENTINEL}"}}',
    ],
)
def test_quoted_keys_are_scrubbed(text: str) -> None:
    out = logs.scrub(text)
    assert SENTINEL not in out
    assert "with spaces" not in out


def test_short_registered_secret_is_scrubbed() -> None:
    logs.register_secret("abcde")
    assert "abcde" not in logs.scrub("x abcde y")
