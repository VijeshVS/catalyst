from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, get_project_or_404
from app.core.db import get_db
from app.models.models import ApiKey, AuditLog, Environment, User
from app.schemas.schemas import (
    ApiKeyCreate,
    ApiKeyCreatedResponse,
    ApiKeyListResponse,
    ApiKeyResponse,
    EnvironmentCreate,
    EnvironmentResponse,
)
from app.services.api_keys import create_api_key, list_api_keys
from app.services.environments import seed_missing_flag_states, sort_environments


router = APIRouter(prefix="/projects", tags=["Projects"])


@router.get("/{project_id}/environments", response_model=List[EnvironmentResponse])
async def list_environments(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await get_project_or_404(db, project_id, current_user.id)
    result = await db.execute(
        select(Environment).where(Environment.project_id == project.id)
    )
    return sort_environments(result.scalars().all())


@router.post(
    "/{project_id}/environments",
    response_model=EnvironmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_environment(
    project_id: str,
    data: EnvironmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await get_project_or_404(db, project_id, current_user.id)

    existing = await db.execute(
        select(Environment).where(
            Environment.project_id == project.id,
            Environment.name == data.name,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Environment '{data.name}' already exists in this project",
        )

    environment = Environment(project_id=project.id, name=data.name, version=1)
    db.add(environment)
    await db.flush()

    # Existing flags become manageable in the new environment immediately.
    await seed_missing_flag_states(db, project.id)

    db.add(
        AuditLog(
            org_id=project.org_id,
            project_id=project.id,
            env=environment.name,
            actor=current_user.email,
            user_id=current_user.id,
            user_email=current_user.email,
            action="environment.created",
            after={"name": environment.name},
        )
    )
    await db.commit()
    await db.refresh(environment)
    return environment


@router.post(
    "/{project_id}/keys",
    response_model=ApiKeyCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_api_key_endpoint(
    project_id: str,
    data: ApiKeyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new API key for a project environment.

    The full API key (raw_key) is returned only once - immediately upon creation.
    Clients must store this securely as it cannot be retrieved later.
    """
    project = await get_project_or_404(db, project_id, current_user.id)

    # Verify the environment exists in this project
    env_stmt = select(Environment).where(
        Environment.project_id == project.id,
        Environment.name == data.env,
    )
    env_result = await db.execute(env_stmt)
    if not env_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Environment '{data.env}' not found in this project",
        )

    # Generate and store the API key
    raw_key, api_key = await create_api_key(
        db=db,
        project_id=project.id,
        env=data.env,
        name=data.name,
    )

    # Record audit log
    db.add(
        AuditLog(
            org_id=project.org_id,
            project_id=project.id,
            env=data.env,
            actor=current_user.email,
            user_id=current_user.id,
            user_email=current_user.email,
            action="api_key.created",
            after={"name": data.name, "env": data.env},
        )
    )
    await db.commit()

    # The full key is returned here and nowhere else, ever again.
    return ApiKeyCreatedResponse(
        id=api_key.id,
        project_id=api_key.project_id,
        env=api_key.env,
        name=api_key.name,
        revoked=api_key.revoked,
        created_at=api_key.created_at,
        key=raw_key,
    )


@router.get("/{project_id}/keys", response_model=ApiKeyListResponse)
async def list_api_keys_endpoint(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all API keys for a project."""
    project = await get_project_or_404(db, project_id, current_user.id)

    keys = await list_api_keys(db, project.id, active_only=False)

    return ApiKeyListResponse(
        keys=[
            ApiKeyResponse(
                id=k.id,
                project_id=k.project_id,
                env=k.env,
                name=k.name,
                revoked=k.revoked,
                created_at=k.created_at,
            )
            for k in keys
        ]
    )


@router.delete("/{project_id}/keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key_endpoint(
    project_id: str,
    key_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete an API key by ID."""
    project = await get_project_or_404(db, project_id, current_user.id)

    # Verify the key belongs to this project
    stmt = select(ApiKey).where(ApiKey.id == key_id, ApiKey.project_id == project.id)
    result = await db.execute(stmt)
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found in this project",
        )

    # The row goes, rather than being flagged: a revoked key that cannot be
    # removed is what made keys look undeletable. The audit entry is the
    # durable record that the key ever existed (see docs/adr/002).
    db.add(
        AuditLog(
            org_id=project.org_id,
            project_id=project.id,
            env=api_key.env,
            actor=current_user.email,
            user_id=current_user.id,
            user_email=current_user.email,
            action="api_key.deleted",
            before={"name": api_key.name, "env": api_key.env},
        )
    )
    await db.delete(api_key)
    await db.commit()

    return None
