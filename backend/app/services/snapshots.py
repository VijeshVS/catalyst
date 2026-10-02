"""
Environment flag snapshots, read through Redis.

`/bootstrap` and `/evaluate` both need the same thing: the resolved flags,
states and rules of one project environment. Building that from PostgreSQL costs
a join over every flag plus its states and rules, which is wasted work when the
environment has not changed.

So the snapshot is cached in Redis under `catalyst:snapshot:<project>:<env>` and
validated against `Environment.version`, which is already the source of truth
for the bootstrap ETag. Every mutation that changes a snapshot calls
`bump_environment_versions`, which bumps that counter and drops the cache entry,
so a stale hit is not something the cache can produce on its own. The TTL is only
a backstop for the case where a mutation forgot to bump the version.

Redis being absent or broken is a supported state: the snapshot is rebuilt from
PostgreSQL and the request proceeds.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.cache import cache_delete, cache_get_json, cache_set_json, snapshot_key
from app.core.config import settings
from app.models.models import Flag

logger = logging.getLogger(__name__)

#: Reported in the `X-Catalyst-Cache` response header so cache behaviour is
#: observable from a client or a test without reaching into Redis.
SOURCE_REDIS = "redis"
SOURCE_POSTGRES = "postgres"


@dataclass(frozen=True)
class EnvSnapshot:
    """Resolved flags of a single project environment."""

    project_id: str
    env: str
    version: int
    flags: Dict[str, Any]
    source: str = SOURCE_POSTGRES

    @property
    def etag(self) -> str:
        return build_etag(self.project_id, self.env, self.version)

    def to_payload(self) -> Dict[str, Any]:
        """The `/bootstrap` response body."""
        return {"env": self.env, "version": self.version, "flags": self.flags}

    def to_cache_entry(self) -> Dict[str, Any]:
        return {"version": self.version, "flags": self.flags}

    @classmethod
    def from_cache_entry(
        cls,
        entry: Any,
        project_id: str,
        env: str,
        version: int,
    ) -> Optional["EnvSnapshot"]:
        """
        Rebuilds a snapshot from a cache entry, or ``None`` if it is unusable.

        The version comparison is the correctness guard: an entry written before
        the last mutation is a miss, not a stale read.
        """
        if not isinstance(entry, dict):
            return None
        if entry.get("version") != version:
            return None
        flags = entry.get("flags")
        if not isinstance(flags, dict):
            return None
        return cls(
            project_id=project_id,
            env=env,
            version=version,
            flags=flags,
            source=SOURCE_REDIS,
        )


def build_etag(project_id: str, env: str, version: int) -> str:
    return f'W/"{project_id}:{env}:{version}"'


def _flag_entry(flag: Flag, env: str) -> Dict[str, Any]:
    """Resolves one flag row plus its state and rules for a single environment."""
    state = next((candidate for candidate in flag.states if candidate.env == env), None)
    rules = [
        {
            "id": rule.id,
            "priority": rule.priority,
            "conditions": rule.conditions_json,
            "serve": rule.serve,
        }
        for rule in sorted(flag.rules, key=lambda item: item.priority)
        if rule.env == env
    ]
    return {
        "key": flag.key,
        "enabled": state.enabled if state else True,
        "enableAll": state.enable_all if state else False,
        "percentage": state.percentage if state else 100,
        "rules": rules,
    }


async def _build_from_postgres(db: AsyncSession, project_id: str, env: str) -> Dict[str, Any]:
    stmt = (
        select(Flag)
        .where(Flag.project_id == project_id)
        .options(selectinload(Flag.states), selectinload(Flag.rules))
    )
    result = await db.execute(stmt)
    return {flag.key: _flag_entry(flag, env) for flag in result.scalars().all()}


async def load_env_snapshot(
    db: AsyncSession,
    project_id: str,
    env: str,
    version: int,
) -> EnvSnapshot:
    """
    Returns the snapshot of one project environment, from Redis when possible.

    `version` must be the caller's already-loaded `Environment.version`; it both
    validates the cached entry and labels a freshly built one.
    """
    key = snapshot_key(project_id, env)

    if settings.SNAPSHOT_CACHE_ENABLED:
        cached = EnvSnapshot.from_cache_entry(
            await cache_get_json(key), project_id, env, version
        )
        if cached is not None:
            return cached

    flags = await _build_from_postgres(db, project_id, env)
    snapshot = EnvSnapshot(
        project_id=project_id,
        env=env,
        version=version,
        flags=flags,
        source=SOURCE_POSTGRES,
    )

    if settings.SNAPSHOT_CACHE_ENABLED:
        await cache_set_json(key, snapshot.to_cache_entry(), ttl=settings.SNAPSHOT_CACHE_TTL)

    return snapshot


async def invalidate_env_snapshots(project_id: str, env_names: Optional[list[str]] = None) -> int:
    """
    Drops cached snapshots for a project's environments.

    Called alongside `bump_environment_versions` so the next read repopulates the
    cache. The version bump alone would already be enough; deleting eagerly just
    avoids serving one stale entry to the first reader after a mutation.
    """
    names = list(env_names) if env_names is not None else None
    if names is not None and not names:
        return 0
    if names is None:
        # No environment filter: drop whatever is cached for the project. The key
        # layout makes this a bounded pattern for a single project, and it only
        # runs on the rare "invalidate everything" path (flag creation).
        client_keys = await _scan_project_keys(project_id)
        return await cache_delete(client_keys)

    return await cache_delete(snapshot_key(project_id, name) for name in names)


async def _scan_project_keys(project_id: str) -> list[str]:
    """Finds every cached snapshot key belonging to one project."""
    from app.core.cache import KEY_PREFIX, get_redis

    client = await get_redis()
    if client is None:
        return []
    pattern = f"{KEY_PREFIX}:snapshot:{project_id}:*"
    try:
        return [key async for key in client.scan_iter(match=pattern, count=100)]
    except Exception as e:  # noqa: BLE001 - invalidation is best effort
        logger.warning("could not scan snapshot keys for project %s: %s", project_id, e)
        return []
