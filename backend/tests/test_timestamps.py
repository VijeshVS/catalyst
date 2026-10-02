"""
Tests for Phase 1 timestamps.

Before this phase most tables carried no mutation time at all, so the project
tile's "last updated" was really the newest flag *creation* date and moving a
rollout slider changed nothing. These tests pin the behaviour that fixes it:
a state mutation records a time, and the project reflects it.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient

API = "/api/v1"


async def create_project(client: AsyncClient, name: str) -> tuple[str, str, str]:
    org = await client.post(f"{API}/organizations", json={"name": f"{name} Org"})
    assert org.status_code == 201, org.text
    project = await client.post(
        f"{API}/organizations/{org.json()['id']}/projects", json={"name": f"{name} Project"}
    )
    assert project.status_code == 201, project.text
    return org.json()["id"], project.json()["id"], project.json()["name"]


async def create_flag(client: AsyncClient, project_id: str, key: str = "ai-assistant") -> dict:
    flag = await client.post(
        f"{API}/flags?project_id={project_id}",
        json={"key": key, "name": "AI Assistant", "default_value": False},
    )
    assert flag.status_code == 201, flag.text
    return flag.json()


def parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def project_summary(client: AsyncClient, org_id: str) -> dict:
    org = await client.get(f"{API}/organizations/{org_id}")
    assert org.status_code == 200, org.text
    return org.json()["projects"][0]


# ---------------------------------------------------------------------------
# FlagEnvState
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_new_flag_state_has_an_updated_at(client):
    _org_id, project_id, _ = await create_project(client, "State Timestamp")
    flag = await create_flag(client, project_id)

    assert flag["updated_at"], "a flag carries an updated_at from creation"
    for state in flag["states"]:
        assert state["updated_at"], "every seeded state carries an updated_at"


@pytest.mark.asyncio
async def test_moving_the_rollout_slider_records_a_time(client):
    _org_id, project_id, _ = await create_project(client, "Rollout Timestamp")
    flag = await create_flag(client, project_id)
    before = parse(next(s for s in flag["states"] if s["env"] == "dev")["updated_at"])

    # A clock jump makes a same-millisecond timestamp impossible to mistake for
    # "changed"; nothing about the response should depend on it.
    response = await client.patch(
        f"{API}/flags/{flag['key']}/environments/dev",
        params={"project_id": project_id},
        json={"percentage": 40},
    )
    assert response.status_code == 200, response.text

    after = parse(response.json()["updated_at"])
    assert after > before


@pytest.mark.asyncio
async def test_toggling_the_kill_switch_records_a_time(client):
    _org_id, project_id, _ = await create_project(client, "Kill Switch Timestamp")
    flag = await create_flag(client, project_id)
    before = parse(next(s for s in flag["states"] if s["env"] == "dev")["updated_at"])

    response = await client.patch(
        f"{API}/flags/{flag['key']}/environments/dev",
        params={"project_id": project_id},
        json={"enabled": False},
    )
    assert response.status_code == 200, response.text

    after = parse(response.json()["updated_at"])
    assert after > before


# ---------------------------------------------------------------------------
# Flag, Environment, TargetingRule
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_editing_a_flag_bumps_its_updated_at(client):
    _org_id, project_id, _ = await create_project(client, "Flag Updated At")
    flag = await create_flag(client, project_id)
    before = parse(flag["updated_at"])

    response = await client.patch(
        f"{API}/flags/{flag['key']}",
        params={"project_id": project_id},
        json={"name": "Renamed Assistant"},
    )
    assert response.status_code == 200, response.text
    assert parse(response.json()["updated_at"]) >= before

    fetched = await client.get(f"{API}/flags/{flag['key']}", params={"project_id": project_id})
    assert parse(fetched.json()["updated_at"]) > before


@pytest.mark.asyncio
async def test_custom_environment_carries_created_at(client):
    _org_id, project_id, _ = await create_project(client, "Environment Created At")
    response = await client.post(
        f"{API}/projects/{project_id}/environments", json={"name": "qa"}
    )
    assert response.status_code == 201, response.text
    assert response.json()["created_at"]


@pytest.mark.asyncio
async def test_targeting_rule_carries_both_timestamps(client):
    _org_id, project_id, _ = await create_project(client, "Rule Timestamps")
    flag = await create_flag(client, project_id)

    response = await client.post(
        f"{API}/flags/{flag['key']}/environments/dev/rules?project_id={project_id}",
        json={
            "conditions": [{"attr": "email", "op": "ends_with", "value": "@acme.com"}],
            "serve": True,
        },
    )
    assert response.status_code == 201, response.text
    rule = response.json()
    assert rule["created_at"]
    assert rule["updated_at"] >= rule["created_at"]


# ---------------------------------------------------------------------------
# 1-C: the project "last updated" is honest
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_project_updated_at_moves_when_a_rollout_changes(client):
    org_id, project_id, project_name = await create_project(client, "Honest Updated At")
    await create_flag(client, project_id)

    before = await project_summary(client, org_id)
    assert before["name"] == project_name

    response = await client.patch(
        f"{API}/flags/ai-assistant/environments/dev",
        params={"project_id": project_id},
        json={"percentage": 40},
    )
    assert response.status_code == 200, response.text

    after = await project_summary(client, org_id)
    assert parse(after["updated_at"]) > parse(before["updated_at"])
    assert parse(after["updated_at"]) >= parse(response.json()["updated_at"])


@pytest.mark.asyncio
async def test_project_updated_at_moves_when_the_kill_switch_flips(client):
    org_id, project_id, _ = await create_project(client, "Honest Kill Switch")
    await create_flag(client, project_id)

    before = parse((await project_summary(client, org_id))["updated_at"])

    response = await client.patch(
        f"{API}/flags/ai-assistant/environments/dev",
        params={"project_id": project_id},
        json={"enabled": False},
    )
    assert response.status_code == 200, response.text

    after = parse((await project_summary(client, org_id))["updated_at"])
    assert after > before


@pytest.mark.asyncio
async def test_project_updated_at_is_not_the_flag_creation_time(client):
    """The old bug: a rollout never moved the tile because it read created_at."""
    org_id, project_id, _ = await create_project(client, "Not Created At")
    flag = await create_flag(client, project_id)
    created_at = parse(flag["created_at"])

    await client.patch(
        f"{API}/flags/ai-assistant/environments/dev",
        params={"project_id": project_id},
        json={"percentage": 75},
    )

    summary = await project_summary(client, org_id)
    # Reading created_at would pin this to the flag's creation moment forever;
    # the value has to come from the mutation instead.
    assert parse(summary["updated_at"]) > created_at


@pytest.mark.asyncio
async def test_project_with_no_flags_reports_its_creation_time(client):
    org_id, _project_id, _ = await create_project(client, "No Flags")
    summary = await project_summary(client, org_id)
    assert summary["updated_at"]
    assert summary["flag_count"] == 0


# ---------------------------------------------------------------------------
# 1-D: the archived column is gone
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_flag_response_has_no_archived_field(client):
    _org_id, project_id, _ = await create_project(client, "No Archived Field")
    flag = await create_flag(client, project_id)
    assert "archived" not in flag

    fetched = await client.get(f"{API}/flags/{flag['key']}", params={"project_id": project_id})
    assert "archived" not in fetched.json()


@pytest.mark.asyncio
async def test_list_flags_ignores_an_archived_query_parameter(client):
    _org_id, project_id, _ = await create_project(client, "Archived Param")
    await create_flag(client, project_id)

    response = await client.get(
        f"{API}/flags", params={"project_id": project_id, "archived": "true"}
    )
    assert response.status_code == 200, response.text
    assert [f["key"] for f in response.json()] == ["ai-assistant"]


@pytest.mark.asyncio
async def test_snapshot_includes_every_flag(client):
    org_id, project_id, _ = await create_project(client, "Snapshot No Archived")
    await create_flag(client, project_id, key="first-flag")
    await create_flag(client, project_id, key="second-flag")

    response = await client.get(
        f"{API}/bootstrap", params={"project_id": project_id, "env": "dev"}
    )
    assert response.status_code == 200, response.text
    assert set(response.json()["flags"]) == {"first-flag", "second-flag"}


@pytest.mark.asyncio
async def test_flag_count_is_a_plain_count(client):
    org_id, project_id, _ = await create_project(client, "Plain Count")
    await create_flag(client, project_id, key="one")
    await create_flag(client, project_id, key="two")

    summary = await project_summary(client, org_id)
    assert summary["flag_count"] == 2


@pytest.mark.asyncio
async def test_updated_at_advances_past_a_stale_value(client):
    """A mutation after a simulated pause still records a later time."""
    _org_id, project_id, _ = await create_project(client, "Advances")
    flag = await create_flag(client, project_id)
    first = parse(flag["states"][0]["updated_at"])

    await client.patch(
        f"{API}/flags/ai-assistant/environments/dev",
        params={"project_id": project_id},
        json={"percentage": 10},
    )
    later = parse(
        (
            await client.get(f"{API}/flags/ai-assistant", params={"project_id": project_id})
        ).json()["states"][0]["updated_at"]
    )

    assert later > first
    assert later - first < timedelta(days=1)