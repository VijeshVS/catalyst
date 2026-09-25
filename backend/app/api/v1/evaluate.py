from typing import Dict, Union
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.deps import (
    get_current_sdk_key_or_user,
    get_environment_or_404,
    get_project_or_404,
)
from app.core.db import get_db
from app.models.models import ApiKey, Environment, Flag, User
from app.schemas.schemas import (
    EvaluateRequest,
    EvaluateResponse,
    BatchEvaluateRequest,
    BatchEvaluateResponse,
)
from app.services.evaluator import evaluate_flag

router = APIRouter(prefix="", tags=["Evaluation"])

PROJECT_ID_QUERY = Query(..., description="ID of the project that scopes this request")


@router.post("/evaluate", response_model=EvaluateResponse)
async def evaluate_single_flag(
    req: EvaluateRequest,
    project_id: str = PROJECT_ID_QUERY,
    db: AsyncSession = Depends(get_db),
    auth_entity: Union[ApiKey, User] = Depends(get_current_sdk_key_or_user),
):
    # For SDK keys, verify the key's project matches the requested project_id
    if isinstance(auth_entity, ApiKey) and auth_entity.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key does not have access to this project",
        )

    if isinstance(auth_entity, User):
        owner_id = auth_entity.id
    else:
        owner_id = auth_entity.organization_owner_id
        if not owner_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="API key owner information not available",
            )

    project = await get_project_or_404(db, project_id, owner_id)

    # For SDK keys, look up the environment directly within the project
    # For users, use the existing get_environment_or_404 which checks ownership
    if isinstance(auth_entity, ApiKey):
        env_stmt = select(Environment).where(
            Environment.project_id == project.id,
            Environment.name == req.env,
        )
        env_result = await db.execute(env_stmt)
        environment = env_result.scalar_one_or_none()
        if not environment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Environment '{req.env}' not found in this project",
            )
    else:
        environment = await get_environment_or_404(db, project.id, req.env, auth_entity.id)

    stmt = (
        select(Flag)
        .where(Flag.project_id == project.id, Flag.key == req.flag_key, Flag.archived == False)
        .options(selectinload(Flag.states), selectinload(Flag.rules))
    )
    res = await db.execute(stmt)
    flag = res.scalar_one_or_none()

    if not flag:
        return EvaluateResponse(
            flag_key=req.flag_key,
            value=False,
            reason="FLAG_NOT_FOUND",
        )

    # Find env state
    state = next((s for s in flag.states if s.env == req.env), None)
    enabled = state.enabled if state else True
    percentage = state.percentage if state else 0

    # Find env rules sorted by priority
    rules = [
        {"id": r.id, "conditions": r.conditions_json, "serve": r.serve}
        for r in sorted(flag.rules, key=lambda x: x.priority)
        if r.env == req.env
    ]

    val, reason, rule_id = evaluate_flag(
        flag_key=flag.key,
        default_value=flag.default_value,
        enabled=enabled,
        percentage=percentage,
        rules=rules,
        user_id=req.context.user_id,
        attributes=req.context.attributes,
    )

    return EvaluateResponse(
        flag_key=flag.key,
        value=val,
        reason=reason,
        rule_id=rule_id,
    )


@router.post("/batch-evaluate", response_model=BatchEvaluateResponse)
async def evaluate_batch_flags(
    req: BatchEvaluateRequest,
    project_id: str = PROJECT_ID_QUERY,
    db: AsyncSession = Depends(get_db),
    auth_entity: Union[ApiKey, User] = Depends(get_current_sdk_key_or_user),
):
    # For SDK keys, verify the key's project matches the requested project_id
    if isinstance(auth_entity, ApiKey) and auth_entity.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key does not have access to this project",
        )

    if isinstance(auth_entity, User):
        owner_id = auth_entity.id
    else:
        owner_id = auth_entity.organization_owner_id
        if not owner_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="API key owner information not available",
            )

    project = await get_project_or_404(db, project_id, owner_id)

    # For SDK keys, look up the environment directly within the project
    # For users, use the existing get_environment_or_404 which checks ownership
    if isinstance(auth_entity, ApiKey):
        env_stmt = select(Environment).where(
            Environment.project_id == project.id,
            Environment.name == req.env,
        )
        env_result = await db.execute(env_stmt)
        environment = env_result.scalar_one_or_none()
        if not environment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Environment '{req.env}' not found in this project",
            )
    else:
        environment = await get_environment_or_404(db, project.id, req.env, auth_entity.id)

    stmt = (
        select(Flag)
        .where(Flag.project_id == project.id, Flag.archived == False)
        .options(selectinload(Flag.states), selectinload(Flag.rules))
    )
    if req.flag_keys:
        stmt = stmt.where(Flag.key.in_(req.flag_keys))

    res = await db.execute(stmt)
    flags = res.scalars().all()

    evaluations: Dict[str, EvaluateResponse] = {}

    for flag in flags:
        state = next((s for s in flag.states if s.env == req.env), None)
        enabled = state.enabled if state else True
        percentage = state.percentage if state else 0

        rules = [
            {"id": r.id, "conditions": r.conditions_json, "serve": r.serve}
            for r in sorted(flag.rules, key=lambda x: x.priority)
            if r.env == req.env
        ]

        val, reason, rule_id = evaluate_flag(
            flag_key=flag.key,
            default_value=flag.default_value,
            enabled=enabled,
            percentage=percentage,
            rules=rules,
            user_id=req.context.user_id,
            attributes=req.context.attributes,
        )

        evaluations[flag.key] = EvaluateResponse(
            flag_key=flag.key,
            value=val,
            reason=reason,
            rule_id=rule_id,
        )

    return BatchEvaluateResponse(evaluations=evaluations)
