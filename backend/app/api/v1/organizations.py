from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.deps import get_organization_or_404, get_current_user
from app.core.db import get_db
from app.models.models import AuditLog, Organization, Project, User
from app.schemas.schemas import (
    EnvironmentResponse,
    OrganizationCreate,
    OrganizationResponse,
    ProjectCreate,
    ProjectResponse,
)
from app.services.environments import provision_standard_environments, sort_environments


router = APIRouter(prefix="/organizations", tags=["Organizations"])


def _organizations_with_projects(owner_id: str):
    return select(Organization).where(Organization.owner_id == owner_id).options(
        selectinload(Organization.projects).selectinload(Project.environments),
        selectinload(Organization.projects).selectinload(Project.flags),
    )


def _serialize_project(project: Project) -> ProjectResponse:
    """Build a project response with deterministic display metadata."""
    environments = sort_environments(project.environments)
    latest_flag = max(
        (flag.created_at for flag in project.flags),
        default=project.created_at,
    )
    return ProjectResponse(
        id=project.id,
        org_id=project.org_id,
        name=project.name,
        created_at=project.created_at,
        environments=[
            EnvironmentResponse.model_validate(environment) for environment in environments
        ],
        flag_count=sum(1 for flag in project.flags if not flag.archived),
        updated_at=latest_flag,
    )


def _serialize_organization(organization: Organization) -> OrganizationResponse:
    projects = sorted(organization.projects, key=lambda project: (project.created_at, project.name))
    return OrganizationResponse(
        id=organization.id,
        name=organization.name,
        description=organization.description,
        owner_id=organization.owner_id,
        created_at=organization.created_at,
        projects=[_serialize_project(project) for project in projects],
    )


@router.post("", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
async def create_organization(
    data: OrganizationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = await db.execute(select(Organization).where(Organization.name == data.name))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Organization with name '{data.name}' already exists",
        )

    organization = Organization(
        name=data.name,
        description=data.description,
        owner_id=current_user.id,
    )
    db.add(organization)
    await db.commit()

    result = await db.execute(
        _organizations_with_projects(current_user.id).where(Organization.id == organization.id)
    )
    return _serialize_organization(result.scalar_one())


@router.get("", response_model=List[OrganizationResponse])
async def list_organizations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        _organizations_with_projects(current_user.id).order_by(Organization.created_at.asc())
    )
    return [_serialize_organization(organization) for organization in result.scalars().all()]


@router.get("/{org_id}", response_model=OrganizationResponse)
async def get_organization(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    organization = await get_organization_or_404(db, org_id, current_user.id)
    result = await db.execute(
        _organizations_with_projects(current_user.id).where(Organization.id == organization.id)
    )
    return _serialize_organization(result.scalar_one())


@router.post(
    "/{org_id}/projects",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_project(
    org_id: str,
    data: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    organization = await get_organization_or_404(db, org_id, current_user.id)

    existing = await db.execute(
        select(Project).where(Project.org_id == organization.id, Project.name == data.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Project with name '{data.name}' already exists in this organization",
        )

    project = Project(org_id=organization.id, name=data.name)
    db.add(project)
    await db.flush()

    # Auto-provision the standard environments for the new project.
    await provision_standard_environments(db, project.id)

    db.add(
        AuditLog(
            org_id=organization.id,
            project_id=project.id,
            actor=current_user.email,
            user_id=current_user.id,
            user_email=current_user.email,
            action="project.created",
            after={"name": project.name},
        )
    )
    await db.commit()

    result = await db.execute(
        select(Project)
        .where(Project.id == project.id)
        .options(
            selectinload(Project.environments),
            selectinload(Project.flags),
        )
    )
    return _serialize_project(result.scalar_one())
