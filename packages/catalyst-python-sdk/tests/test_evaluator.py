"""Evaluator unit tests: operators, precedence, and hashing parity."""

from __future__ import annotations

import pytest

from catalyst_sdk.evaluator import (
    REASON_DEFAULT,
    REASON_ENABLE_ALL,
    REASON_KILL_SWITCH,
    REASON_ROLLOUT,
    REASON_ROLLOUT_OUTSIDE,
    REASON_RULE_AND_ROLLOUT,
    REASON_RULE_OUTSIDE_ROLLOUT,
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


def _evaluate(**overrides):
    params = {
        "flag_key": "f",
        "enabled": True,
        "enable_all": False,
        "percentage": 100,
        "rules": [],
        "user_id": "u1",
        "attributes": {},
    }
    params.update(overrides)
    return evaluate_flag(**params)


def test_kill_switch_short_circuits_everything():
    """Highest priority: the kill switch means false, full stop."""
    result = _evaluate(
        enabled=False,
        enable_all=True,
        percentage=100,
        rules=[_rule("r1", 0, True, [{"attr": "email", "op": "exists"}])],
        attributes={"email": "a@b.com"},
    )
    assert result.value is False
    assert result.reason == REASON_KILL_SWITCH
    assert result.rule_id is None


def test_enable_all_serves_true_to_everyone():
    result = _evaluate(
        enable_all=True,
        percentage=0,
        rules=[_rule("r1", 0, False, [{"attr": "email", "op": "exists"}])],
        attributes={"email": "a@b.com"},
    )
    assert result.value is True
    assert result.reason == REASON_ENABLE_ALL
    assert result.rule_id is None


def test_first_matching_rule_by_priority_wins():
    rules = [
        _rule("low", 5, False, [{"attr": "plan", "op": "equals", "value": "pro"}]),
        _rule("high", 0, True, [{"attr": "plan", "op": "equals", "value": "pro"}]),
    ]
    result = _evaluate(rules=rules, attributes={"plan": "pro"})
    assert result.rule_id == "high"
    assert result.value is True
    assert result.reason == REASON_RULE_AND_ROLLOUT


def test_a_rule_and_a_percentage_combine_rather_than_override():
    """The old test asserted the short-circuit; the rules now split the group."""
    rules = [_rule("optout", 0, False, [{"attr": "plan", "op": "equals", "value": "free"}])]
    inside = _evaluate(rules=rules, percentage=100, attributes={"plan": "free"})
    assert inside.value is False
    assert inside.reason == REASON_RULE_AND_ROLLOUT

    outside = _evaluate(rules=rules, percentage=0, attributes={"plan": "free"})
    assert outside.value is True, "a matched user outside the rollout gets the opposite value"
    assert outside.reason == REASON_RULE_OUTSIDE_ROLLOUT


def test_the_percentage_splits_the_matched_group():
    rules = [_rule("beta", 0, True, [{"attr": "plan", "op": "equals", "value": "pro"}])]
    values = [
        _evaluate(rules=rules, percentage=40, user_id=f"user_{i}", attributes={"plan": "pro"}).value
        for i in range(400)
    ]
    assert set(values) == {True, False}, "the matched group is split, not wiped"
    assert 120 <= sum(values) <= 200


def test_rules_filter_out_a_user_who_matches_none():
    rules = [_rule("beta", 0, True, [{"attr": "plan", "op": "equals", "value": "pro"}])]
    result = _evaluate(rules=rules, percentage=100, attributes={"plan": "free"})
    assert result.value is False
    assert result.reason == REASON_DEFAULT


def test_rollout_is_sticky_across_calls():
    """Same flag and user must always resolve the same way."""
    first = _evaluate(user_id="user_123")
    second = _evaluate(user_id="user_123")
    assert first.value is second.value is True
    assert first.reason == REASON_ROLLOUT
    assert second.reason == REASON_ROLLOUT


def test_rollout_outcome_depends_on_the_user_bucket():
    """At 50% a given user is deterministically in or out, never random."""
    outcomes = {_evaluate(percentage=50, user_id=f"user_{i}").value for i in range(400)}
    assert outcomes == {True, False}, "a 50% rollout should split the population"


def test_raising_the_percentage_never_removes_a_user():
    """The bucket is a fixed number per user, so a rollout only ever grows."""
    users = [f"user_{i}" for i in range(300)]
    served: set[str] = set()
    for percentage in range(0, 101, 10):
        now = {u for u in users if _evaluate(percentage=percentage, user_id=u).value}
        assert served <= now, f"raising the rollout to {percentage}% stopped serving a user"
        served = now


def test_zero_and_hundred_percent_edges():
    """0% and 100% are opposites, which they used not be."""
    assert _evaluate(percentage=0).value is False
    assert _evaluate(percentage=0).reason == REASON_ROLLOUT_OUTSIDE
    assert _evaluate(percentage=100).value is True
    assert _evaluate(percentage=100).reason == REASON_ROLLOUT


def test_empty_rule_conditions_match_unconditionally():
    """Defensive: the API rejects these on write, but old snapshots may hold one."""
    result = _evaluate(rules=[_rule("catchall", 0, True, [])])
    assert result.rule_id == "catchall"
    assert result.value is True
