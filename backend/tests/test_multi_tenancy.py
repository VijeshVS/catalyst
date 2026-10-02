"""
Phase 1 tests: multi-tenant hierarchy (organizations, projects, environments),
strict project scoping of flags/evaluation/bootstrap/audit, and
environment version (ETag) invalidation.
"""
import pytest

API = "/api/v1"


async def create_organization(client, name: str) -> dict:
    res = await client.post(f"{API}/organizations", json={"name": name})
    assert res.status_code == 201, res.text
    return res.json()


async def create_project(client, org_id: str, name: str) -> dict:
    res = await client.post(f"{API}/organizations/{org_id}/projects", json={"name": name})
    assert res.status_code == 201, res.text
    return res.json()


async def env_names(client, project_id: str) -> list:
    res = await client.get(f"{API}/projects/{project_id}/environments")
    assert res.status_code == 200, res.text
    return [e["name"] for e in res.json()]


# ---------------------------------------------------------------------------
# Organization management
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_organization_crud(client):
    res = await client.get(f"{API}/organizations")
    assert res.status_code == 200
    assert res.json() == []

    org = await create_organization(client, "Acme Inc")
    assert org["name"] == "Acme Inc"
    assert org["projects"] == []

    # Duplicate names are rejected
    res = await client.post(f"{API}/organizations", json={"name": "Acme Inc"})
    assert res.status_code == 409

    # Blank names are rejected
    res = await client.post(f"{API}/organizations", json={"name": "   "})
    assert res.status_code == 422

    res = await client.get(f"{API}/organizations")
    assert res.status_code == 200
    assert [o["id"] for o in res.json()] == [org["id"]]

    res = await client.get(f"{API}/organizations/{org['id']}")
    assert res.status_code == 200
    assert res.json()["name"] == "Acme Inc"
    assert res.json()["projects"] == []

    res = await client.get(f"{API}/organizations/00000000-0000-0000-0000-000000000000")
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# Projects & environments
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_project_creation_provisions_standard_environments(client):
    org = await create_organization(client, "Acme Inc")
    project = await create_project(client, org["id"], "Web App")

    assert project["org_id"] == org["id"]
    assert project["name"] == "Web App"
    assert [e["name"] for e in project["environments"]] == ["dev", "staging", "prod"]
    assert all(e["version"] == 1 for e in project["environments"])

    # The environments list endpoint returns the standard set in order
    assert await env_names(client, project["id"]) == ["dev", "staging", "prod"]

    # Nested under organization details as well
    res = await client.get(f"{API}/organizations/{org['id']}")
    assert res.status_code == 200
    assert [p["id"] for p in res.json()["projects"]] == [project["id"]]

    # Duplicate project name within the same organization is rejected
    res = await client.post(
        f"{API}/organizations/{org['id']}/projects", json={"name": "Web App"}
    )
    assert res.status_code == 409

    # The same project name may exist in a different organization
    other_org = await create_organization(client, "Globex")
    other_project = await create_project(client, other_org["id"], "Web App")
    assert other_project["id"] != project["id"]

    # Unknown organization
    res = await client.post(
        f"{API}/organizations/00000000-0000-0000-0000-000000000000/projects",
        json={"name": "Nope"},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_custom_environment_management(client):
    org = await create_organization(client, "Acme Inc")
    project = await create_project(client, org["id"], "Web App")

    res = await client.post(
        f"{API}/projects/{project['id']}/environments", json={"name": "qa"}
    )
    assert res.status_code == 201, res.text
    assert res.json()["name"] == "qa"
    assert res.json()["version"] == 1

    assert await env_names(client, project["id"]) == ["dev", "staging", "prod", "qa"]

    # Duplicates (custom or standard) are rejected
    res = await client.post(
        f"{API}/projects/{project['id']}/environments", json={"name": "qa"}
    )
    assert res.status_code == 409
    res = await client.post(
        f"{API}/projects/{project['id']}/environments", json={"name": "dev"}
    )
    assert res.status_code == 409

    # Invalid names are rejected (identifiers must be lowercase)
    res = await client.post(
        f"{API}/projects/{project['id']}/environments", json={"name": "QA!"}
    )
    assert res.status_code == 422

    # Unknown project
    res = await client.get(f"{API}/projects/00000000-0000-0000-0000-000000000000/environments")
    assert res.status_code == 404
    res = await client.post(
        f"{API}/projects/00000000-0000-0000-0000-000000000000/environments",
        json={"name": "qa"},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_endpoints_require_project_scope(client):
    org = await create_organization(client, "Acme Inc")
    project = await create_project(client, org["id"], "Web App")
    unknown = "00000000-0000-0000-0000-000000000000"

    # Missing project_id -> validation error
    res = await client.get(f"{API}/flags")
    assert res.status_code == 422
    res = await client.get(f"{API}/audit")
    assert res.status_code == 422
    res = await client.get(f"{API}/bootstrap")
    assert res.status_code == 422
    res = await client.post(
        f"{API}/evaluate",
        json={"flag_key": "x", "context": {"user_id": "u"}, "env": "dev"},
    )
    assert res.status_code == 422
    res = await client.post(
        f"{API}/batch-evaluate",
        json={"context": {"user_id": "u"}, "env": "dev"},
    )
    assert res.status_code == 422

    # Unknown project -> 404
    res = await client.get(f"{API}/flags", params={"project_id": unknown})
    assert res.status_code == 404
    res = await client.post(
        f"{API}/flags",
        params={"project_id": unknown},
        json={"key": "some-flag", "name": "Some Flag"},
    )
    assert res.status_code == 404
    res = await client.get(f"{API}/audit", params={"project_id": unknown})
    assert res.status_code == 404
    res = await client.get(f"{API}/bootstrap", params={"project_id": unknown})
    assert res.status_code == 404
    res = await client.post(
        f"{API}/evaluate",
        params={"project_id": unknown},
        json={"flag_key": "x", "context": {"user_id": "u"}, "env": "dev"},
    )
    assert res.status_code == 404

    # Unknown environment within a valid project -> 404
    res = await client.get(
        f"{API}/bootstrap", params={"project_id": project["id"], "env": "ghost"}
    )
    assert res.status_code == 404
    res = await client.post(
        f"{API}/evaluate",
        params={"project_id": project["id"]},
        json={"flag_key": "x", "context": {"user_id": "u"}, "env": "ghost"},
    )
    assert res.status_code == 404
    res = await client.patch(
        f"{API}/flags/x/environments/ghost",
        params={"project_id": project["id"]},
        json={"percentage": 10},
    )
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# Project isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_flag_project_isolation(client):
    org = await create_organization(client, "Acme Inc")
    project_a = await create_project(client, org["id"], "Alpha")
    project_b = await create_project(client, org["id"], "Beta")

    # The same flag key can exist independently in two projects
    res = await client.post(
        f"{API}/flags",
        params={"project_id": project_a["id"]},
        json={"key": "shared-key", "name": "Alpha Flag"},
    )
    assert res.status_code == 201, res.text
    flag_a = res.json()
    res = await client.post(
        f"{API}/flags",
        params={"project_id": project_b["id"]},
        json={"key": "shared-key", "name": "Beta Flag"},
    )
    assert res.status_code == 201, res.text
    flag_b = res.json()

    assert flag_a["id"] != flag_b["id"]
    # A new flag gets a state row for every environment of its project
    assert {s["env"] for s in flag_a["states"]} == {"dev", "staging", "prod"}

    # Duplicate key within one project is rejected
    res = await client.post(
        f"{API}/flags",
        params={"project_id": project_a["id"]},
        json={"key": "shared-key", "name": "Duplicate"},
    )
    assert res.status_code == 400

    # Listing is scoped
    res = await client.get(f"{API}/flags", params={"project_id": project_a["id"]})
    assert [f["id"] for f in res.json()] == [flag_a["id"]]
    res = await client.get(f"{API}/flags", params={"project_id": project_b["id"]})
    assert [f["id"] for f in res.json()] == [flag_b["id"]]

    # Detail fetch is scoped: project B sees its own definition, not project A's
    res = await client.get(
        f"{API}/flags/shared-key", params={"project_id": project_b["id"]}
    )
    assert res.json()["id"] == flag_b["id"]
    assert res.json()["name"] == "Beta Flag"

    # Kill switch in project A must not leak into project B
    res = await client.patch(
        f"{API}/flags/shared-key/environments/prod",
        params={"project_id": project_a["id"]},
        json={"enabled": False},
    )
    assert res.status_code == 200

    eval_body = {"flag_key": "shared-key", "context": {"user_id": "u1"}, "env": "prod"}
    res = await client.post(
        f"{API}/evaluate", params={"project_id": project_a["id"]}, json=eval_body
    )
    assert res.json() == {"flag_key": "shared-key", "value": False, "reason": "KILL_SWITCH_ACTIVE", "rule_id": None}

    # Project B's flag was not killed, so it decides on its own percentage.
    # Both answer false, but for different reasons -- which is the isolation.
    res = await client.post(
        f"{API}/evaluate", params={"project_id": project_b["id"]}, json=eval_body
    )
    assert res.json()["value"] is False
    assert res.json()["reason"] == "PERCENTAGE_OUTSIDE_ROLLOUT"

    # Audit log is scoped per project
    res = await client.get(f"{API}/audit", params={"project_id": project_a["id"]})
    actions_a = [e["action"] for e in res.json()]
    res = await client.get(f"{API}/audit", params={"project_id": project_b["id"]})
    actions_b = [e["action"] for e in res.json()]

    assert "flag.created" in actions_a and "kill_switch.activated" in actions_a
    assert "flag.created" in actions_b
    assert "kill_switch.activated" not in actions_b


# ---------------------------------------------------------------------------
# Bootstrap ETag scoping & invalidation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bootstrap_etag_scoping_and_invalidation(client):
    org = await create_organization(client, "Acme Inc")
    project_a = await create_project(client, org["id"], "Alpha")
    project_b = await create_project(client, org["id"], "Beta")

    for project, key in ((project_a, "alpha-feature"), (project_b, "beta-feature")):
        res = await client.post(
            f"{API}/flags",
            params={"project_id": project["id"]},
            json={"key": key, "name": key},
        )
        assert res.status_code == 201, res.text

    res = await client.get(
        f"{API}/bootstrap", params={"project_id": project_a["id"], "env": "prod"}
    )
    assert res.status_code == 200
    snapshot_a = res.json()
    etag_a = res.headers["ETag"]
    assert set(snapshot_a["flags"]) == {"alpha-feature"}
    assert snapshot_a["version"] >= 1

    res = await client.get(
        f"{API}/bootstrap",
        params={"project_id": project_b["id"], "env": "prod"},
    )
    assert res.status_code == 200
    etag_b = res.headers["ETag"]
    assert set(res.json()["flags"]) == {"beta-feature"}
    assert etag_a != etag_b

    # Conditional request -> 304 with the ETag echoed back
    res = await client.get(
        f"{API}/bootstrap",
        params={"project_id": project_a["id"], "env": "prod"},
        headers={"If-None-Match": etag_a},
    )
    assert res.status_code == 304
    assert res.headers["ETag"] == etag_a

    # Cross-project ETag must not validate a different project snapshot
    res = await client.get(
        f"{API}/bootstrap",
        params={"project_id": project_b["id"], "env": "prod"},
        headers={"If-None-Match": etag_a},
    )
    assert res.status_code == 200

    # Mutating project A must invalidate A's ETag...
    res = await client.patch(
        f"{API}/flags/alpha-feature/environments/prod",
        params={"project_id": project_a["id"]},
        json={"percentage": 50},
    )
    assert res.status_code == 200

    res = await client.get(
        f"{API}/bootstrap",
        params={"project_id": project_a["id"], "env": "prod"},
        headers={"If-None-Match": etag_a},
    )
    assert res.status_code == 200
    assert res.headers["ETag"] != etag_a
    assert res.json()["version"] > snapshot_a["version"]
    assert res.json()["flags"]["alpha-feature"]["percentage"] == 50

    # ...but must leave project B's snapshot (and ETag) untouched
    res = await client.get(
        f"{API}/bootstrap",
        params={"project_id": project_b["id"], "env": "prod"},
        headers={"If-None-Match": etag_b},
    )
    assert res.status_code == 304


# ---------------------------------------------------------------------------
# Custom environments end-to-end
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_custom_environment_end_to_end(client):
    org = await create_organization(client, "Acme Inc")
    project = await create_project(client, org["id"], "Web App")

    # Flag created before the custom environment exists
    res = await client.post(
        f"{API}/flags",
        params={"project_id": project["id"]},
        json={"key": "qa-flag", "name": "QA Flag"},
    )
    assert res.status_code == 201, res.text
    flag = res.json()
    assert {s["env"] for s in flag["states"]} == {"dev", "staging", "prod"}

    # Creating the environment seeds state rows for existing flags
    res = await client.post(
        f"{API}/projects/{project['id']}/environments", json={"name": "qa"}
    )
    assert res.status_code == 201, res.text

    res = await client.get(
        f"{API}/flags/qa-flag", params={"project_id": project["id"]}
    )
    assert res.status_code == 200
    assert {s["env"] for s in res.json()["states"]} == {"dev", "staging", "prod", "qa"}

    # The custom environment is fully usable
    res = await client.patch(
        f"{API}/flags/qa-flag/environments/qa",
        params={"project_id": project["id"]},
        json={"percentage": 100},
    )
    assert res.status_code == 200

    res = await client.get(
        f"{API}/bootstrap",
        params={"project_id": project["id"], "env": "qa"},
    )
    assert res.status_code == 200
    assert res.json()["flags"]["qa-flag"]["percentage"] == 100

    res = await client.post(
        f"{API}/evaluate",
        params={"project_id": project["id"]},
        json={"flag_key": "qa-flag", "context": {"user_id": "u1"}, "env": "qa"},
    )
    assert res.status_code == 200
    assert res.json()["value"] is True
    assert res.json()["reason"] == "PERCENTAGE_ROLLOUT"
