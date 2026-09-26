from typing import Any, Dict, List, Optional, Tuple
import mmh3


#: Canonical condition operators. Aliases are accepted on read (see
#: ``OPERATOR_ALIASES``) but every condition written through the API is
#: normalized to one of these names so snapshots stay stable across SDKs.
RULE_OPERATORS: Tuple[str, ...] = (
    "equals",
    "not_equals",
    "in",
    "not_in",
    "contains",
    "starts_with",
    "ends_with",
    "greater_than",
    "greater_than_or_equal",
    "less_than",
    "less_than_or_equal",
    "exists",
    "not_exists",
)

#: Operators that inspect attribute presence only; their ``value`` is ignored.
PRESENCE_OPERATORS: Tuple[str, ...] = ("exists", "not_exists")

#: Short operators kept for backwards compatibility with the Phase 1 payloads.
OPERATOR_ALIASES: Dict[str, str] = {
    "eq": "equals",
    "neq": "not_equals",
    "gt": "greater_than",
    "gte": "greater_than_or_equal",
    "lt": "less_than",
    "lte": "less_than_or_equal",
    "notexists": "not_exists",
    "not_exists": "not_exists",
    "exists": "exists",
}


def normalize_operator(op: Optional[str]) -> str:
    """
    Maps any accepted operator spelling onto its canonical name.
    Unknown operators fall back to ``equals`` so evaluation never raises.
    """
    if not op:
        return "equals"
    lowered = str(op).strip().lower()
    return OPERATOR_ALIASES.get(lowered, lowered)


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
    op = normalize_operator(condition.get("op"))
    target_value = condition.get("value")

    if not attr_name:
        return False

    # Presence operators are the only ones that do not require the attribute
    # to be present, so they are evaluated before the membership check.
    if op == "exists":
        return attr_name in attributes
    if op == "not_exists":
        return attr_name not in attributes

    if attr_name not in attributes:
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

    # 2. Check targeting rules (lowest priority number first).
    # Sorted here rather than relying on the caller, so the documented
    # "first match by ascending priority wins" contract holds no matter how the
    # rule list arrives. Callers already pass sorted lists, so this is a no-op
    # for them and keeps the Python SDK's local evaluation byte-identical.
    for rule in sorted(rules, key=lambda item: item.get("priority", 0)):
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
