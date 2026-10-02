"""API Key generation, hashing, and management service."""

import hashlib
import secrets
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import ApiKey


def generate_api_key_prefix(env: str) -> str:
    """Generate a deterministic API key prefix: cp_<env>_<random32>.

    Format: cp_<env>_<base64url-encode(random_bytes(16))>
    This produces: cp_<env>_<22-char-base64url-string>
    Example: cp_prod_a1b2c3d4e5f6g7h8i9j0k1
    """
    random_part = secrets.token_urlsafe(16)[:22]
    return f"cp_{env}_{random_part}"


def hash_api_key(raw_key: str) -> str:
    """Hash an API key using SHA-256 for secure storage.

    Only the hash is stored in the database; the raw key is returned once
    upon creation and never stored.
    """
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


async def create_api_key(
    db: AsyncSession,
    project_id: str,
    env: str,
    name: str,
) -> tuple[str, ApiKey]:
    """Create a new API key for a project environment.

    Returns:
        tuple: (raw_key, api_key_object)
        The raw_key must be returned to the user immediately and never stored.
    """
    raw_key = generate_api_key_prefix(env)

    key_hash = hash_api_key(raw_key)

    api_key = ApiKey(
        project_id=project_id,
        env=env,
        name=name,
        # A non-secret label for operators. Authentication never reads it.
        prefix=raw_key[:12],
        hash=key_hash,
        revoked=False,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    return raw_key, api_key


async def get_api_key_by_raw_key(db: AsyncSession, raw_key: str) -> Optional[ApiKey]:
    """Resolve a presented API key to its stored row, by hash only.

    The stored ``prefix`` is a non-secret display label and is deliberately
    never matched here: a label that authenticates is a public credential.
    """
    key_hash = hash_api_key(raw_key)
    stmt = select(ApiKey).where(ApiKey.hash == key_hash)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_api_keys(
    db: AsyncSession,
    project_id: str,
    active_only: bool = True,
) -> list[ApiKey]:
    """List all API keys for a project.

    Args:
        db: Database session
        project_id: Project ID to filter by
        active_only: If True, only return non-revoked keys

    Returns:
        List of API keys ordered by creation date (newest first)
    """
    stmt = select(ApiKey).where(
        ApiKey.project_id == project_id,
    )
    if active_only:
        stmt = stmt.where(ApiKey.revoked == False)
    stmt = stmt.order_by(ApiKey.created_at.desc())
    result = await db.execute(stmt)
    return result.scalars().all()
