from typing import Union

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import (
    get_current_sdk_key_or_user,
    get_environment_or_404,
    get_project_or_404,
)
from app.core.db import get_db
from app.models.models import ApiKey, Environment, User
from app.schemas.schemas import BootstrapResponse
from app.services.snapshots import build_etag, load_env_snapshot

router = APIRouter(prefix="/bootstrap", tags=["SDK Bootstrap"])


@router.get("", response_model=BootstrapResponse)
async def get_bootstrap_snapshot(
    request: Request,
    response: Response,
    project_id: str = Query(..., description="ID of the project that scopes this snapshot"),
    env: str = "dev",
    db: AsyncSession = Depends(get_db),
    auth_entity: Union[ApiKey, User] = Depends(get_current_sdk_key_or_user),
):
    """
    Returns full environment flag snapshot for SDK evaluation.
    Supports HTTP ETag and If-None-Match for 304 Not Modified.

    The ETag derives from `Environment.version`, which is incremented by every
    mutation that changes this project environment's flag snapshot. The snapshot
    body itself is served from Redis when available and rebuilt from PostgreSQL
    on a miss, so a `304` costs one indexed environment lookup rather than a
    join over every flag, state and rule.

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

    etag = build_etag(project.id, env, environment.version)
    client_etag = request.headers.get("if-none-match")
    if client_etag == etag:
        # The environment version is unchanged, so the client's copy is still
        # current and the snapshot body never has to be loaded.
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers={"ETag": etag, "Cache-Control": "private, max-age=0, must-revalidate"},
        )

    snapshot = await load_env_snapshot(db, project.id, env, environment.version)

    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "private, max-age=0, must-revalidate"
    response.headers["X-Catalyst-Cache"] = snapshot.source

    return BootstrapResponse(**snapshot.to_payload())
