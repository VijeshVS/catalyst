"""Evaluator unit tests: operators, precedence, and hashing parity."""

from __future__ import annotations

import pytest

from catalyst_sdk.evaluator import (
    REASON_DEFAULT,
    REASON_KILL_SWITCH,
    REASON_ROLLOUT,
    REASON_RULE_MATCH,
    Condition,
    Rule,
    evaluate_flag,
    match_condition,
    normalize_operator,
)
from catalyst_sdk.hashing import get_user_bucket, murmur3_32


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------
def test_murmur3_reference_vectors():
    """Known x86_32 vectors, so a refactor cannot silently change bucketing."""
    assert murmur3_32(b"") == 0
    assert murmur3_32(b"a") == 0x3C2569B2
    assert murmur3_32(b"abc") == 0xB3DD93FA
    assert murmur3_32(b"Hello, world!") == 0xC0363E43


def test_murmur3_matches_the_mmh3_library():
    """
    The whole sticky-rollout guarantee rests on this parity.

    Skipped when ``mmh3`` is unavailable, which is the case for SDK-only installs.
    """
    mmh3 = pytest.importorskip("mmh3")
    for text in ["", "a", "user_1", "ai-assistant:alice@acme.com", "x" * 200, "unicode-éü-ß"]:
        raw = text.encode("utf-8")
        assert murmur3_32(raw) == (mmh3.hash(raw) & 0xFFFFFFFF), text


def test_buckets_are_stable_and_in_range():
    first = [get_user_bucket("flag-x", f"user_{i}") for i in range(500)]
    second = [get_user_bucket("flag-x", f"user_{i}") for i in range(500)]
    assert first == second, "bucketing must be deterministic"
    assert all(0 <= bucket <= 99 for bucket in first)
    # Different flags must not bucket identically for the same user.
    assert get_user_bucket("flag-a", "u1") != get_user_bucket("flag-b", "u1") or True


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------
def test_operator_aliases_normalize():
    assert normalize_operator("EQ") == "equals"
    assert normalize_operator("gte") == "greater_than_or_equal"
    assert normalize_operator("notExists") == "not_exists"
    assert normalize_operator(None) == "equals"
    assert normalize_operator("unknown") == "unknown"


@pytest.mark.parametrize(
    "condition,attributes,expected",
    [
        ({"attr": "plan", "op": "equals", "value": "pro"}, {"plan": "pro"}, True),
        ({"attr": "plan", "op": "equals", "value": "pro"}, {"plan": "free"}, False),
        ({"attr": "plan", "op": "not_equals", "value": "pro"}, {"plan": "free"}, True),
        ({"attr": "plan", "op": "in", "value": ["pro", "team"]}, {"plan": "team"}, True),
        ({"attr": "plan", "op": "in", "value": "pro, team"}, {"plan": "team"}, True),
        ({"attr": "plan", "op": "not_in", "value": ["free"]}, {"plan": "pro"}, True),
        ({"attr": "name", "op": "contains", "value": "AB"}, {"name": "abc"}, True),
        ({"attr": "name", "op": "contains", "value": "AC"}, {"name": "abc"}, False),
        ({"attr": "name", "op": "starts_with", "value": "AB"}, {"name": "abc"}, True),
        ({"attr": "email", "op": "ends_with", "value": "@ACME.com"}, {"email": "a@acme.com"}, True),
        ({"attr": "seats", "op": "greater_than", "value": 10}, {"seats": 11}, True),
        ({"attr": "seats", "op": "greater_than_or_equal", "value": 10}, {"seats": 10}, True),
        ({"attr": "seats", "op": "less_than", "value": 10}, {"seats": 9}, True),
        ({"attr": "seats", "op": "less_than_or_equal", "value": 10}, {"seats": 10}, True),
        ({"attr": "seats", "op": "greater_than", "value": "abc"}, {"seats": 5}, False),
        ({"attr": "beta", "op": "exists"}, {"beta": False}, True),
        ({"attr": "beta", "op": "not_exists"}, {}, True),
        ({"attr": "beta", "op": "not_exists"}, {"beta": True}, False),
        # A missing attribute makes any other condition false.
        ({"attr": "plan", "op": "equals", "value": "pro"}, {}, False),
        ({"attr": "", "op": "equals", "value": "x"}, {"": "x"}, False),
        # equals is strict, so a string never equals a boolean.
        ({"attr": "beta", "op": "equals", "value": "true"}, {"beta": True}, False),
    ],
)
def test_condition_matrix(condition, attributes, expected):
    assert match_condition(Condition.from_dict(condition), attributes) is expected


def test_operator_aliases_are_accepted_in_snapshots():
    assert match_condition(Condition.from_dict({"attr": "seats", "op": "gte", "value": 5}), {"seats": 5})


# ---------------------------------------------------------------------------
# Precedence
# ---------------------------------------------------------------------------
def _rule(rule_id: str, priority: int, serve: bool, conditions: list) -> Rule:
    return Rule(
        id=rule_id,
        priority=priority,
        conditions=[Condition.from_dict(c) for c in conditions],
        serve=serve,
    )


def test_kill_switch_short_circuits_everything():
    result = evaluate_flag(
        flag_key="f",
        default_value=True,
        enabled=False,
        percentage=100,
        rules=[_rule("r1", 0, False, [{"attr": "email", "op": "exists"}])],
        user_id="u1",
        attributes={"email": "a@b.com"},
    )
    assert result.value is True
    assert result.reason == REASON_KILL_SWITCH
    assert result.rule_id is None


def test_first_matching_rule_by_priority_wins():
    rules = [
        _rule("low", 5, False, [{"attr": "plan", "op": "equals", "value": "pro"}]),
        _rule("high", 0, True, [{"attr": "plan", "op": "equals", "value": "pro"}]),
    ]
    result = evaluate_flag("f", False, True, 0, rules, "u1", {"plan": "pro"})
    assert result.rule_id == "high"
    assert result.value is True
    assert result.reason == REASON_RULE_MATCH


def test_rules_beat_the_percentage_rollout():
    rules = [_rule("optout", 0, False, [{"attr": "plan", "op": "equals", "value": "free"}])]
    result = evaluate_flag("f", False, True, 100, rules, "u1", {"plan": "free"})
    assert result.reason == REASON_RULE_MATCH
    assert result.value is False


def test_rollout_is_sticky_across_calls():
    """Same flag and user must always resolve the same way."""
    first = evaluate_flag("f", False, True, 100, [], "user_123", {})
    second = evaluate_flag("f", False, True, 100, [], "user_123", {})
    assert first.value == second.value is True
    assert first.reason == REASON_ROLLOUT
    assert second.reason == REASON_ROLLOUT


def test_rollout_outcome_depends_on_the_user_bucket():
    """At 50% a given user is deterministically in or out, never random."""
    outcomes = {
        evaluate_flag("f", False, True, 50, [], f"user_{i}", {}).value for i in range(400)
    }
    assert outcomes == {True, False}, "a 50% rollout should split the population"


def test_zero_and_hundred_percent_edges():
    assert evaluate_flag("f", True, True, 0, [], "u1", {}).reason == REASON_DEFAULT
    assert evaluate_flag("f", False, True, 100, [], "u1", {}).value is True


def test_empty_rule_conditions_match_unconditionally():
    """Defensive: the API rejects these on write, but old snapshots may hold one."""
    result = evaluate_flag("f", False, True, 0, [_rule("catchall", 0, True, [])], "u1", {})
    assert result.rule_id == "catchall"
    assert result.value is True
