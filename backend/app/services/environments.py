"""
Environment lifecycle business logic.

- Provisioning of the standard environments for a new project.
- Seeding per-flag/per-environment state rows so every flag is manageable
  in every environment of its project.
- Cache version invalidation: the bootstrap ETag is derived from
  `Environment.version`, so every mutation that changes an environment's
  flag snapshot must bump that counter, which also evicts the Redis snapshot.
"""
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Environment, Flag, FlagEnvState
from app.services.snapshots import invalidate_env_snapshots

STANDARD_ENVIRONMENTS: tuple[str, ...] = ("dev", "staging", "prod")


def environment_sort_key(name: str) -> tuple[int, str]:
    """Standard environments first (dev, staging, prod), custom ones alphabetically after."""
    standard_order = {env_name: index for index, env_name in enumerate(STANDARD_ENVIRONMENTS)}
    return standard_order.get(name, len(standard_order)), name


def sort_environments(environments: Iterable[Environment]) -> list[Environment]:
    """Returns environments in a deterministic display order."""
    return sorted(environments, key=lambda environment: environment_sort_key(environment.name))


async def provision_standard_environments(db: AsyncSession, project_id: str) -> list[Environment]:
    """Creates the standard dev / staging / prod environments for a new project."""
    environments = [
        Environment(project_id=project_id, name=name, version=1) for name in STANDARD_ENVIRONMENTS
    ]
    db.add_all(environments)
    await db.flush()
    return environments


async def seed_missing_flag_states(db: AsyncSession, project_id: str) -> None:
    """
    Creates any missing `FlagEnvState` rows for every flag x environment
    combination within a project. Safe to call repeatedly (idempotent).
    """
    env_names = (
        await db.execute(select(Environment.name).where(Environment.project_id == project_id))
    ).scalars().all()
    flag_ids = (
        await db.execute(select(Flag.id).where(Flag.project_id == project_id))
    ).scalars().all()

    if not env_names or not flag_ids:
        return

    rows = (
        await db.execute(
            select(FlagEnvState.flag_id, FlagEnvState.env).where(FlagEnvState.flag_id.in_(flag_ids))
        )
    ).all()
    existing = {(row[0], row[1]) for row in rows}

    for flag_id in flag_ids:
        for env_name in env_names:
            if (flag_id, env_name) not in existing:
                db.add(
                    FlagEnvState(
                        flag_id=flag_id,
                        env=env_name,
                        enabled=True,
                        percentage=0,
                        version=1,
                    )
                )
    await db.flush()


async def bump_environment_versions(
    db: AsyncSession,
    project_id: str,
    env_names: Optional[Iterable[str]] = None,
) -> None:
    """
    Increments the cache version of a project's environments so that SDK
    clients polling `/bootstrap` with `If-None-Match` receive a fresh snapshot,
    and drops the matching Redis snapshot entries.

    When `env_names` is omitted, every environment of the project is bumped.

    This is the single invalidation hook for environment snapshots: every
    mutation that changes flag state or targeting rules routes through here, so
    the cached snapshot can never outlive the version it was built from.
    """
    stmt = select(Environment).where(Environment.project_id == project_id)
    names: Optional[list[str]] = None
    if env_names is not None:
        names = list(env_names)
        stmt = stmt.where(Environment.name.in_(names))

    res = await db.execute(stmt)
    for environment in res.scalars().all():
        environment.version += 1

    await invalidate_env_snapshots(project_id, names)
