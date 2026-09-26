from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.deps import (
    get_current_user,
    get_environment_or_404,
    get_project_or_404,
)
from app.core.db import get_db
from app.models.models import AuditLog, Flag, FlagEnvState, Project, TargetingRule, User
from app.schemas.schemas import (
    FlagCreate,
    FlagResponse,
    FlagStateSchema,
    FlagStateUpdate,
    RuleCreate,
    RuleReorder,
    RuleUpdate,
    TargetingRuleResponse,
)
from app.services.environments import bump_environment_versions, seed_missing_flag_states
from app.services.rules import (
    apply_ordered_ids,
    list_rules_for_env,
    next_priority,
    normalize_priorities,
    serialize_rule,
    serialize_rules,
)


router = APIRouter(prefix="/flags", tags=["Flags"])

PROJECT_ID_QUERY = Query(..., description="ID of the project that scopes this request")


async def _get_flag_in_project(db: AsyncSession, project_id: str, flag_key: str) -> Flag:
    result = await db.execute(
        select(Flag)
        .where(Flag.project_id == project_id, Flag.key == flag_key)
        .options(selectinload(Flag.states), selectinload(Flag.rules))
    )
    flag = result.scalar_one_or_none()
    if not flag:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flag not found")
    return flag


def _add_rule_audit(
    db: AsyncSession,
    *,
    project: Project,
    flag: Flag,
    env: str,
    user: User,
    action: str,
    before=None,
    after=None,
) -> None:
    """Records a targeting rule mutation with full user attribution."""
    db.add(
        AuditLog(
            org_id=project.org_id,
            project_id=project.id,
            flag_id=flag.id,
            env=env,
            actor=user.email,
            user_id=user.id,
            user_email=user.email,
            action=action,
            before=before,
            after=after,
        )
    )


@router.get("", response_model=List[FlagResponse])
async def list_flags(
    project_id: str = PROJECT_ID_QUERY,
    archived: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await get_project_or_404(db, project_id, current_user.id)
    result = await db.execute(
        select(Flag)
        .where(Flag.project_id == project.id, Flag.archived == archived)
        .options(selectinload(Flag.states), selectinload(Flag.rules))
        .order_by(Flag.created_at.desc())
    )
    return result.scalars().all()


@router.post("", response_model=FlagResponse, status_code=status.HTTP_201_CREATED)
async def create_flag(
    data: FlagCreate,
    project_id: str = PROJECT_ID_QUERY,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await get_project_or_404(db, project_id, current_user.id)

    existing = await db.execute(
        select(Flag).where(Flag.project_id == project.id, Flag.key == data.key)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Flag with key '{data.key}' already exists in this project",
        )

    flag = Flag(
        project_id=project.id,
        key=data.key,
        name=data.name,
        description=data.description,
        default_value=data.default_value,
    )
    db.add(flag)
    await db.flush()

    # Create a state row for every environment of the project.
    await seed_missing_flag_states(db, project.id)
    # The flag now appears in every environment snapshot -> bust SDK caches.
    await bump_environment_versions(db, project.id)

    db.add(
        AuditLog(
            org_id=project.org_id,
            project_id=project.id,
            flag_id=flag.id,
            actor=current_user.email,
            user_id=current_user.id,
            user_email=current_user.email,
            action="flag.created",
            after={"key": flag.key, "name": flag.name, "default_value": flag.default_value},
        )
    )
    await db.commit()

    result = await db.execute(
        select(Flag)
        .where(Flag.id == flag.id)
        .options(selectinload(Flag.states), selectinload(Flag.rules))
    )
    return result.scalar_one()


@router.get("/{flag_key}", response_model=FlagResponse)
async def get_flag(
    flag_key: str,
    project_id: str = PROJECT_ID_QUERY,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await get_project_or_404(db, project_id, current_user.id)
    return await _get_flag_in_project(db, project.id, flag_key)


@router.patch("/{flag_key}/environments/{env}", response_model=FlagStateSchema)
async def update_flag_env_state(
    flag_key: str,
    env: str,
    data: FlagStateUpdate,
    project_id: str = PROJECT_ID_QUERY,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update rollout percentage or trigger the Emergency Kill Switch."""
    project = await get_project_or_404(db, project_id, current_user.id)
    # The environment must belong to this project (strict project scoping).
    await get_environment_or_404(db, project.id, env, current_user.id)
    flag = await _get_flag_in_project(db, project.id, flag_key)

    result = await db.execute(
        select(FlagEnvState).where(
            FlagEnvState.flag_id == flag.id,
            FlagEnvState.env == env,
        )
    )
    state = result.scalar_one_or_none()
    if not state:
        state = FlagEnvState(flag_id=flag.id, env=env, enabled=True, percentage=0, version=1)
        db.add(state)

    before_state = {"enabled": state.enabled, "percentage": state.percentage}

    if data.enabled is not None:
        state.enabled = data.enabled
    if data.percentage is not None:
        state.percentage = data.percentage

    state.version += 1
    # The environment snapshot changed -> bust the bootstrap ETag.
    await bump_environment_versions(db, project.id, env_names=[env])

    action_name = "flag.updated"
    if data.enabled is not None and data.enabled != before_state["enabled"]:
        action_name = "kill_switch.activated" if not data.enabled else "kill_switch.deactivated"
    elif data.percentage is not None and data.percentage != before_state["percentage"]:
        action_name = "rollout.percentage_updated"

    db.add(
        AuditLog(
            org_id=project.org_id,
            project_id=project.id,
            flag_id=flag.id,
            env=env,
            actor=current_user.email,
            user_id=current_user.id,
            user_email=current_user.email,
            action=action_name,
            before=before_state,
            after={"enabled": state.enabled, "percentage": state.percentage},
        )
    )

    await db.commit()
    await db.refresh(state)
    return state


# ---------------------------------------------------------------------------
# Targeting rules (environment scoped, ordered by priority)
# ---------------------------------------------------------------------------
@router.get(
    "/{flag_key}/environments/{env}/rules",
    response_model=List[TargetingRuleResponse],
)
async def list_flag_rules(
    flag_key: str,
    env: str,
    project_id: str = PROJECT_ID_QUERY,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List a flag's targeting rules for one environment, highest priority first."""
    project = await get_project_or_404(db, project_id, current_user.id)
    await get_environment_or_404(db, project.id, env, current_user.id)
    flag = await _get_flag_in_project(db, project.id, flag_key)
    return await list_rules_for_env(db, flag.id, env)


@router.post(
    "/{flag_key}/environments/{env}/rules",
    response_model=TargetingRuleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_flag_rule(
    flag_key: str,
    env: str,
    data: RuleCreate,
    project_id: str = PROJECT_ID_QUERY,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a targeting rule. Conditions are ANDed and priority 0 wins."""
    project = await get_project_or_404(db, project_id, current_user.id)
    await get_environment_or_404(db, project.id, env, current_user.id)
    flag = await _get_flag_in_project(db, project.id, flag_key)

    priority = data.priority
    if priority is None:
        priority = await next_priority(db, flag.id, env)

    rule = TargetingRule(
        flag_id=flag.id,
        env=env,
        priority=priority,
        conditions_json=[condition.model_dump() for condition in data.conditions],
        serve=data.serve,
    )
    db.add(rule)
    # The snapshot changed -> bust the bootstrap ETag for this environment only.
    await bump_environment_versions(db, project.id, env_names=[env])

    _add_rule_audit(
        db,
        project=project,
        flag=flag,
        env=env,
        user=current_user,
        action="rule.created",
        after=serialize_rule(rule),
    )

    await db.commit()
    await db.refresh(rule)
    return rule


# Declared before `/{rule_id}` so the literal path is not captured as a rule id.
@router.put(
    "/{flag_key}/environments/{env}/rules/reorder",
    response_model=List[TargetingRuleResponse],
)
async def reorder_flag_rules(
    flag_key: str,
    env: str,
    data: RuleReorder,
    project_id: str = PROJECT_ID_QUERY,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Re-order rules and renormalize priorities to a dense 0..n-1 sequence."""
    project = await get_project_or_404(db, project_id, current_user.id)
    await get_environment_or_404(db, project.id, env, current_user.id)
    flag = await _get_flag_in_project(db, project.id, flag_key)

    existing = await list_rules_for_env(db, flag.id, env)
    before = serialize_rules(existing)
    ordered = apply_ordered_ids(existing, data.rule_ids)
    normalize_priorities(ordered)

    await bump_environment_versions(db, project.id, env_names=[env])
    _add_rule_audit(
        db,
        project=project,
        flag=flag,
        env=env,
        user=current_user,
        action="rule.reordered",
        before={"order": [rule["id"] for rule in before]},
        after={"order": [rule.id for rule in ordered]},
    )

    await db.commit()
    return ordered


@router.put(
    "/{flag_key}/environments/{env}/rules/{rule_id}",
    response_model=TargetingRuleResponse,
)
async def update_flag_rule(
    flag_key: str,
    env: str,
    rule_id: str,
    data: RuleUpdate,
    project_id: str = PROJECT_ID_QUERY,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a rule's conditions, served value, or priority."""
    project = await get_project_or_404(db, project_id, current_user.id)
    await get_environment_or_404(db, project.id, env, current_user.id)
    flag = await _get_flag_in_project(db, project.id, flag_key)

    result = await db.execute(
        select(TargetingRule).where(
            TargetingRule.id == rule_id,
            TargetingRule.flag_id == flag.id,
            TargetingRule.env == env,
        )
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Targeting rule not found in this environment",
        )

    before = serialize_rule(rule)
    if data.conditions is not None:
        rule.conditions_json = [condition.model_dump() for condition in data.conditions]
    if data.serve is not None:
        rule.serve = data.serve
    if data.priority is not None:
        rule.priority = data.priority

    await bump_environment_versions(db, project.id, env_names=[env])
    _add_rule_audit(
        db,
        project=project,
        flag=flag,
        env=env,
        user=current_user,
        action="rule.updated",
        before=before,
        after=serialize_rule(rule),
    )

    await db.commit()
    await db.refresh(rule)
    return rule


@router.delete(
    "/{flag_key}/environments/{env}/rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_flag_rule(
    flag_key: str,
    env: str,
    rule_id: str,
    project_id: str = PROJECT_ID_QUERY,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a targeting rule and close the priority gap it leaves behind."""
    project = await get_project_or_404(db, project_id, current_user.id)
    await get_environment_or_404(db, project.id, env, current_user.id)
    flag = await _get_flag_in_project(db, project.id, flag_key)

    result = await db.execute(
        select(TargetingRule).where(
            TargetingRule.id == rule_id,
            TargetingRule.flag_id == flag.id,
            TargetingRule.env == env,
        )
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Targeting rule not found in this environment",
        )

    before = serialize_rule(rule)
    remaining = [candidate for candidate in await list_rules_for_env(db, flag.id, env) if candidate.id != rule.id]
    normalize_priorities(remaining)

    await db.delete(rule)
    await bump_environment_versions(db, project.id, env_names=[env])
    _add_rule_audit(
        db,
        project=project,
        flag=flag,
        env=env,
        user=current_user,
        action="rule.deleted",
        before=before,
        after={"order": [candidate.id for candidate in remaining]},
    )

    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
