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


#: Reason codes on EvaluateResponse.reason. An operator debugging a rollout has
#: to be able to tell "your rule did not match" from "your rule matched and you
#: fell outside the percentage" — two very different problems.
REASON_KILL_SWITCH = "KILL_SWITCH_ACTIVE"
REASON_ENABLE_ALL = "ENABLE_ALL_USERS"
REASON_RULE_AND_ROLLOUT = "RULE_AND_ROLLOUT"
REASON_RULE_OUTSIDE_ROLLOUT = "RULE_OUTSIDE_ROLLOUT"
REASON_PERCENTAGE_ROLLOUT = "PERCENTAGE_ROLLOUT"
REASON_PERCENTAGE_OUTSIDE_ROLLOUT = "PERCENTAGE_OUTSIDE_ROLLOUT"
REASON_DEFAULT = "DEFAULT_VALUE"


def evaluate_flag(
    flag_key: str,
    enabled: bool,
    enable_all: bool,
    percentage: int,
    rules: List[Dict[str, Any]],
    user_id: str,
    attributes: Dict[str, Any],
) -> Tuple[bool, str, Optional[str]]:
    """
    Evaluates a flag from its two switches, its rules, and its percentage.

    Order:

    1. The kill switch. Off means nobody gets the feature, and nothing else is
       even looked at.
    2. "Enable to all users". On means everybody does, with no targeting.
    3. Rules filter the population: the first rule matching by ascending
       priority puts the user in, and no match means they are out.
    4. The percentage splits whoever survived step 3.

    Returns: (served_value, reason, matched_rule_id)
    """
    # 1. Emergency Kill Switch: highest priority, no exceptions.
    if not enabled:
        return False, REASON_KILL_SWITCH, None

    # 2. Enable to all users: everybody, no targeting.
    if enable_all:
        return True, REASON_ENABLE_ALL, None

    # 3. Rules decide who is in the population. Sorted here rather than relying
    # on the caller, so the documented "first match by ascending priority
    # wins" contract holds no matter how the rule list arrives. Callers already
    # pass sorted lists, so this is a no-op for them and keeps the Python SDK's
    # local evaluation byte-identical.
    matched: Optional[Dict[str, Any]] = None
    for rule in sorted(rules, key=lambda item: item.get("priority", 0)):
        if match_rule(rule.get("conditions", []), attributes):
            matched = rule
            break

    if rules and matched is None:
        # Rules exist and filtered this user out, so they are not in the
        # population and the percentage is irrelevant to them.
        return False, REASON_DEFAULT, None

    # 4. The percentage splits the eligible population. The same bucket is
    # used for every percentage value, so raising it can only ever add users.
    serve = True if matched is None else bool(matched.get("serve", True))
    rule_id = matched.get("id") if matched else None
    inside = get_user_bucket(flag_key, user_id) < percentage

    if inside:
        reason = REASON_RULE_AND_ROLLOUT if matched else REASON_PERCENTAGE_ROLLOUT
        return serve, reason, rule_id

    # Outside the rollout the user gets the opposite of the rule's value, so
    # the two together still partition the matched group exactly.
    reason = REASON_RULE_OUTSIDE_ROLLOUT if matched else REASON_PERCENTAGE_OUTSIDE_ROLLOUT
    return not serve, reason, rule_id
