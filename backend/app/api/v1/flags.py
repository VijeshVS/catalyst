from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.deps import get_environment_or_404, get_project_or_404
from app.core.db import get_db
from app.models.models import Flag, FlagEnvState, AuditLog
from app.schemas.schemas import (
    FlagCreate,
    FlagResponse,
    FlagStateUpdate,
    FlagStateSchema,
)
from app.services.environments import bump_environment_versions, seed_missing_flag_states

router = APIRouter(prefix="/flags", tags=["Flags"])

PROJECT_ID_QUERY = Query(..., description="ID of the project that scopes this request")


async def _get_flag_in_project(db: AsyncSession, project_id: str, flag_key: str) -> Flag:
    stmt = (
        select(Flag)
        .where(Flag.project_id == project_id, Flag.key == flag_key)
        .options(selectinload(Flag.states), selectinload(Flag.rules))
    )
    res = await db.execute(stmt)
    flag = res.scalar_one_or_none()
    if not flag:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flag not found")
    return flag


@router.get("", response_model=List[FlagResponse])
async def list_flags(
    project_id: str = PROJECT_ID_QUERY,
    archived: bool = False,
    db: AsyncSession = Depends(get_db),
):
    project = await get_project_or_404(db, project_id)
    stmt = (
        select(Flag)
        .where(Flag.project_id == project.id, Flag.archived == archived)
        .options(selectinload(Flag.states), selectinload(Flag.rules))
        .order_by(Flag.created_at.desc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=FlagResponse, status_code=status.HTTP_201_CREATED)
async def create_flag(
    data: FlagCreate,
    project_id: str = PROJECT_ID_QUERY,
    db: AsyncSession = Depends(get_db),
):
    project = await get_project_or_404(db, project_id)

    # Check unique key within the project
    stmt = select(Flag).where(Flag.project_id == project.id, Flag.key == data.key)
    existing = await db.execute(stmt)
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

    # Create a state row for every environment of the project
    await seed_missing_flag_states(db, project.id)
    # The flag now appears in every environment snapshot -> bust SDK caches
    await bump_environment_versions(db, project.id)

    audit = AuditLog(
        org_id=project.org_id,
        project_id=project.id,
        flag_id=flag.id,
        actor="developer",
        action="flag.created",
        after={"key": flag.key, "name": flag.name, "default_value": flag.default_value},
    )
    db.add(audit)

    await db.commit()

    # Re-fetch with relationships
    stmt = (
        select(Flag)
        .where(Flag.id == flag.id)
        .options(selectinload(Flag.states), selectinload(Flag.rules))
    )
    res = await db.execute(stmt)
    return res.scalar_one()


@router.get("/{flag_key}", response_model=FlagResponse)
async def get_flag(
    flag_key: str,
    project_id: str = PROJECT_ID_QUERY,
    db: AsyncSession = Depends(get_db),
):
    project = await get_project_or_404(db, project_id)
    return await _get_flag_in_project(db, project.id, flag_key)


@router.patch("/{flag_key}/environments/{env}", response_model=FlagStateSchema)
async def update_flag_env_state(
    flag_key: str,
    env: str,
    data: FlagStateUpdate,
    project_id: str = PROJECT_ID_QUERY,
    db: AsyncSession = Depends(get_db),
):
    """
    Update rollout percentage or trigger Emergency Kill Switch (enabled = False).
    """
    project = await get_project_or_404(db, project_id)
    # The environment must belong to the project (strict scoping)
    await get_environment_or_404(db, project.id, env)
    flag = await _get_flag_in_project(db, project.id, flag_key)

    state_stmt = select(FlagEnvState).where(
        FlagEnvState.flag_id == flag.id,
        FlagEnvState.env == env,
    )
    res = await db.execute(state_stmt)
    state = res.scalar_one_or_none()
    if not state:
        state = FlagEnvState(flag_id=flag.id, env=env, enabled=True, percentage=0, version=1)
        db.add(state)

    before_state = {"enabled": state.enabled, "percentage": state.percentage}

    if data.enabled is not None:
        state.enabled = data.enabled
    if data.percentage is not None:
        state.percentage = data.percentage

    state.version += 1
    # The environment snapshot changed -> bust the bootstrap ETag
    await bump_environment_versions(db, project.id, env_names=[env])

    action_name = "flag.updated"
    if data.enabled is not None and data.enabled != before_state["enabled"]:
        action_name = "kill_switch.activated" if not data.enabled else "kill_switch.deactivated"
    elif data.percentage is not None and data.percentage != before_state["percentage"]:
        action_name = "rollout.percentage_updated"

    audit = AuditLog(
        org_id=project.org_id,
        project_id=project.id,
        flag_id=flag.id,
        env=env,
        actor="developer",
        action=action_name,
        before=before_state,
        after={"enabled": state.enabled, "percentage": state.percentage},
    )
    db.add(audit)

    await db.commit()
    await db.refresh(state)
    return state
