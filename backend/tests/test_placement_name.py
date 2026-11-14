"""Tests for placement_name.parse_name."""

from __future__ import annotations

import pytest

from app.targets.placement_name import parse_name

CASES = [
    # (title, artists, hardened, author, root, number, is_series)
    ("[Kisaragi] Love 2 (Original) [English]", (), True, "[Kisaragi]", "Love", "2", True),
    ("[Kisaragi] Love (Original) [English]", (), True, "[Kisaragi]", "Love", "", False),
    ("[Kisaragi] Love 3 [English] [Digital]", (), True, "[Kisaragi]", "Love", "3", True),
    (
        "[Mizuki] What I Did Last Summer [English]",
        (),
        True,
        "[Mizuki]",
        "What I Did Last Summer",
        "",
        False,
    ),
    ("[Mizuki] What I Did Last Summer [English]", (), False, "[Mizuki]", "What", "1", True),
    (
        "[Nanao] Fate Grand Order 2025 [English]",
        (),
        True,
        "[Nanao]",
        "Fate Grand Order 2025",
        "",
        False,
    ),
    (
        "[Nanao] Fate Grand Order 2025 [English]",
        (),
        False,
        "[Nanao]",
        "Fate Grand Order",
        "2025",
        True,
    ),
    ("[Nanao] Sailor Moon 3D [English]", (), True, "[Nanao]", "Sailor Moon 3D", "", False),
    ("My Sister Vol. 2 [English]", (), True, "", "My Sister", "2", True),
    ("My Sister #3", (), True, "", "My Sister", "3", True),
    ("My Sister Chapter 12 - The Beach", (), True, "", "My Sister", "12", True),
    ("My Sister - 4", (), True, "", "My Sister", "4", True),
    ("My Sister II", (), True, "", "My Sister", "2", True),
    ("My Sister 1.5", (), True, "", "My Sister", "1.5", True),
    ("My Sister Returns", (), True, "", "My Sister Returns", "", False),
    ("Dark Room ~Extra~", (), True, "", "Dark Room", "", False),
    ("No Game No Life", (), True, "", "No Game No Life", "", False),
    ("Part Time Lover", (), True, "", "Part Time Lover", "", False),
    ("Love 2 You", (), True, "", "Love 2 You", "", False),
    ("Love 2 You", (), False, "", "Love", "2", True),
    ("Love Hotel 3 (Original) [Digital]", (), True, "", "Love Hotel", "3", True),
    ("[Foo] Love 2 [TeamX] (Original)", (), True, "[Foo]", "Love", "2", True),
    ("[Foo] Love (Original) [English] [TeamX] [Digital]", (), True, "[Foo]", "Love", "", False),
    ("Some Title without author 2", (), True, "", "Some Title without author", "2", True),
    ("Some Title 2", ["Kisaragi"], True, "[Kisaragi]", "Some Title", "2", True),
    ("[Kisaragi] Love 4 [English]", (), True, "[Kisaragi]", "Love", "4", True),
    ("[Ao:ki] Who? 2 [English]", (), True, "[Ao:ki]", "Who?", "2", True),
    ("[Foo] ... 3 [English]", (), True, "[Foo]", "...", "3", True),
    ("[Foo] [English]", ["Zed"], True, "[Zed]", "Unknown_Title", "", False),
    ("[Circle (Artist)] Title 2", (), True, "[Circle (Artist)]", "Title", "2", True),
    ("X 1899", (), True, "", "X", "1899", True),
    ("X 2100", (), True, "", "X", "2100", True),
]


@pytest.mark.parametrize(
    ("title", "artists", "hardened", "author", "root", "number", "is_series"),
    CASES,
    ids=[c[0] + (f" hardened={c[2]}" if c[2] is False else "") for c in CASES],
)
def test_parse_name(title, artists, hardened, author, root, number, is_series):
    result = parse_name(title, artists, hardened)
    assert result.author == author
    assert result.root == root
    assert result.number == number
    assert result.is_series is is_series


def test_cut_uses_earliest_separator() -> None:
    assert parse_name("A 〜 B ~ C").root == "A"


def test_year_after_dash_is_not_a_volume() -> None:
    assert not parse_name("Fate - 2025").is_series
    assert parse_name("Fate - 2025", hardened=False).is_series
