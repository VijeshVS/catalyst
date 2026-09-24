from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Environment, Organization, Project


async def get_organization_or_404(db: AsyncSession, org_id: str) -> Organization:
    res = await db.execute(select(Organization).where(Organization.id == org_id))
    organization = res.scalar_one_or_none()
    if not organization:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return organization


async def get_project_or_404(db: AsyncSession, project_id: str) -> Project:
    res = await db.execute(select(Project).where(Project.id == project_id))
    project = res.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


async def get_environment_or_404(db: AsyncSession, project_id: str, env_name: str) -> Environment:
    res = await db.execute(
        select(Environment).where(
            Environment.project_id == project_id,
            Environment.name == env_name,
        )
    )
    environment = res.scalar_one_or_none()
    if not environment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Environment '{env_name}' not found in this project",
        )
    return environment
