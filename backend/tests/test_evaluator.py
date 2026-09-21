from app.services.evaluator import (
    get_user_bucket,
    match_condition,
    match_rule,
    evaluate_flag,
)


def test_sticky_bucket_determinism():
    """Ensure identical flag_key + user_id always yields the exact same bucket."""
    b1 = get_user_bucket("dark-mode", "user-456")
    b2 = get_user_bucket("dark-mode", "user-456")
    assert b1 == b2
    assert 0 <= b1 < 100


def test_kill_switch_overrides_everything():
    """When enabled=False (Emergency Kill Switch), always return default_value."""
    val, reason, _ = evaluate_flag(
        flag_key="checkout-v2",
        default_value=False,
        enabled=False,  # Emergency Kill Switch ON
        percentage=100,  # Even with 100% rollout
        rules=[{"conditions": [], "serve": True}],  # Even with matching rules
        user_id="user-123",
        attributes={"beta": True},
    )
    assert val is False
    assert reason == "KILL_SWITCH_ACTIVE"


def test_rule_targeting():
    """Targeted beta testing rule evaluation."""
    rules = [
        {
            "id": "rule-beta-users",
            "conditions": [
                {"attr": "email", "op": "ends_with", "value": "@company.com"}
            ],
            "serve": True,
        }
    ]

    # Matching user
    val, reason, rule_id = evaluate_flag(
        flag_key="ai-assistant",
        default_value=False,
        enabled=True,
        percentage=0,
        rules=rules,
        user_id="alice",
        attributes={"email": "alice@company.com"},
    )
    assert val is True
    assert reason == "RULE_MATCH"
    assert rule_id == "rule-beta-users"

    # Non-matching user
    val, reason, _ = evaluate_flag(
        flag_key="ai-assistant",
        default_value=False,
        enabled=True,
        percentage=0,
        rules=rules,
        user_id="bob",
        attributes={"email": "bob@gmail.com"},
    )
    assert val is False
    assert reason == "DEFAULT_VALUE"


def test_percentage_rollout_distribution():
    """Canary rollout: test that 50% rollout roughly covers half of 1,000 distinct users."""
    flag_key = "new-search-engine"
    evals = [
        evaluate_flag(
            flag_key=flag_key,
            default_value=False,
            enabled=True,
            percentage=50,
            rules=[],
            user_id=f"user_{i}",
            attributes={},
        )[0]
        for i in range(1000)
    ]
    served_true = sum(1 for e in evals if e is True)
    # Expect roughly ~500 (between 450 and 550)
    assert 450 <= served_true <= 550
