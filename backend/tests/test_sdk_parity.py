"""
Differential parity tests between the server evaluator and the Python SDK.

The SDK re-implements evaluation locally so that ``is_enabled()`` never touches
the network. That is only safe if the local implementation is *provably*
identical to ``app/services/evaluator.py`` on the server. These tests drive both
implementations with the same generated inputs and require identical results.

They live in the backend suite because that is where ``app`` and ``mmh3`` are
already available; the SDK itself is imported straight from source, so there is
no publish step between the two sides of the comparison.
"""

import os
import random
import sys
from typing import Any, Dict, List

import pytest

SDK_SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "packages",
    "catalyst-python-sdk",
    "src",
)
if SDK_SRC not in sys.path:
    sys.path.insert(0, SDK_SRC)

from app.services import evaluator as server  # noqa: E402
from catalyst_sdk import evaluator as sdk  # noqa: E402
from catalyst_sdk.snapshot import Snapshot  # noqa: E402


# ---------------------------------------------------------------------------
# Bucketing
# ---------------------------------------------------------------------------
def test_user_bucket_matches_the_server():
    """Murmur3 parity is what makes sticky rollouts agree across platforms."""
    for i in range(5000):
        flag_key = random.choice(["ai-assistant", "new-checkout", "f", "x" * 40])
        user_id = random.choice([f"user_{i}", f"u{i}", "alice@acme.com", "", "éü"])
        assert sdk.get_user_bucket(flag_key, user_id) == server.get_user_bucket(flag_key, user_id)


def test_operator_normalization_matches_the_server():
    for op in [
        "equals", "eq", "EQ", "neq", "gt", "gte", "lt", "lte",
        "notExists", "exists", "not_exists", "in", "not_in", "contains",
        "starts_with", "ends_with", "less_than", None, "garbage",
    ]:
        assert sdk.normalize_operator(op) == server.normalize_operator(op)


# ---------------------------------------------------------------------------
# Condition matching
# ---------------------------------------------------------------------------
VALUES: List[Any] = [
    None, True, False, 0, 1, 10, 3.5, -2, "", "pro", "free", "@acme.com",
    "a@acme.com", ["pro", "team"], ["free"], "pro, team", "abc", "3.2", 100,
]
ATTRS = ["plan", "email", "seats", "beta", "app_version", "missing_attr"]
OPS = list(server.RULE_OPERATORS)


@pytest.mark.parametrize("op", OPS)
def test_condition_matching_matches_the_server_for_every_operator(op):
    for attr in ATTRS:
        for value in VALUES:
            for attributes in (
                {attr: "pro"},
                {attr: 10},
                {attr: True},
                {attr: "@acme.com"},
                {attr: "3.2.1"},
                {attr: ["pro", "free"]},
                {},
            ):
                condition = {"attr": attr, "op": op, "value": value}
                assert sdk.match_condition(
                    sdk.Condition.from_dict(condition), attributes
                ) == server.match_condition(condition, attributes), (
                    f"divergence for {condition} against {attributes}"
                )


# ---------------------------------------------------------------------------
# Whole-flag evaluation
# ---------------------------------------------------------------------------
def _random_condition() -> Dict[str, Any]:
    return {
        "attr": random.choice(ATTRS),
        "op": random.choice(OPS),
        "value": random.choice(VALUES),
    }


def _random_rules() -> List[Dict[str, Any]]:
    rules = []
    for index in range(random.randint(0, 4)):
        rules.append(
            {
                "id": f"rule-{index}",
                # Deliberately out of order: the SDK must sort by priority.
                "priority": random.randint(0, 5),
                "conditions": [_random_condition() for _ in range(random.randint(1, 3))],
                "serve": random.choice([True, False]),
            }
        )
    return rules


def _random_attributes() -> Dict[str, Any]:
    attributes: Dict[str, Any] = {}
    for attr in random.sample(ATTRS, random.randint(0, len(ATTRS))):
        attributes[attr] = random.choice(
            ["pro", "free", "team", 10, 3, 0, True, False, "@acme.com",
             "a@acme.com", "3.2.1", ["pro", "free"], "3.2"]
        )
    return attributes


def test_flag_evaluation_matches_the_server_across_fuzzed_inputs():
    """
    Fuzzes whole-flag evaluation and requires the SDK and server to agree on
    the served value, the reason, and the matched rule id.
    """
    random.seed(1337)
    for _ in range(3000):
        rules = _random_rules()
        attributes = _random_attributes()
        user_id = random.choice(["user_1", "u42", "alice@acme.com", ""])
        default_value = random.choice([True, False])
        enabled = random.choice([True, False])
        percentage = random.choice([0, 1, 25, 50, 99, 100])

        expected_value, expected_reason, expected_rule = server.evaluate_flag(
            flag_key="ai-assistant",
            default_value=default_value,
            enabled=enabled,
            percentage=percentage,
            rules=rules,
            user_id=user_id,
            attributes=attributes,
        )

        actual = sdk.evaluate_flag(
            flag_key="ai-assistant",
            default_value=default_value,
            enabled=enabled,
            percentage=percentage,
            rules=[sdk.Rule.from_dict(rule) for rule in rules],
            user_id=user_id,
            attributes=attributes,
        )

        assert actual.value == expected_value, (rules, attributes, user_id)
        assert actual.reason == expected_reason, (rules, attributes, user_id)
        assert actual.rule_id == expected_rule, (rules, attributes, user_id)


def test_sdk_reads_the_bootstrap_payload_shape():
    """
    Guards the wire contract: the SDK must parse the exact ``/bootstrap`` body
    the server emits, including camelCase ``defaultValue`` and rule conditions.
    """
    payload = {
        "env": "prod",
        "version": 3,
        "flags": {
            "ai-assistant": {
                "key": "ai-assistant",
                "defaultValue": True,
                "enabled": True,
                "percentage": 25,
                "rules": [
                    {
                        "id": "r1",
                        "priority": 0,
                        "serve": True,
                        "conditions": [{"attr": "email", "op": "ends_with", "value": "@acme.com"}],
                    }
                ],
            }
        },
    }
    snapshot = Snapshot.from_payload(payload, etag='W/"p:prod:3"')
    flag = snapshot.get("ai-assistant")
    assert flag is not None
    assert flag.default_value is True
    assert flag.enabled is True
    assert flag.percentage == 25
    assert flag.version == 3
    assert [rule.id for rule in flag.rules] == ["r1"]
    assert flag.rules[0].serve is True
    assert flag.rules[0].conditions[0].op == "ends_with"
    assert flag.rules[0].conditions[0].value == "@acme.com"
    # A matching context is served True by the kill switch being off.
    result = sdk.evaluate_flag(
        flag_key="ai-assistant",
        default_value=flag.default_value,
        enabled=flag.enabled,
        percentage=flag.percentage,
        rules=flag.rules,
        user_id="user_1",
        attributes={"email": "dev@acme.com"},
    )
    assert result.value is True
    assert result.rule_id == "r1"
