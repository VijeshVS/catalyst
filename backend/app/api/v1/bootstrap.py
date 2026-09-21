from typing import Any, Dict
from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.db import get_db
from app.models.models import Flag, FlagEnvState, TargetingRule, Environment, Project
from app.schemas.schemas import BootstrapResponse

router = APIRouter(prefix="/bootstrap", tags=["SDK Bootstrap"])


@router.get("", response_model=BootstrapResponse)
async def get_bootstrap_snapshot(
    request: Request,
    response: Response,
    env: str = "prod",
    db: AsyncSession = Depends(get_db),
):
    """
    Returns full environment flag snapshot for SDK in-memory evaluation.
    Supports HTTP ETag and If-None-Match for 304 Not Modified.
    """
    # Fetch environment version
    env_stmt = select(Environment).where(Environment.name == env).limit(1)
    env_res = await db.execute(env_stmt)
    env_obj = env_res.scalar_one_or_none()
    env_version = env_obj.version if env_obj else 1

    etag = f'W/"{env}-{env_version}"'
    client_etag = request.headers.get("if-none-match")
    if client_etag == etag:
        response.status_code = status.HTTP_304_NOT_MODIFIED
        return Response(status_code=status.HTTP_304_NOT_MODIFIED)

    # Fetch active flags
    stmt = (
        select(Flag)
        .where(Flag.archived == False)
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
    response.headers["Cache-Control"] = "public, max-age=0, must-revalidate"

    return BootstrapResponse(
        env=env,
        version=env_version,
        flags=flag_map,
    )
