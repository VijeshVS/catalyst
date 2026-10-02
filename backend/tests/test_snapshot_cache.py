"""
Tests for the Redis snapshot cache that `/bootstrap` and `/evaluate` read
through.

The suite runs without a Redis server, so a small in-memory fake stands in for
the client. That keeps the tests self-contained while still exercising the real
code paths: version validation on read, invalidation on mutation, and graceful
degradation when Redis is unavailable or broken.
"""

from __future__ import annotations

import json

import pytest

from app.core import cache as cache_module
from app.core.db import async_session_maker
from app.services.snapshots import (
    SOURCE_POSTGRES,
    SOURCE_REDIS,
    build_etag,
    load_env_snapshot,
)

API = "/api/v1"


class FakeRedis:
    """Minimal async Redis stand-in covering the commands the cache layer uses."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.gets = 0
        self.sets = 0
        self.deletes = 0
        self.broken = False

    async def get(self, key: str):
        self._check()
        self.gets += 1
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None):
        self._check()
        self.sets += 1
        self.store[key] = value
        return True

    async def delete(self, *keys: str) -> int:
        self._check()
        self.deletes += 1
        removed = 0
        for key in keys:
            if self.store.pop(key, None) is not None:
                removed += 1
        return removed

    async def ping(self):
        self._check()
        return True

    async def scan_iter(self, match: str, count: int = 100):
        self._check()
        prefix = match.rstrip("*")
        for key in list(self.store):
            if key.startswith(prefix):
                yield key

    def _check(self):
        if self.broken:
            raise ConnectionError("redis is down")


@pytest.fixture
def fake_redis(monkeypatch):
    """Installs a fake Redis as the process-wide client for one test."""
    fake = FakeRedis()
    monkeypatch.setattr(cache_module, "redis_client", fake)
    return fake


@pytest.fixture
def no_redis(monkeypatch):
    """Simulates a deployment where Redis was never reachable."""
    monkeypatch.setattr(cache_module, "redis_client", None)


async def create_org_project_flag(client, name: str) -> tuple[str, str]:
    org = await client.post(f"{API}/organizations", json={"name": f"{name} Org"})
    assert org.status_code == 201, org.text
    project = await client.post(
        f"{API}/organizations/{org.json()['id']}/projects", json={"name": f"{name} Project"}
    )
    assert project.status_code == 201, project.text
    flag = await client.post(
        f"{API}/flags?project_id={project.json()['id']}",
        json={"key": "ai-assistant", "name": "AI Assistant"},
    )
    assert flag.status_code == 201, flag.text
    return project.json()["id"], flag.json()["key"]


async def get_bootstrap(client, project_id: str, env: str = "prod"):
    return await client.get(f"{API}/bootstrap?project_id={project_id}&env={env}")


# ---------------------------------------------------------------------------
# Cache hits and misses
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_snapshot_is_cached_and_reused(client, fake_redis):
    project_id, _ = await create_org_project_flag(client, "Cache Reuse")

    first = await get_bootstrap(client, project_id)
    assert first.status_code == 200, first.text
    assert first.headers["X-Catalyst-Cache"] == SOURCE_POSTGRES
    assert first.headers["ETag"] == build_etag(project_id, "prod", first.json()["version"])
    assert cache_module.snapshot_key(project_id, "prod") in fake_redis.store

    second = await get_bootstrap(client, project_id)
    assert second.status_code == 200
    assert second.headers["X-Catalyst-Cache"] == SOURCE_REDIS, "second read must hit Redis"
    assert second.json() == first.json(), "a cache hit must return the identical snapshot"
    assert fake_redis.sets == 1, "a hit must not rewrite the entry"


@pytest.mark.asyncio
async def test_environments_are_cached_independently(client, fake_redis):
    project_id, _ = await create_org_project_flag(client, "Cache Per Env")

    await get_bootstrap(client, project_id, "prod")
    await get_bootstrap(client, project_id, "staging")

    assert cache_module.snapshot_key(project_id, "prod") in fake_redis.store
    assert cache_module.snapshot_key(project_id, "staging") in fake_redis.store

    dev = await get_bootstrap(client, project_id, "dev")
    assert dev.headers["X-Catalyst-Cache"] == SOURCE_POSTGRES, "dev was never cached"


@pytest.mark.asyncio
async def test_cached_entry_for_a_stale_version_is_ignored(client, fake_redis):
    project_id, flag_key = await create_org_project_flag(client, "Cache Stale Version")

    await get_bootstrap(client, project_id)
    # An entry written before the last version bump, with a value that would be
    # visible if the version check were ever skipped.
    fake_redis.store[cache_module.snapshot_key(project_id, "prod")] = json.dumps(
        {
            "version": 0,
            "flags": {
                flag_key: {
                    "key": flag_key,
                    "enabled": False,
                    "enableAll": False,
                    "percentage": 0,
                    "rules": [],
                }
            },
        }
    )

    res = await get_bootstrap(client, project_id)
    assert res.status_code == 200
    assert res.headers["X-Catalyst-Cache"] == SOURCE_POSTGRES, "a stale entry must be rebuilt"
    assert res.json()["flags"][flag_key]["enabled"] is True


# ---------------------------------------------------------------------------
# Invalidation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_rollout_change_invalidates_the_cached_snapshot(client, fake_redis):
    project_id, flag_key = await create_org_project_flag(client, "Cache Invalidate Rollout")
    await get_bootstrap(client, project_id)
    assert fake_redis.store[cache_module.snapshot_key(project_id, "prod")]

    patch = await client.patch(
        f"{API}/flags/{flag_key}/environments/prod?project_id={project_id}",
        json={"percentage": 100},
    )
    assert patch.status_code == 200, patch.text
    assert cache_module.snapshot_key(project_id, "prod") not in fake_redis.store

    res = await get_bootstrap(client, project_id)
    assert res.headers["X-Catalyst-Cache"] == SOURCE_POSTGRES
    assert res.json()["flags"][flag_key]["percentage"] == 100


@pytest.mark.asyncio
async def test_rule_change_invalidates_only_its_environment(client, fake_redis):
    project_id, flag_key = await create_org_project_flag(client, "Cache Invalidate Rules")
    await get_bootstrap(client, project_id, "prod")
    await get_bootstrap(client, project_id, "staging")

    rule = await client.post(
        f"{API}/flags/{flag_key}/environments/prod/rules?project_id={project_id}",
        json={"conditions": [{"attr": "plan", "op": "equals", "value": "pro"}], "serve": True},
    )
    assert rule.status_code == 201, rule.text

    assert cache_module.snapshot_key(project_id, "prod") not in fake_redis.store
    assert cache_module.snapshot_key(project_id, "staging") in fake_redis.store, (
        "a prod mutation must not evict the staging snapshot"
    )

    refreshed = await get_bootstrap(client, project_id, "prod")
    assert refreshed.json()["flags"][flag_key]["rules"][0]["id"] == rule.json()["id"]


@pytest.mark.asyncio
async def test_flag_creation_invalidates_every_environment(client, fake_redis):
    project_id, _ = await create_org_project_flag(client, "Cache Invalidate All")
    await get_bootstrap(client, project_id, "prod")
    await get_bootstrap(client, project_id, "staging")

    created = await client.post(
        f"{API}/flags?project_id={project_id}",
        json={"key": "new-checkout", "name": "New Checkout"},
    )
    assert created.status_code == 201, created.text

    for env in ("prod", "staging"):
        res = await get_bootstrap(client, project_id, env)
        assert "new-checkout" in res.json()["flags"], f"{env} served a stale snapshot"


# ---------------------------------------------------------------------------
# Evaluation reads through the same cache
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_evaluate_serves_from_the_cached_snapshot(client, fake_redis):
    project_id, flag_key = await create_org_project_flag(client, "Cache Evaluate")
    await client.patch(
        f"{API}/flags/{flag_key}/environments/prod?project_id={project_id}",
        json={"percentage": 100},
    )

    body = {"flag_key": flag_key, "env": "prod", "context": {"user_id": "user_123"}}
    first = await client.post(f"{API}/evaluate?project_id={project_id}", json=body)
    assert first.status_code == 200, first.text
    assert first.headers["X-Catalyst-Cache"] == SOURCE_POSTGRES
    assert first.json()["value"] is True
    assert first.json()["reason"] == "PERCENTAGE_ROLLOUT"

    second = await client.post(f"{API}/evaluate?project_id={project_id}", json=body)
    assert second.headers["X-Catalyst-Cache"] == SOURCE_REDIS
    assert second.json() == first.json()

    batch = await client.post(
        f"{API}/batch-evaluate?project_id={project_id}",
        json={"env": "prod", "context": {"user_id": "user_123"}},
    )
    assert batch.status_code == 200, batch.text
    assert batch.json()["evaluations"][flag_key]["value"] is True


@pytest.mark.asyncio
async def test_evaluate_reports_a_missing_flag(client, fake_redis):
    project_id, _ = await create_org_project_flag(client, "Cache Evaluate Missing")
    await get_bootstrap(client, project_id)

    res = await client.post(
        f"{API}/evaluate?project_id={project_id}",
        json={"flag_key": "nope", "env": "prod", "context": {"user_id": "u1"}},
    )
    assert res.status_code == 200, res.text
    assert res.json() == {"flag_key": "nope", "value": False, "reason": "FLAG_NOT_FOUND", "rule_id": None}


# ---------------------------------------------------------------------------
# Degradation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_endpoints_work_without_redis(client, no_redis):
    project_id, flag_key = await create_org_project_flag(client, "No Redis")
    await client.patch(
        f"{API}/flags/{flag_key}/environments/prod?project_id={project_id}",
        json={"percentage": 100},
    )

    res = await get_bootstrap(client, project_id)
    assert res.status_code == 200, res.text
    assert res.headers["X-Catalyst-Cache"] == SOURCE_POSTGRES
    assert res.json()["flags"][flag_key]["percentage"] == 100

    evaluation = await client.post(
        f"{API}/evaluate?project_id={project_id}",
        json={"flag_key": flag_key, "env": "prod", "context": {"user_id": "user_123"}},
    )
    assert evaluation.status_code == 200, evaluation.text
    assert evaluation.json()["value"] is True


@pytest.mark.asyncio
async def test_a_broken_redis_does_not_fail_requests(client, fake_redis):
    project_id, flag_key = await create_org_project_flag(client, "Broken Redis")
    await get_bootstrap(client, project_id)

    fake_redis.broken = True
    res = await get_bootstrap(client, project_id)
    assert res.status_code == 200, "a cache outage must not become a 500"
    assert res.headers["X-Catalyst-Cache"] == SOURCE_POSTGRES
    assert flag_key in res.json()["flags"]

    evaluation = await client.post(
        f"{API}/evaluate?project_id={project_id}",
        json={"flag_key": flag_key, "env": "prod", "context": {"user_id": "user_123"}},
    )
    assert evaluation.status_code == 200, evaluation.text


@pytest.mark.asyncio
async def test_unreadable_cache_entry_is_treated_as_a_miss(client, fake_redis):
    project_id, flag_key = await create_org_project_flag(client, "Corrupt Cache")
    key = cache_module.snapshot_key(project_id, "prod")
    fake_redis.store[key] = "{not json"

    res = await get_bootstrap(client, project_id)
    assert res.status_code == 200, res.text
    assert res.headers["X-Catalyst-Cache"] == SOURCE_POSTGRES
    assert flag_key in res.json()["flags"]


@pytest.mark.asyncio
async def test_cache_can_be_disabled_by_settings(client, fake_redis, monkeypatch):
    project_id, _ = await create_org_project_flag(client, "Cache Disabled")
    monkeypatch.setattr("app.services.snapshots.settings.SNAPSHOT_CACHE_ENABLED", False)

    await get_bootstrap(client, project_id)
    assert fake_redis.store == {}, "nothing should be written when the cache is off"

    res = await get_bootstrap(client, project_id)
    assert res.headers["X-Catalyst-Cache"] == SOURCE_POSTGRES


# ---------------------------------------------------------------------------
# 304 fast path
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_conditional_request_short_circuits_before_the_snapshot(client, fake_redis):
    project_id, _ = await create_org_project_flag(client, "Cache 304")
    first = await get_bootstrap(client, project_id)
    etag = first.headers["ETag"]

    fake_redis.gets = 0
    not_modified = await client.get(
        f"{API}/bootstrap?project_id={project_id}&env=prod", headers={"If-None-Match": etag}
    )
    assert not_modified.status_code == 304
    assert not_modified.headers["ETag"] == etag
    assert fake_redis.gets == 0, "a 304 must not read the snapshot at all"


# ---------------------------------------------------------------------------
# Service-level unit checks
# ---------------------------------------------------------------------------
def test_from_cache_entry_rejects_a_version_mismatch():
    from app.services.snapshots import EnvSnapshot

    entry = {"version": 4, "flags": {"a": {"key": "a"}}}
    assert EnvSnapshot.from_cache_entry(entry, "p1", "prod", 4) is not None
    assert EnvSnapshot.from_cache_entry(entry, "p1", "prod", 5) is None
    assert EnvSnapshot.from_cache_entry({"version": 4}, "p1", "prod", 4) is None
    assert EnvSnapshot.from_cache_entry("nonsense", "p1", "prod", 4) is None
    assert EnvSnapshot.from_cache_entry(None, "p1", "prod", 4) is None


@pytest.mark.asyncio
async def test_load_env_snapshot_reports_its_source(client, fake_redis, monkeypatch):
    """Direct service call, so the snapshot contract is tested without HTTP."""
    import app.services.snapshots as snapshots_module

    project_id, flag_key = await create_org_project_flag(client, "Cache Service")

    calls = {"n": 0}
    original = snapshots_module._build_from_postgres

    async def counting_build(db, pid, env):
        calls["n"] += 1
        return await original(db, pid, env)

    monkeypatch.setattr(snapshots_module, "_build_from_postgres", counting_build)

    async with async_session_maker() as db:
        first = await load_env_snapshot(db, project_id, "prod", 1)
        assert first.source == SOURCE_POSTGRES
        assert first.flags[flag_key]["enabled"] is True
        assert first.to_payload() == {"env": "prod", "version": 1, "flags": first.flags}

        second = await load_env_snapshot(db, project_id, "prod", 1)
        assert second.source == SOURCE_REDIS
        assert calls["n"] == 1, "the second read must not touch PostgreSQL"
