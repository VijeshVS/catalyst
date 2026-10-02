"""
Local flag evaluation, byte-for-byte equivalent to the Catalyst server.

Precedence, matching ``app/services/evaluator.py`` on the backend:

1. Emergency kill switch -> serve ``False`` to everyone, nothing else is looked at
2. "Enable to all users" -> serve ``True`` to everyone, no targeting at all
3. Targeting rules in ascending ``priority`` -> the first rule whose conditions
   all match puts the user in the population. If rules exist and none matched,
   the user is filtered out and served ``False``.
4. Percentage rollout -> a deterministic sticky bucket splits the eligible
   population. A matched user outside the bucket gets the *opposite* of the
   rule's value, so the two partition the matched group exactly.

A missing context attribute makes a condition false so the rule safely skips.
Nothing here performs I/O, which is what keeps evaluation sub-millisecond.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from .hashing import get_user_bucket

# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------
#: Canonical operators. Aliases are accepted on read and normalized here, so a
#: snapshot written by an older server still evaluates identically.
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

RULE_OPERATORS = (
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

#: Operators that only inspect presence; their ``value`` is ignored.
PRESENCE_OPERATORS = ("exists", "not_exists")


def normalize_operator(op: Optional[str]) -> str:
    """Maps any accepted operator spelling onto its canonical name."""
    if not op:
        return "equals"
    lowered = str(op).strip().lower()
    return OPERATOR_ALIASES.get(lowered, lowered)


# ---------------------------------------------------------------------------
# Reasons (kept identical to the server's EvaluateResponse.reason values)
# ---------------------------------------------------------------------------
#: An operator debugging a rollout has to be able to tell "your rule did not
#: match" (DEFAULT_VALUE) from "your rule matched and you fell outside the
#: percentage" (RULE_OUTSIDE_ROLLOUT) -- two very different problems.
REASON_KILL_SWITCH = "KILL_SWITCH_ACTIVE"
REASON_ENABLE_ALL = "ENABLE_ALL_USERS"
REASON_RULE_AND_ROLLOUT = "RULE_AND_ROLLOUT"
REASON_RULE_OUTSIDE_ROLLOUT = "RULE_OUTSIDE_ROLLOUT"
REASON_ROLLOUT = "PERCENTAGE_ROLLOUT"
REASON_ROLLOUT_OUTSIDE = "PERCENTAGE_OUTSIDE_ROLLOUT"
REASON_DEFAULT = "DEFAULT_VALUE"
REASON_FLAG_NOT_FOUND = "FLAG_NOT_FOUND"
REASON_NO_SNAPSHOT = "NO_SNAPSHOT"


@dataclass(frozen=True)
class Condition:
    attr: str
    op: str = "equals"
    value: Any = None

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "Condition":
        return cls(
            attr=str(raw.get("attr") or ""),
            op=normalize_operator(raw.get("op")),
            value=raw.get("value"),
        )


@dataclass(frozen=True)
class Rule:
    """One targeting rule from the bootstrap snapshot."""

    id: str
    priority: int
    conditions: List[Condition]
    serve: bool = True

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "Rule":
        conditions = [Condition.from_dict(entry) for entry in raw.get("conditions") or []]
        return cls(
            id=str(raw.get("id") or ""),
            priority=int(raw.get("priority") or 0),
            conditions=conditions,
            serve=bool(raw.get("serve", True)),
        )


@dataclass(frozen=True)
class EvaluationResult:
    """Outcome of evaluating a single flag."""

    value: bool
    reason: str
    rule_id: Optional[str] = None
    flag_key: str = ""
    flag_version: Optional[int] = None

    def __bool__(self) -> bool:  # pragma: no cover - convenience only
        return self.value


# ---------------------------------------------------------------------------
# Condition matching
# ---------------------------------------------------------------------------
def _as_string_list(value: Any) -> List[str]:
    """The server's fallback for a non-list ``in``/``not_in`` target."""
    return [part.strip() for part in str(value).split(",")]


def match_condition(condition: Condition, attributes: Mapping[str, Any]) -> bool:
    """
    Evaluates one condition against the context attributes.

    ``equals`` is a strict comparison, so a boolean attribute only equals the
    real boolean ``True``. Numeric operators use ``float()`` and treat an
    unparseable operand as "no match" instead of raising.
    """
    attr = condition.attr
    if not attr:
        return False

    if condition.op == "exists":
        return attr in attributes
    if condition.op == "not_exists":
        return attr not in attributes

    if attr not in attributes:
        return False

    actual = attributes[attr]
    target = condition.value

    try:
        if condition.op == "equals":
            return actual == target
        if condition.op == "not_equals":
            return actual != target
        if condition.op == "in":
            if isinstance(target, (list, tuple)):
                return actual in target
            # The server stringifies the actual value in this branch, so a
            # numeric attribute still matches the string "3" in a list.
            return str(actual) in _as_string_list(target)
        if condition.op == "not_in":
            if isinstance(target, (list, tuple)):
                return actual not in target
            return str(actual) not in _as_string_list(target)
        if condition.op == "contains":
            return str(target).lower() in str(actual).lower()
        if condition.op == "starts_with":
            return str(actual).lower().startswith(str(target).lower())
        if condition.op == "ends_with":
            return str(actual).lower().endswith(str(target).lower())
        if condition.op == "greater_than":
            return float(actual) > float(target)
        if condition.op == "greater_than_or_equal":
            return float(actual) >= float(target)
        if condition.op == "less_than":
            return float(actual) < float(target)
        if condition.op == "less_than_or_equal":
            return float(actual) <= float(target)
    except (ValueError, TypeError):
        return False

    return False


def match_rule(conditions: Sequence[Condition], attributes: Mapping[str, Any]) -> bool:
    """A rule matches when every condition matches (AND logic)."""
    if not conditions:
        # An unconditional rule always matches. The API rejects these on write,
        # but a snapshot could predate that validation.
        return True
    return all(match_condition(condition, attributes) for condition in conditions)


# ---------------------------------------------------------------------------
# Flag evaluation
# ---------------------------------------------------------------------------
def evaluate_flag(
    flag_key: str,
    enabled: bool,
    enable_all: bool,
    percentage: int,
    rules: Iterable[Rule],
    user_id: str,
    attributes: Mapping[str, Any],
    flag_version: Optional[int] = None,
) -> EvaluationResult:
    """
    Evaluates a flag from its two switches, its rules, and its percentage.

    Pure and allocation-light, so the hot path stays comfortably under a
    millisecond.
    """

    def result(value: bool, reason: str, rule_id: Optional[str] = None) -> EvaluationResult:
        return EvaluationResult(
            value=value,
            reason=reason,
            rule_id=rule_id,
            flag_key=flag_key,
            flag_version=flag_version,
        )

    # 1. Emergency Kill Switch: highest priority, no exceptions.
    if not enabled:
        return result(False, REASON_KILL_SWITCH)

    # 2. Enable to all users: everybody, no targeting.
    if enable_all:
        return result(True, REASON_ENABLE_ALL)

    # 3. Targeting rules, lowest priority number first, decide who is in.
    matched: Optional[Rule] = None
    for rule in sorted(rules, key=lambda item: item.priority):
        if match_rule(rule.conditions, attributes):
            matched = rule
            break

    if matched is None and rules:
        # Rules exist and filtered this user out, so they are not in the
        # population and the percentage is irrelevant to them.
        return result(False, REASON_DEFAULT)

    # 4. The percentage splits the eligible population. The same bucket is used
    # for every percentage value, so raising it can only ever add users.
    serve = True if matched is None else matched.serve
    rule_id = matched.id if matched is not None else None
    if get_user_bucket(flag_key, user_id) < percentage:
        reason = REASON_RULE_AND_ROLLOUT if matched else REASON_ROLLOUT
        return result(serve, reason, rule_id)

    reason = REASON_RULE_OUTSIDE_ROLLOUT if matched else REASON_ROLLOUT_OUTSIDE
    return result(not serve, reason, rule_id)
