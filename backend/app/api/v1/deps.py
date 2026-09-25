from typing import Optional, Union

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose.exceptions import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.db import get_db
from app.core.security import decode_token, unauthorized
from app.models.models import ApiKey, Environment, Organization, Project, User


oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login",
    auto_error=False,
)


async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the bearer access token for every protected API route."""
    if not token:
        raise unauthorized()

    try:
        payload = decode_token(token, expected_type="access")
    except JWTError as exc:
        raise unauthorized("Invalid or expired access token") from exc

    result = await db.execute(select(User).where(User.id == payload["sub"]))
    user = result.scalar_one_or_none()
    if user is None:
        raise unauthorized("User account no longer exists")
    return user


async def get_organization_or_404(
    db: AsyncSession,
    org_id: str,
    owner_id: str,
) -> Organization:
    stmt = select(Organization).where(
        Organization.id == org_id,
        Organization.owner_id == owner_id,
    )
    result = await db.execute(stmt)
    organization = result.scalar_one_or_none()
    if not organization:
        # Deliberately use the same response for missing and inaccessible
        # resources so organization IDs cannot be enumerated.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return organization


async def get_project_or_404(
    db: AsyncSession,
    project_id: str,
    owner_id: str,
) -> Project:
    stmt = (
        select(Project)
        .join(Organization, Project.org_id == Organization.id)
        .where(
            Project.id == project_id,
            Organization.owner_id == owner_id,
        )
    )
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    if not project:
        # Keep project access scoped to the owning organization while
        # preserving the Phase 1 unknown-project 404 behavior.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


async def get_environment_or_404(
    db: AsyncSession,
    project_id: str,
    env_name: str,
    owner_id: str,
) -> Environment:
    stmt = (
        select(Environment)
        .join(Project, Environment.project_id == Project.id)
        .join(Organization, Project.org_id == Organization.id)
        .where(
            Environment.project_id == project_id,
            Environment.name == env_name,
            Organization.owner_id == owner_id,
        )
    )
    result = await db.execute(stmt)
    environment = result.scalar_one_or_none()
    if not environment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Environment '{env_name}' not found in this project",
        )
    return environment


# SDK Key Authentication
# The SDK sends the full API key (which is the prefix we generate) in the X-SDK-Key header


async def get_sdk_key_from_header(request: Request) -> Optional[str]:
    """Extract the API key from the X-SDK-Key header."""
    return request.headers.get("X-SDK-Key")


async def get_current_sdk_key_or_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> Union[ApiKey, User]:
    """Authenticate using either X-SDK-Key (SDK) or Bearer token (user).

    Returns the Authenticated entity (ApiKey for SDK, User for web) or raises 401.

    Use this for endpoints that should accept both SDK and user authentication
    (e.g., /bootstrap, /evaluate).
    """
    # First, try SDK key authentication
    sdk_key = request.headers.get("X-SDK-Key")
    if sdk_key:
        from app.services.api_keys import get_api_key_by_prefix

        api_key = await get_api_key_by_prefix(db, sdk_key)

        if not api_key:
            # Return 404 instead of 401 to avoid key enumeration
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API key not found",
            )

        if api_key.revoked:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key has been revoked",
            )

        # Load the project and organization to get the owner_id
        stmt = (
            select(ApiKey)
            .where(ApiKey.id == api_key.id)
            .options(selectinload(ApiKey.project).selectinload(Project.organization))
        )
        result = await db.execute(stmt)
        updated_key = result.scalar_one_or_none()
        if updated_key and updated_key.project and updated_key.project.organization:
            api_key.organization_owner_id = updated_key.project.organization.owner_id

        return api_key

    # Fall back to user authentication
    if not token:
        raise unauthorized()

    try:
        payload = decode_token(token, expected_type="access")
    except JWTError as exc:
        raise unauthorized("Invalid or expired access token") from exc

    result = await db.execute(select(User).where(User.id == payload["sub"]))
    user = result.scalar_one_or_none()
    if user is None:
        raise unauthorized("User account no longer exists")

    return user
