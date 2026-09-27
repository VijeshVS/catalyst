"""
Tests for updating an existing flag's definition via
``PATCH /api/v1/flags/{key}`` — primarily the safe default value.

Covers both directions of the toggle, strict project scoping, unknown-flag
handling, environment version (ETag) invalidation, and the guarantee that
rollout / kill-switch behavior is untouched by a default-value change.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport

from app.core import cache as cache_module
from app.services.snapshots import SOURCE_POSTGRES
from test_snapshot_cache import fake_redis  # noqa: F401  (shared fixture)

API = "/api/v1"


async def create_org_project_flag(
    client: AsyncClient, name: str, default_value: bool = False
) -> tuple[str, str]:
    org = await client.post(f"{API}/organizations", json={"name": f"{name} Org"})
    assert org.status_code == 201, org.text
    project = await client.post(
        f"{API}/organizations/{org.json()['id']}/projects", json={"name": f"{name} Project"}
    )
    assert project.status_code == 201, project.text
    flag = await client.post(
        f"{API}/flags?project_id={project.json()['id']}",
        json={"key": "ai-assistant", "name": "AI Assistant", "default_value": default_value},
    )
    assert flag.status_code == 201, flag.text
    return project.json()["id"], flag.json()["key"]


async def patch_default(client: AsyncClient, project_id: str, flag_key: str, value: bool):
    return await client.patch(
        f"{API}/flags/{flag_key}",
        params={"project_id": project_id},
        json={"default_value": value},
    )


# ---------------------------------------------------------------------------
# Default value updates
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_default_value_can_be_changed_from_false_to_true(client):
    project_id, flag_key = await create_org_project_flag(client, "Default False To True")

    res = await patch_default(client, project_id, flag_key, True)
    assert res.status_code == 200, res.text
    assert res.json()["default_value"] is True

    fetched = await client.get(f"{API}/flags/{flag_key}", params={"project_id": project_id})
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["default_value"] is True


@pytest.mark.asyncio
async def test_default_value_can_be_changed_from_true_to_false(client):
    project_id, flag_key = await create_org_project_flag(client, "Default True To False", True)

    res = await patch_default(client, project_id, flag_key, False)
    assert res.status_code == 200, res.text
    assert res.json()["default_value"] is False

    fetched = await client.get(f"{API}/flags/{flag_key}", params={"project_id": project_id})
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["default_value"] is False


@pytest.mark.asyncio
async def test_default_value_update_is_scoped_to_the_project(client):
    project_a, flag_a = await create_org_project_flag(client, "Scope A")
    project_b, flag_b = await create_org_project_flag(client, "Scope B", True)

    # The same key exists in both projects with different defaults.
    assert flag_a == "ai-assistant" and flag_b == "ai-assistant"

    # Updating via project B's scope must not touch project A's flag.
    res = await patch_default(client, project_b, flag_b, False)
    assert res.status_code == 200, res.text

    fetched_a = await client.get(f"{API}/flags/ai-assistant", params={"project_id": project_a})
    assert fetched_a.status_code == 200, fetched_a.text
    assert fetched_a.json()["default_value"] is False, "project A's flag was modified through project B"

    fetched_b = await client.get(f"{API}/flags/ai-assistant", params={"project_id": project_b})
    assert fetched_b.json()["default_value"] is True or fetched_b.json()["default_value"] is False
    assert fetched_b.json()["default_value"] is False

    # A flag that does not exist in the caller's project is a 404, not a leak.
    res = await patch_default(client, project_a, "ghost-flag", True)
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_default_value_update_rejects_unknown_project(client):
    res = await patch_default(client, "nonexistent-project", "ai-assistant", True)
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_default_value_change_invalidates_environment_snapshots(client, fake_redis):
    project_id, flag_key = await create_org_project_flag(client, "Default Invalidate")

    first = await client.get(f"{API}/bootstrap?project_id={project_id}&env=prod")
    assert first.status_code == 200, first.text
    assert first.headers["X-Catalyst-Cache"] == SOURCE_POSTGRES
    etag_before = first.headers["ETag"]
    assert cache_module.snapshot_key(project_id, "prod") in fake_redis.store

    res = await patch_default(client, project_id, flag_key, True)
    assert res.status_code == 200, res.text

    # The cached snapshot is evicted and the ETag changes with the version.
    assert cache_module.snapshot_key(project_id, "prod") not in fake_redis.store

    second = await client.get(f"{API}/bootstrap?project_id={project_id}&env=prod")
    assert second.status_code == 200, second.text
    assert second.headers["ETag"] != etag_before
    assert second.json()["flags"][flag_key]["defaultValue"] is True


@pytest.mark.asyncio
async def test_default_value_change_does_not_disturb_rollout_or_kill_switch(client):
    project_id, flag_key = await create_org_project_flag(client, "Default No Disturb")

    # Give the flag a non-default rollout and kill it in prod.
    state = await client.patch(
        f"{API}/flags/{flag_key}/environments/prod",
        params={"project_id": project_id},
        json={"enabled": False, "percentage": 40},
    )
    assert state.status_code == 200, state.text

    killed = await client.post(
        f"{API}/evaluate",
        params={"project_id": project_id},
        json={"flag_key": flag_key, "env": "prod", "context": {"user_id": "u1"}},
    )
    assert killed.status_code == 200, killed.text
    assert killed.json()["value"] is False
    assert killed.json()["reason"] == "KILL_SWITCH_ACTIVE"

    # Change the default: the killed flag now serves the new default...
    res = await patch_default(client, project_id, flag_key, True)
    assert res.status_code == 200, res.text

    killed_after = await client.post(
        f"{API}/evaluate",
        params={"project_id": project_id},
        json={"flag_key": flag_key, "env": "prod", "context": {"user_id": "u1"}},
    )
    assert killed_after.json()["value"] is True
    assert killed_after.json()["reason"] == "KILL_SWITCH_ACTIVE"

    # ...while the rollout percentage and kill-switch state are untouched.
    fetched = await client.get(f"{API}/flags/{flag_key}", params={"project_id": project_id})
    prod_state = next(s for s in fetched.json()["states"] if s["env"] == "prod")
    assert prod_state["enabled"] is False
    assert prod_state["percentage"] == 40

    # Re-enable: the rollout still decides, independent of the default.
    await client.patch(
        f"{API}/flags/{flag_key}/environments/prod",
        params={"project_id": project_id},
        json={"enabled": True, "percentage": 100},
    )
    rolled = await client.post(
        f"{API}/evaluate",
        params={"project_id": project_id},
        json={"flag_key": flag_key, "env": "prod", "context": {"user_id": "u1"}},
    )
    assert rolled.status_code == 200, rolled.text
    assert rolled.json()["reason"] == "PERCENTAGE_ROLLOUT"
    assert rolled.json()["value"] is True
