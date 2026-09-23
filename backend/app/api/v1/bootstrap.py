from typing import Any, Dict
from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.deps import get_environment_or_404, get_project_or_404
from app.core.db import get_db
from app.models.models import Flag
from app.schemas.schemas import BootstrapResponse

router = APIRouter(prefix="/bootstrap", tags=["SDK Bootstrap"])


@router.get("", response_model=BootstrapResponse)
async def get_bootstrap_snapshot(
    request: Request,
    response: Response,
    project_id: str = Query(..., description="ID of the project that scopes this snapshot"),
    env: str = "prod",
    db: AsyncSession = Depends(get_db),
):
    """
    Returns full environment flag snapshot for SDK in-memory evaluation.
    Supports HTTP ETag and If-None-Match for 304 Not Modified.

    The ETag derives from `Environment.version`, which is incremented by every
    mutation that changes this project environment's flag snapshot.
    """
    project = await get_project_or_404(db, project_id)
    environment = await get_environment_or_404(db, project.id, env)
    env_version = environment.version

    etag = f'W/"{env}-{env_version}"'
    client_etag = request.headers.get("if-none-match")
    if client_etag == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers={"ETag": etag, "Cache-Control": "public, max-age=0, must-revalidate"},
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
    response.headers["Cache-Control"] = "public, max-age=0, must-revalidate"

    return BootstrapResponse(
        env=env,
        version=env_version,
        flags=flag_map,
    )
