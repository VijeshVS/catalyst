from typing import Any, Dict, List, Optional, Tuple
import mmh3


def get_user_bucket(flag_key: str, user_id: str) -> int:
    """
    Computes a deterministic sticky bucket from 0 to 99 using MurmurHash3.
    Identical across SDKs (Python, JS) to guarantee evaluation consistency.
    """
    raw_hash = mmh3.hash(f"{flag_key}:{user_id}")
    return (raw_hash & 0xFFFFFFFF) % 100


def match_condition(condition: Dict[str, Any], attributes: Dict[str, Any]) -> bool:
    """
    Evaluates a single condition against the context attributes.
    Condition format: {"attr": "email", "op": "ends_with", "value": "@company.com"}
    """
    attr_name = condition.get("attr")
    op = condition.get("op", "equals").lower()
    target_value = condition.get("value")

    if not attr_name or attr_name not in attributes:
        return False

    actual_value = attributes[attr_name]

    try:
        if op in ("equals", "eq"):
            return actual_value == target_value
        elif op in ("not_equals", "neq"):
            return actual_value != target_value
        elif op == "in":
            if isinstance(target_value, list):
                return actual_value in target_value
            return str(actual_value) in [x.strip() for x in str(target_value).split(",")]
        elif op == "not_in":
            if isinstance(target_value, list):
                return actual_value not in target_value
            return str(actual_value) not in [x.strip() for x in str(target_value).split(",")]
        elif op == "contains":
            return str(target_value).lower() in str(actual_value).lower()
        elif op == "starts_with":
            return str(actual_value).lower().startswith(str(target_value).lower())
        elif op == "ends_with":
            return str(actual_value).lower().endswith(str(target_value).lower())
        elif op in ("greater_than", "gt"):
            return float(actual_value) > float(target_value)
        elif op in ("greater_than_or_equal", "gte"):
            return float(actual_value) >= float(target_value)
        elif op in ("less_than", "lt"):
            return float(actual_value) < float(target_value)
        elif op in ("less_than_or_equal", "lte"):
            return float(actual_value) <= float(target_value)
    except (ValueError, TypeError):
        return False

    return False


def match_rule(rule_conditions: List[Dict[str, Any]], attributes: Dict[str, Any]) -> bool:
    """
    A rule matches if ALL conditions match (AND logic).
    """
    if not rule_conditions:
        return True
    return all(match_condition(cond, attributes) for cond in rule_conditions)


def evaluate_flag(
    flag_key: str,
    default_value: bool,
    enabled: bool,
    percentage: int,
    rules: List[Dict[str, Any]],
    user_id: str,
    attributes: Dict[str, Any],
) -> Tuple[bool, str, Optional[str]]:
    """
    Evaluates a flag given its state and rules.
    Returns: (served_value, reason, matched_rule_id)
    """
    # 1. Emergency Kill Switch check
    if not enabled:
        return default_value, "KILL_SWITCH_ACTIVE", None

    # 2. Check targeting rules (sorted by priority)
    for rule in rules:
        conditions = rule.get("conditions", [])
        if match_rule(conditions, attributes):
            return rule.get("serve", True), "RULE_MATCH", rule.get("id")

    # 3. Gradual / Canary % Rollout check
    if percentage > 0:
        bucket = get_user_bucket(flag_key, user_id)
        if bucket < percentage:
            return True, "PERCENTAGE_ROLLOUT", None

    # 4. Fallback to flag default
    return default_value, "DEFAULT_VALUE", None
