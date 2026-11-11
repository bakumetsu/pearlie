"""Tests for the rules engine: layers, order, versioned store."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.db import connect, init_db
from app.filters.baselist import BASE_LIST
from app.filters.rules import (
    RuleSet,
    StaleVersion,
    evaluate,
    load_rules,
    save_rules,
)


def _rs(**kw) -> RuleSet:
    """Build a RuleSet with defaults, overriding specified fields."""
    defaults: dict = {"version": 1, "reject": [], "warn": [], "require": [], "mapping": []}
    defaults.update(kw)
    return RuleSet(**defaults)


def test_reject_alone() -> None:
    """A matching reject rule produces a reject verdict; absence gives None."""
    rules = _rs(reject=["bad_tag"])
    v = evaluate({"general": ["bad_tag"]}, rules)
    assert v is not None
    assert v.decision == "reject"
    assert v.layer == "reject"
    assert v.rule == "bad_tag"
    assert evaluate({"general": ["clean"]}, rules) is None


def test_warn_alone() -> None:
    """A matching warn rule (no reject hit) produces a warn verdict."""
    rules = _rs(warn=["spooky"])
    v = evaluate({"general": ["spooky"]}, rules)
    assert v is not None
    assert v.decision == "warn"
    assert v.layer == "warn"


def test_require_missing_and_present() -> None:
    """Missing require tag yields require_missing; present tag passes."""
    rules = _rs(require=["good"])
    v = evaluate({"general": ["neutral"]}, rules)
    assert v is not None
    assert v.decision == "require_missing"
    assert v.layer == "require"
    assert evaluate({"general": ["good"]}, rules) is None


def test_base_list_beats_user_rules() -> None:
    """Base-list match wins even when user reject/warn/require exist."""
    base_tag = next(iter(BASE_LIST))
    rules = _rs(
        reject=["zzz_unrelated_1"],
        warn=["zzz_unrelated_2"],
        require=["zzz_unrelated_3"],
    )
    v = evaluate({"general": [base_tag]}, rules)
    assert v is not None
    assert v.layer == "base"


def test_order_reject_before_require_before_warn() -> None:
    """Priority order: reject > require_missing > warn."""
    rules = _rs(reject=["a"], require=["z"], warn=["b"])
    v = evaluate({"general": ["a", "b"]}, rules)
    assert v is not None
    assert v.layer == "reject"
    v = evaluate({"general": ["b"]}, rules)
    assert v is not None
    assert v.decision == "require_missing"
    v = evaluate({"general": ["z", "b"]}, rules)
    assert v is not None
    assert v.layer == "warn"


def test_normalization() -> None:
    """fold() normalises case/spaces/hyphens; scoped rules respect scope."""
    rules = _rs(reject=["Blue Sky"])
    assert evaluate({"general": ["blue-sky"]}, rules) is not None
    assert evaluate({"general": ["BLUE_SKY"]}, rules) is not None

    scoped = _rs(reject=["artist:x y"])
    assert evaluate({"artist": ["x_y"]}, scoped) is not None
    assert evaluate({"general": ["x_y"]}, scoped) is None

    bare = _rs(reject=["x_y"])
    assert evaluate({"general": ["x_y"]}, bare) is not None
    assert evaluate({"artist": ["x_y"]}, bare) is not None


def test_alias_in_base_list() -> None:
    """A base-list alias tag triggers a base-layer verdict with the alias set."""
    base_tag, alias = next((t, a[0]) for t, a in BASE_LIST.items() if a)
    v = evaluate({"general": [alias]}, _rs())
    assert v is not None
    assert v.layer == "base"
    assert v.alias == alias


def test_save_load_roundtrip(tmp_path: Path) -> None:
    """save_rules then load_rules round-trips all fields and bumps version."""
    db = tmp_path / "t.db"
    init_db(db)
    rs = load_rules(db)
    assert rs.version == 1
    assert rs.reject == []
    assert rs.warn == []
    assert rs.require == []
    assert rs.mapping == []

    new_rs = RuleSet(1, ["r", "artist:q"], ["w"], ["q"], [("artist:*", "stash_tag")])
    v = save_rules(db, 1, new_rs)
    assert v == 2

    loaded = load_rules(db)
    assert loaded.version == 2
    assert loaded.reject == ["r", "artist:q"]
    assert loaded.warn == ["w"]
    assert loaded.require == ["q"]
    assert loaded.mapping == [("artist:*", "stash_tag")]


def test_stale_version(tmp_path: Path) -> None:
    """Second save with stale version raises StaleVersion; state is preserved."""
    db = tmp_path / "t.db"
    init_db(db)
    save_rules(db, 1, _rs(reject=["first"]))
    with pytest.raises(StaleVersion):
        save_rules(db, 1, _rs(reject=["second"]))
    loaded = load_rules(db)
    assert loaded.reject == ["first"]
    assert loaded.version == 2


def test_existing_t05_reject_rows_still_load(tmp_path: Path) -> None:
    """Rows inserted directly with a scope load as scoped entries."""
    db = tmp_path / "t.db"
    init_db(db)
    conn = connect(db)
    conn.execute(
        "INSERT INTO rules (list, pattern, scope, enabled) VALUES ('reject','x','artist',1)"
    )
    conn.commit()
    conn.close()
    assert load_rules(db).reject == ["artist:x"]


def test_disabled_rows_ignored(tmp_path: Path) -> None:
    """Rows with enabled=0 are excluded from the loaded RuleSet."""
    db = tmp_path / "t.db"
    init_db(db)
    conn = connect(db)
    conn.execute(
        "INSERT INTO rules (list, pattern, scope, enabled) VALUES ('reject','off','general',0)"
    )
    conn.commit()
    conn.close()
    assert load_rules(db).reject == []
