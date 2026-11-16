import json
from pathlib import Path

import pytest

from app.sources.query_terms import (
    Title,
    is_reserved,
    parse_title,
    split_terms,
    title_terms,
)

ROWS = json.loads((Path(__file__).parent / "data" / "query_terms.json").read_text("utf-8"))


@pytest.mark.parametrize("row", ROWS, ids=[r["text"] or "empty" for r in ROWS])
def test_split_terms_shared_table(row):
    assert split_terms(row["text"]) == row["tokens"]


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ('"big dragon"', Title("big dragon")),
        ('title:"big dragon"', Title("big dragon")),
        ("title:foo_bar", Title("foo_bar")),
        ('-title:"x y"', Title("x y", True)),
        ('-"x"', Title("x", True)),
        ('"big dragon', Title("big dragon")),
        ('title:"a"b"', Title("ab")),
        ('title:""', None),
        ("title:", None),
        ("cat", None),
        ("artist:x", None),
    ],
)
def test_parse_title(token, expected):
    assert parse_title(token) == expected


def test_parse_title_cut_at_200():
    t = parse_title("title:" + "a" * 300)
    assert t is not None
    assert len(t.value) == 200


def test_title_terms_split_and_dedupe():
    titles, others = title_terms(split_terms('cat "a b" title:"a b" -title:c artist:x title:'))
    assert [t.token for t in titles] == ['title:"a b"', '-title:"c"']
    assert others == ["cat", "artist:x"]


def test_is_reserved():
    assert is_reserved("title:x")
    assert is_reserved("-ID:5")
    assert not is_reserved("artist:x")
    assert not is_reserved("titles")
