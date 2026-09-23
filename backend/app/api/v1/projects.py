from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_project_or_404
from app.core.db import get_db
from app.models.models import AuditLog, Environment
from app.schemas.schemas import EnvironmentCreate, EnvironmentResponse
from app.services.environments import seed_missing_flag_states, sort_environments

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.get("/{project_id}/environments", response_model=List[EnvironmentResponse])
async def list_environments(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    project = await get_project_or_404(db, project_id)
    res = await db.execute(
        select(Environment).where(Environment.project_id == project.id)
    )
    return sort_environments(res.scalars().all())


@router.post(
    "/{project_id}/environments",
    response_model=EnvironmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_environment(
    project_id: str,
    data: EnvironmentCreate,
    db: AsyncSession = Depends(get_db),
):
    project = await get_project_or_404(db, project_id)

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
            actor="developer",
            action="environment.created",
            after={"name": environment.name},
        )
    )
    await db.commit()
    await db.refresh(environment)
    return environment
