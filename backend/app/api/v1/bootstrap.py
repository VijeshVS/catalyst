from typing import Any, Dict, Union
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
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
from app.schemas.schemas import BootstrapResponse

router = APIRouter(prefix="/bootstrap", tags=["SDK Bootstrap"])


@router.get("", response_model=BootstrapResponse)
async def get_bootstrap_snapshot(
    request: Request,
    response: Response,
    project_id: str = Query(..., description="ID of the project that scopes this snapshot"),
    env: str = "prod",
    db: AsyncSession = Depends(get_db),
    auth_entity: Union[ApiKey, User] = Depends(get_current_sdk_key_or_user),
):
    """
    Returns full environment flag snapshot for SDK in-memory evaluation.
    Supports HTTP ETag and If-None-Match for 304 Not Modified.

    The ETag derives from `Environment.version`, which is incremented by every
    mutation that changes this project environment's flag snapshot.

    Authentication: Either Bearer token (user) or X-SDK-Key (SDK).
    """
    from app.models.models import ApiKey

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
    env_version = environment.version

    etag = f'W/"{project.id}:{env}:{env_version}"'
    client_etag = request.headers.get("if-none-match")
    if client_etag == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers={"ETag": etag, "Cache-Control": "private, max-age=0, must-revalidate"},
        )

    # Fetch active flags for this project only
    stmt = (
        select(Flag)
        .where(Flag.project_id == project.id, Flag.archived == False)
        .options(selectinload(Flag.states), selectinload(Flag.rules))
    )
    res = await db.execute(stmt)
    flags = res.scalars().all()

    flag_map: Dict[str, Any] = {}
    for flag in flags:
        state = next((s for s in flag.states if s.env == env), None)
        enabled = state.enabled if state else True
        percentage = state.percentage if state else 0

        rules = [
            {
                "id": r.id,
                "priority": r.priority,
                "conditions": r.conditions_json,
                "serve": r.serve,
            }
            for r in sorted(flag.rules, key=lambda x: x.priority)
            if r.env == env
        ]

        flag_map[flag.key] = {
            "key": flag.key,
            "defaultValue": flag.default_value,
            "enabled": enabled,
            "percentage": percentage,
            "rules": rules,
        }

    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "private, max-age=0, must-revalidate"

    return BootstrapResponse(
        env=env,
        version=env_version,
        flags=flag_map,
    )
