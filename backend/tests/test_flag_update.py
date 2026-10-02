"""
Tests for updating an existing flag's definition via
``PATCH /api/v1/flags/{key}``.

Covers both editable fields, strict project scoping, unknown-flag handling,
environment version (ETag) invalidation, and the guarantee that rollout and
kill-switch behaviour are untouched by a name or description change.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core import cache as cache_module
from app.services.snapshots import SOURCE_POSTGRES
from test_snapshot_cache import fake_redis  # noqa: F401  (shared fixture)

API = "/api/v1"


async def create_flag(client: AsyncClient, name: str) -> tuple[str, str, str]:
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
    return org.json()["id"], project.json()["id"], flag.json()["key"]


async def patch(client: AsyncClient, project_id: str, flag_key: str, **fields):
    return await client.patch(
        f"{API}/flags/{flag_key}",
        params={"project_id": project_id},
        json=fields,
    )


# ---------------------------------------------------------------------------
# Definition updates
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_name_can_be_changed(client):
    _org_id, project_id, flag_key = await create_flag(client, "Rename")

    res = await patch(client, project_id, flag_key, name="Renamed Assistant")
    assert res.status_code == 200, res.text
    assert res.json()["name"] == "Renamed Assistant"

    fetched = await client.get(f"{API}/flags/{flag_key}", params={"project_id": project_id})
    assert fetched.json()["name"] == "Renamed Assistant"


@pytest.mark.asyncio
async def test_description_can_be_changed(client):
    _org_id, project_id, flag_key = await create_flag(client, "Describe")

    res = await patch(client, project_id, flag_key, description="Controls the widget")
    assert res.status_code == 200, res.text
    assert res.json()["description"] == "Controls the widget"


@pytest.mark.asyncio
async def test_flag_has_no_default_value_field(client):
    """2-C removed it: a vestigial third source of truth is how the confusion started."""
    _org_id, project_id, flag_key = await create_flag(client, "No Default")

    fetched = await client.get(f"{API}/flags/{flag_key}", params={"project_id": project_id})
    assert "default_value" not in fetched.json()


@pytest.mark.asyncio
async def test_a_flag_starts_off_and_inactive(client):
    """A new flag serves nobody until someone turns it on."""
    _org_id, project_id, flag_key = await create_flag(client, "Fresh Off")

    res = await client.post(
        f"{API}/evaluate",
        params={"project_id": project_id},
        json={"flag_key": flag_key, "env": "dev", "context": {"user_id": "u1"}},
    )
    assert res.status_code == 200, res.text
    assert res.json()["value"] is False
    assert res.json()["reason"] == "PERCENTAGE_OUTSIDE_ROLLOUT"

    fetched = await client.get(f"{API}/flags/{flag_key}", params={"project_id": project_id})
    dev_state = next(s for s in fetched.json()["states"] if s["env"] == "dev")
    assert dev_state["percentage"] == 0
    assert dev_state["enable_all"] is False


@pytest.mark.asyncio
async def test_definition_update_is_scoped_to_the_project(client):
    org_a = await client.post(f"{API}/organizations", json={"name": "Scope A"})
    project_a = await client.post(
        f"{API}/organizations/{org_a.json()['id']}/projects", json={"name": "Project A"}
    )
    org_b = await client.post(f"{API}/organizations", json={"name": "Scope B"})
    project_b = await client.post(
        f"{API}/organizations/{org_b.json()['id']}/projects", json={"name": "Project B"}
    )
    for project in (project_a, project_b):
        assert (
            await client.post(
                f"{API}/flags?project_id={project.json()['id']}",
                json={"key": "ai-assistant", "name": "AI Assistant"},
            )
        ).status_code == 201

    # The same key exists in both projects.
    res = await patch(client, project_b.json()["id"], "ai-assistant", name="Only B")
    assert res.status_code == 200, res.text

    fetched_a = await client.get(
        f"{API}/flags/ai-assistant", params={"project_id": project_a.json()["id"]}
    )
    assert fetched_a.json()["name"] == "AI Assistant", "project A's flag was modified through B"

    # A flag that does not exist in the caller's project is a 404, not a leak.
    assert (await patch(client, project_a.json()["id"], "ghost-flag", name="x")).status_code == 404


@pytest.mark.asyncio
async def test_definition_update_rejects_unknown_project(client):
    res = await patch(client, "nonexistent-project", "ai-assistant", name="x")
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# Cache invalidation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_definition_change_invalidates_environment_snapshots(client, fake_redis):
    _org_id, project_id, flag_key = await create_flag(client, "Definition Invalidate")

    first = await client.get(f"{API}/bootstrap?project_id={project_id}&env=prod")
    assert first.status_code == 200, first.text
    assert first.headers["X-Catalyst-Cache"] == SOURCE_POSTGRES
    etag_before = first.headers["ETag"]
    assert cache_module.snapshot_key(project_id, "prod") in fake_redis.store

    res = await patch(client, project_id, flag_key, name="Renamed")
    assert res.status_code == 200, res.text

    assert cache_module.snapshot_key(project_id, "prod") not in fake_redis.store

    second = await client.get(f"{API}/bootstrap?project_id={project_id}&env=prod")
    assert second.status_code == 200, second.text
    assert second.headers["ETag"] != etag_before
    assert "defaultValue" not in second.json()["flags"][flag_key]
    assert second.json()["flags"][flag_key]["enableAll"] is False


@pytest.mark.asyncio
async def test_definition_change_does_not_disturb_rollout_or_kill_switch(client):
    _org_id, project_id, flag_key = await create_flag(client, "Definition No Disturb")

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

    res = await patch(client, project_id, flag_key, name="Renamed")
    assert res.status_code == 200, res.text

    # The kill switch now means false, full stop: there is no default to fall
    # back to any more.
    killed_after = await client.post(
        f"{API}/evaluate",
        params={"project_id": project_id},
        json={"flag_key": flag_key, "env": "prod", "context": {"user_id": "u1"}},
    )
    assert killed_after.json()["value"] is False
    assert killed_after.json()["reason"] == "KILL_SWITCH_ACTIVE"

    # The rollout percentage and kill-switch state are untouched.
    fetched = await client.get(f"{API}/flags/{flag_key}", params={"project_id": project_id})
    prod_state = next(s for s in fetched.json()["states"] if s["env"] == "prod")
    assert prod_state["enabled"] is False
    assert prod_state["percentage"] == 40

    # Re-enable: the rollout still decides.
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
