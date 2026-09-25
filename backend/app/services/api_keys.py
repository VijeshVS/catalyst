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
    random_bytes = secrets.token_bytes(16)
    random_part = secrets.token_urlsafe(16)[:22]
    return f"cp_{env}_{random_part}"


def hash_api_key(raw_key: str) -> str:
    """Hash an API key using SHA-256 for secure storage.

    Only the hash is stored in the database; the raw key is returned once
    upon creation and never stored.
    """
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def verify_api_key(raw_key: str, stored_hash: str) -> bool:
    """Verify a raw API key against its stored hash.

    Uses constant-time comparison to prevent timing attacks.
    """
    computed_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    return secrets.compare_digest(computed_hash, stored_hash)


async def create_api_key(
    db: AsyncSession,
    project_id: str,
    env: str,
    name: str,
    user_id: str,
    user_email: str,
) -> tuple[str, ApiKey]:
    """Create a new API key for a project environment.

    Returns:
        tuple: (raw_key, api_key_object)
        The raw_key must be returned to the user immediately and never stored.
    """
    # Generate the full secret key
    raw_key = generate_api_key_prefix(env)
    
    # Extract just the prefix for display (first 12 chars to show cp_env_abc...)
    # This is what we store and show in the list - NOT the full key
    display_prefix = raw_key[:12] if len(raw_key) > 12 else raw_key

    # Hash the full key for authentication
    key_hash = hash_api_key(raw_key)

    api_key = ApiKey(
        project_id=project_id,
        env=env,
        name=name,
        prefix=display_prefix,  # Only store the short prefix for display
        hash=key_hash,
        revoked=False,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    return raw_key, api_key


async def get_api_key_by_raw_key(db: AsyncSession, raw_key: str) -> Optional[ApiKey]:
    """Retrieve an API key by its raw key (via SHA-256 hash) or display prefix."""
    key_hash = hash_api_key(raw_key)
    stmt = select(ApiKey).where(ApiKey.hash == key_hash)
    result = await db.execute(stmt)
    key = result.scalar_one_or_none()
    if key:
        return key

    # Fallback to direct prefix match
    stmt = select(ApiKey).where(ApiKey.prefix == raw_key)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_api_key_by_prefix(db: AsyncSession, prefix: str) -> Optional[ApiKey]:
    """Retrieve an API key by raw key or prefix."""
    return await get_api_key_by_raw_key(db, prefix)


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


async def revoke_api_key(db: AsyncSession, key_id: str) -> bool:
    """Revoke an API key by ID.

    Returns:
        True if a key was revoked, False if no key found
    """
    stmt = select(ApiKey).where(ApiKey.id == key_id)
    result = await db.execute(stmt)
    api_key = result.scalar_one_or_none()

    if api_key:
        api_key.revoked = True
        await db.commit()
        return True

    return False


async def get_api_key_or_404(db: AsyncSession, key_id: str) -> ApiKey:
    """Get an API key or raise 404 if not found."""
    stmt = select(ApiKey).where(ApiKey.id == key_id)
    result = await db.execute(stmt)
    api_key = result.scalar_one_or_none()
    if not api_key:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )
    return api_key
