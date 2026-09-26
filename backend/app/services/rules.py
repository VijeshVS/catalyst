from typing import Any, Dict, Iterable, List, Sequence

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import TargetingRule


async def list_rules_for_env(
    db: AsyncSession,
    flag_id: str,
    env: str,
) -> List[TargetingRule]:
    """Returns a flag's targeting rules for one environment, highest priority first."""
    result = await db.execute(
        select(TargetingRule)
        .where(TargetingRule.flag_id == flag_id, TargetingRule.env == env)
        .order_by(TargetingRule.priority.asc(), TargetingRule.id.asc())
    )
    return list(result.scalars().all())


async def next_priority(db: AsyncSession, flag_id: str, env: str) -> int:
    """Returns the priority a newly appended rule should take."""
    result = await db.execute(
        select(TargetingRule.priority)
        .where(TargetingRule.flag_id == flag_id, TargetingRule.env == env)
        .order_by(TargetingRule.priority.desc())
        .limit(1)
    )
    highest = result.scalar_one_or_none()
    return 0 if highest is None else highest + 1


def normalize_priorities(rules: Sequence[TargetingRule]) -> None:
    """Renormalizes priorities to a dense 0..n-1 ordering in the given order."""
    for index, rule in enumerate(rules):
        rule.priority = index


def apply_ordered_ids(
    rules: Sequence[TargetingRule],
    ordered_ids: Sequence[str],
) -> List[TargetingRule]:
    """
    Resolves an explicit ordering request against the environment's rules.

    Every rule of the environment must appear exactly once so a reorder can
    never silently drop or invent a rule.
    """
    by_id = {rule.id: rule for rule in rules}
    requested = list(ordered_ids)

    if len(set(requested)) != len(requested):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="rule_ids must not contain duplicates",
        )

    missing = sorted(rule_id for rule_id in by_id if rule_id not in set(requested))
    unknown = [rule_id for rule_id in requested if rule_id not in by_id]
    if missing or unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="rule_ids must list every targeting rule in this environment exactly once",
        )

    return [by_id[rule_id] for rule_id in requested]


def serialize_rule(rule: TargetingRule) -> Dict[str, Any]:
    """Snapshot of a rule for `AuditLog.before` / `AuditLog.after` payloads."""
    return {
        "id": rule.id,
        "env": rule.env,
        "priority": rule.priority,
        "conditions": rule.conditions_json,
        "serve": rule.serve,
    }


def serialize_rules(rules: Iterable[TargetingRule]) -> List[Dict[str, Any]]:
    return [serialize_rule(rule) for rule in rules]
