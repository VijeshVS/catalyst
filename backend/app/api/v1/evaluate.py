from typing import Dict, Union

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import (
    get_current_sdk_key_or_user,
    get_environment_or_404,
    get_project_or_404,
)
from app.core.db import get_db
from app.models.models import ApiKey, Environment, User
from app.schemas.schemas import (
    BatchEvaluateRequest,
    BatchEvaluateResponse,
    EvaluateRequest,
    EvaluateResponse,
)
from app.services.evaluator import evaluate_flag
from app.services.snapshots import load_env_snapshot

router = APIRouter(prefix="", tags=["Evaluation"])

PROJECT_ID_QUERY = Query(..., description="ID of the project that scopes this request")


async def _resolve_environment(
    db: AsyncSession,
    auth_entity: Union[ApiKey, User],
    project_id: str,
    env: str,
):
    """
    Authorizes the caller and returns the project plus its named environment.

    Shared by both evaluate endpoints, which otherwise repeated this preamble.
    """
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
            Environment.name == env,
        )
        env_result = await db.execute(env_stmt)
        environment = env_result.scalar_one_or_none()
        if not environment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Environment '{env}' not found in this project",
            )
    else:
        environment = await get_environment_or_404(db, project.id, env, auth_entity.id)

    return project, environment


def _evaluate_entry(entry: Dict, user_id: str, attributes: Dict) -> EvaluateResponse:
    """Runs the shared evaluator over one resolved snapshot flag entry."""
    value, reason, rule_id = evaluate_flag(
        flag_key=entry["key"],
        enabled=entry["enabled"],
        enable_all=entry["enableAll"],
        percentage=entry["percentage"],
        rules=entry["rules"],
        user_id=user_id,
        attributes=attributes,
    )
    return EvaluateResponse(
        flag_key=entry["key"],
        value=value,
        reason=reason,
        rule_id=rule_id,
    )


@router.post("/evaluate", response_model=EvaluateResponse)
async def evaluate_single_flag(
    req: EvaluateRequest,
    response: Response,
    project_id: str = PROJECT_ID_QUERY,
    db: AsyncSession = Depends(get_db),
    auth_entity: Union[ApiKey, User] = Depends(get_current_sdk_key_or_user),
):
    project, environment = await _resolve_environment(db, auth_entity, project_id, req.env)

    # The whole environment snapshot is read through Redis, so a repeat
    # evaluation costs no flag queries at all.
    snapshot = await load_env_snapshot(db, project.id, req.env, environment.version)
    response.headers["X-Catalyst-Cache"] = snapshot.source

    entry = snapshot.flags.get(req.flag_key)
    if entry is None:
        return EvaluateResponse(
            flag_key=req.flag_key,
            value=False,
            reason="FLAG_NOT_FOUND",
        )

    return _evaluate_entry(entry, req.context.user_id, req.context.attributes)


@router.post("/batch-evaluate", response_model=BatchEvaluateResponse)
async def evaluate_batch_flags(
    req: BatchEvaluateRequest,
    response: Response,
    project_id: str = PROJECT_ID_QUERY,
    db: AsyncSession = Depends(get_db),
    auth_entity: Union[ApiKey, User] = Depends(get_current_sdk_key_or_user),
):
    project, environment = await _resolve_environment(db, auth_entity, project_id, req.env)

    snapshot = await load_env_snapshot(db, project.id, req.env, environment.version)
    response.headers["X-Catalyst-Cache"] = snapshot.source

    requested = set(req.flag_keys) if req.flag_keys else None
    evaluations: Dict[str, EvaluateResponse] = {}

    for key, entry in snapshot.flags.items():
        if requested is not None and key not in requested:
            continue
        evaluations[key] = _evaluate_entry(entry, req.context.user_id, req.context.attributes)

    return BatchEvaluateResponse(evaluations=evaluations)
