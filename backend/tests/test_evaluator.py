"""
Tests for the evaluation decision table.

The table is the specification; each test is one row of it. Before this rework
a matching rule short-circuited the percentage entirely, and 0% and 100%
behaved identically. Both are now covered explicitly.
"""

import pytest

from app.services.evaluator import evaluate_flag, get_user_bucket


def evaluate(**overrides):
    """Evaluates a flag with sane defaults for anything the test does not care about."""
    params = {
        "flag_key": "checkout-v2",
        "enabled": True,
        "enable_all": False,
        "percentage": 100,
        "rules": [],
        "user_id": "user-123",
        "attributes": {},
    }
    params.update(overrides)
    return evaluate_flag(**params)


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------
def test_sticky_bucket_determinism():
    """Identical flag_key + user_id always yields the exact same bucket."""
    b1 = get_user_bucket("dark-mode", "user-456")
    b2 = get_user_bucket("dark-mode", "user-456")
    assert b1 == b2
    assert 0 <= b1 < 100


# ---------------------------------------------------------------------------
# Row 1: kill switch ON wins over everything
# ---------------------------------------------------------------------------
def test_kill_switch_serves_false_to_everyone():
    """Nothing else is even looked at, so every other setting is irrelevant."""
    for percentage in (0, 50, 100):
        for enable_all in (False, True):
            val, reason, rule_id = evaluate(
                enabled=False,
                enable_all=enable_all,
                percentage=percentage,
                rules=[{"id": "r1", "conditions": [], "serve": True}],
            )
            assert val is False
            assert reason == "KILL_SWITCH_ACTIVE"
            assert rule_id is None


# ---------------------------------------------------------------------------
# Row 2: enable to all users, with the kill switch off
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("percentage", [0, 37, 100])
def test_enable_all_serves_true_to_everyone(percentage):
    """No rules, no percentage, nothing. This switch bypasses all targeting."""
    val, reason, rule_id = evaluate(
        enable_all=True,
        percentage=percentage,
        rules=[
            {"id": "r1", "conditions": [{"attr": "email", "op": "exists"}], "serve": False},
        ],
        attributes={"email": "a@b.com"},
    )
    assert val is True
    assert reason == "ENABLE_ALL_USERS"
    assert rule_id is None


def test_enable_all_serves_true_even_with_no_rules_at_all():
    val, reason, _ = evaluate(enable_all=True, percentage=0, rules=[])
    assert val is True
    assert reason == "ENABLE_ALL_USERS"


# ---------------------------------------------------------------------------
# Rows 3-5: no rules, percentage only
# ---------------------------------------------------------------------------
def test_percentage_100_serves_everybody():
    values = [evaluate(percentage=100, user_id=f"user-{i}")[0] for i in range(200)]
    assert all(values)


def test_percentage_0_serves_nobody():
    values = [evaluate(percentage=0, user_id=f"user-{i}")[0] for i in range(200)]
    assert not any(values)


def test_percentage_0_has_its_own_reason():
    _, reason, _ = evaluate(percentage=0)
    assert reason == "PERCENTAGE_OUTSIDE_ROLLOUT", "0% used to be indistinguishable from 100%"


def test_percentage_50_serves_about_half():
    evals = [evaluate(percentage=50, user_id=f"user_{i}")[0] for i in range(1000)]
    served_true = sum(1 for value in evals if value)
    assert 450 <= served_true <= 550


def test_percentage_is_sticky_for_one_user():
    first = evaluate(percentage=37, user_id="user-abc")[0]
    for _ in range(1000):
        assert evaluate(percentage=37, user_id="user-abc")[0] == first


def test_raising_the_percentage_never_removes_a_user():
    """The bucket is a fixed number per user, so a rollout only ever grows."""
    users = [f"user_{i}" for i in range(500)]
    previously_served = set()

    for percentage in range(0, 101, 10):
        now_served = {
            user for user in users if evaluate(percentage=percentage, user_id=user)[0]
        }
        assert previously_served <= now_served, (
            f"raising the rollout to {percentage}% stopped serving a user"
        )
        previously_served = now_served

    assert len(previously_served) > 0


# ---------------------------------------------------------------------------
# Rows 6-7: a rule matched
# ---------------------------------------------------------------------------
BETA_RULE = [
    {
        "id": "rule-beta",
        "conditions": [{"attr": "email", "op": "ends_with", "value": "@company.com"}],
        "serve": True,
    }
]


def test_matched_rule_serves_its_value_at_full_rollout():
    val, reason, rule_id = evaluate(
        percentage=100,
        rules=BETA_RULE,
        user_id="alice",
        attributes={"email": "alice@company.com"},
    )
    assert val is True
    assert reason == "RULE_AND_ROLLOUT"
    assert rule_id == "rule-beta"


def test_matched_rule_can_serve_false():
    val, reason, rule_id = evaluate(
        percentage=100,
        rules=[{"id": "r1", "conditions": [], "serve": False}],
    )
    assert val is False
    assert reason == "RULE_AND_ROLLOUT"
    assert rule_id == "r1"


def test_the_percentage_splits_the_matched_group():
    """A matching rule and a percentage combine instead of one overriding the other."""
    users = [f"user_{i}" for i in range(400)]
    served_true = [
        user
        for user in users
        if evaluate(
            percentage=40,
            rules=BETA_RULE,
            user_id=user,
            attributes={"email": f"{user}@company.com"},
        )[0]
    ]
    assert 120 <= len(served_true) <= 200, "roughly 40% of the matched users"


def test_matched_users_outside_the_rollout_get_the_opposite_value():
    """The two outcomes still partition the matched group exactly."""
    users = [f"user_{i}" for i in range(400)]
    outcomes = [
        evaluate(
            percentage=40,
            rules=[{"id": "r1", "conditions": [], "serve": True}],
            user_id=user,
        )[0]
        for user in users
    ]
    assert any(outcomes), "the matched group is split, not wiped"
    assert not all(outcomes), "the matched group is split, not universal"

    # And the reason distinguishes the two halves.
    reasons = {
        evaluate(
            percentage=40,
            rules=[{"id": "r1", "conditions": [], "serve": True}],
            user_id=user,
        )[1]
        for user in users
    }
    assert reasons == {"RULE_AND_ROLLOUT", "RULE_OUTSIDE_ROLLOUT"}


def test_first_match_by_priority_wins():
    rules = [
        {"id": "low", "priority": 5, "conditions": [], "serve": False},
        {"id": "high", "priority": 0, "conditions": [], "serve": True},
    ]
    _, reason, rule_id = evaluate(percentage=100, rules=rules)
    assert (reason, rule_id) == ("RULE_AND_ROLLOUT", "high")


# ---------------------------------------------------------------------------
# Row 8: rules exist and none matched, so the user is filtered out
# ---------------------------------------------------------------------------
def test_no_rule_match_serves_nobody_whatever_the_percentage():
    for percentage in (0, 50, 100):
        val, reason, _ = evaluate(
            percentage=percentage,
            rules=BETA_RULE,
            user_id="bob",
            attributes={"email": "bob@gmail.com"},
        )
        assert val is False, f"a filtered-out user got served at {percentage}%"
        assert reason == "DEFAULT_VALUE"


def test_filtered_out_reason_differs_from_being_outside_the_rollout():
    """An operator must be able to tell "no rule matched" from "outside the %"."""
    filtered = evaluate(
        percentage=100, rules=BETA_RULE, user_id="bob", attributes={"email": "b@x.com"}
    )[1]
    outside = evaluate(percentage=0, rules=[], user_id="bob")[1]
    assert filtered == "DEFAULT_VALUE"
    assert outside == "PERCENTAGE_OUTSIDE_ROLLOUT"
    assert filtered != outside


# ---------------------------------------------------------------------------
# Reasons
# ---------------------------------------------------------------------------
def test_every_reason_is_distinguishable():
    """The seven reasons an operator can be shown, each reachable and distinct."""
    seen = {
        evaluate(enabled=False)[1],
        evaluate(enable_all=True)[1],
        evaluate(percentage=100)[1],
        evaluate(percentage=0)[1],
        evaluate(percentage=100, rules=BETA_RULE, attributes={"email": "a@company.com"})[1],
        evaluate(percentage=0, rules=BETA_RULE, attributes={"email": "a@company.com"})[1],
        evaluate(percentage=100, rules=BETA_RULE, attributes={"email": "a@other.com"})[1],
    }
    assert seen == {
        "KILL_SWITCH_ACTIVE",
        "ENABLE_ALL_USERS",
        "PERCENTAGE_ROLLOUT",
        "PERCENTAGE_OUTSIDE_ROLLOUT",
        "RULE_AND_ROLLOUT",
        "RULE_OUTSIDE_ROLLOUT",
        "DEFAULT_VALUE",
    }
    assert "RULE_MATCH" not in seen, "the old short-circuit reason is gone"
