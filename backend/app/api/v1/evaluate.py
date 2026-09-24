from typing import Dict
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.deps import get_environment_or_404, get_project_or_404
from app.core.db import get_db
from app.models.models import Flag
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
):
    project = await get_project_or_404(db, project_id)
    await get_environment_or_404(db, project.id, req.env)

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
):
    project = await get_project_or_404(db, project_id)
    await get_environment_or_404(db, project.id, req.env)

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
