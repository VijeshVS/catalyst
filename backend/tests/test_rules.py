"""
Phase 3 tests: rule-based targeting CRUD, priority ordering, environment
version invalidation, audit attribution, and rule-driven evaluation.
"""
import pytest

from app.services.evaluator import match_condition, normalize_operator

API = "/api/v1"


async def create_organization(client, name: str) -> dict:
    res = await client.post(f"{API}/organizations", json={"name": name})
    assert res.status_code == 201, res.text
    return res.json()


async def create_project(client, org_id: str, name: str) -> dict:
    res = await client.post(f"{API}/organizations/{org_id}/projects", json={"name": name})
    assert res.status_code == 201, res.text
    return res.json()


async def create_flag(client, project_id: str, key: str = "ai-assistant") -> dict:
    res = await client.post(
        f"{API}/flags?project_id={project_id}",
        json={"key": key, "name": "AI Assistant", "default_value": False},
    )
    assert res.status_code == 201, res.text
    return res.json()


def rules_base(key: str, env: str) -> str:
    return f"{API}/flags/{key}/environments/{env}/rules"


def rules_path(project_id: str, key: str, env: str) -> str:
    return f"{rules_base(key, env)}?project_id={project_id}"


def rule_path(project_id: str, key: str, env: str, rule_id: str) -> str:
    return f"{rules_base(key, env)}/{rule_id}?project_id={project_id}"


async def bootstrap_version(client, project_id: str, env: str):
    res = await client.get(f"{API}/bootstrap?project_id={project_id}&env={env}")
    assert res.status_code == 200, res.text
    return res.json()["version"], res.json(), res.headers.get("ETag")


# ---------------------------------------------------------------------------
# Condition schema validation
# ---------------------------------------------------------------------------

def test_operator_aliases_normalize_to_canonical_names():
    assert normalize_operator("EQ") == "equals"
    assert normalize_operator("gte") == "greater_than_or_equal"
    assert normalize_operator(None) == "equals"
    assert normalize_operator("notExists") == "not_exists"


def test_presence_operators_only_look_at_attribute_presence():
    assert match_condition({"attr": "beta", "op": "exists"}, {"beta": False}) is True
    assert match_condition({"attr": "beta", "op": "exists"}, {}) is False
    assert match_condition({"attr": "beta", "op": "not_exists"}, {}) is True
    assert match_condition({"attr": "beta", "op": "not_exists"}, {"beta": 1}) is False


@pytest.mark.asyncio
async def test_rule_creation_validates_conditions(client):
    org = await create_organization(client, "Rule Validation")
    project = await create_project(client, org["id"], "Validation")
    flag = await create_flag(client, project["id"])
    path = rules_path(project["id"], flag["key"], "dev")

    empty = await client.post(path, json={"conditions": []})
    assert empty.status_code == 422

    bad_operator = await client.post(
        path, json={"conditions": [{"attr": "email", "op": "regex", "value": ".*"}]}
    )
    assert bad_operator.status_code == 422

    bad_attr = await client.post(
        path, json={"conditions": [{"attr": "email address", "op": "equals", "value": "a"}]}
    )
    assert bad_attr.status_code == 422

    missing_attr = await client.post(path, json={"conditions": [{"op": "equals", "value": "a"}]})
    assert missing_attr.status_code == 422


# ---------------------------------------------------------------------------
# Rule CRUD
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rule_crud_lifecycle(client):
    org = await create_organization(client, "Rule CRUD")
    project = await create_project(client, org["id"], "Lifecycle")
    flag = await create_flag(client, project["id"])
    path = rules_path(project["id"], flag["key"], "dev")

    created = await client.post(
        path,
        json={
            "conditions": [
                {"attr": "email", "op": "ends_with", "value": "@acme.com"},
                {"attr": "plan", "op": "in", "value": ["pro", "enterprise"]},
            ],
            "serve": True,
        },
    )
    assert created.status_code == 201, created.text
    rule = created.json()
    assert rule["env"] == "dev"
    assert rule["priority"] == 0
    assert rule["serve"] is True
    # Operator aliases are normalized on the way in.
    assert rule["conditions"][0]["op"] == "ends_with"

    single = rule_path(project["id"], flag["key"], "dev", rule["id"])

    listed = await client.get(path)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [rule["id"]]

    # The flag list embeds the same `conditions` shape as the rule endpoints.
    flag_list = await client.get(f"{API}/flags?project_id={project['id']}")
    embedded = next(item for item in flag_list.json() if item["key"] == flag["key"])
    assert embedded["rules"][0]["conditions"] == [
        {"attr": "email", "op": "ends_with", "value": "@acme.com"},
        {"attr": "plan", "op": "in", "value": ["pro", "enterprise"]},
    ]

    updated = await client.put(
        single,
        json={"conditions": [{"attr": "role", "op": "equals", "value": "admin"}], "serve": False},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["serve"] is False
    assert updated.json()["conditions"] == [
        {"attr": "role", "op": "equals", "value": "admin"}
    ]

    deleted = await client.delete(single)
    assert deleted.status_code == 204
    assert (await client.get(path)).json() == []


@pytest.mark.asyncio
async def test_rules_are_scoped_to_flag_and_environment(client):
    org = await create_organization(client, "Rule Scoping")
    project = await create_project(client, org["id"], "Scoping")
    await create_flag(client, project["id"], "dev-only")
    await create_flag(client, project["id"], "prod-only")

    dev_rule = await client.post(
        rules_path(project["id"], "dev-only", "dev"),
        json={"conditions": [{"attr": "country", "op": "equals", "value": "IN"}]},
    )
    assert dev_rule.status_code == 201, dev_rule.text

    # The rule is invisible from another environment of the same flag.
    assert (await client.get(rules_path(project["id"], "dev-only", "prod"))).json() == []
    # ... and from the same environment of a different flag.
    assert (await client.get(rules_path(project["id"], "prod-only", "dev"))).json() == []
    # ... and from a different project entirely, where the flag does not exist.
    other_org = await create_organization(client, "Other Org")
    other_project = await create_project(client, other_org["id"], "Other")
    await create_flag(client, other_project["id"], "dev-only")
    assert (await client.get(rules_path(other_project["id"], "dev-only", "dev"))).json() == []


@pytest.mark.asyncio
async def test_rule_endpoints_reject_unknown_project_flag_env_and_rule(client):
    org = await create_organization(client, "Rule Guards")
    project = await create_project(client, org["id"], "Guards")
    flag = await create_flag(client, project["id"])
    rule = (
        await client.post(
            rules_path(project["id"], flag["key"], "dev"),
            json={"conditions": [{"attr": "country", "op": "equals", "value": "IN"}]},
        )
    ).json()

    assert (await client.get(f"{API}/flags/{flag['key']}/environments/dev/rules")).status_code == 422
    assert (await client.get(rules_path("does-not-exist", flag["key"], "dev"))).status_code == 404
    assert (await client.get(rules_path(project["id"], "nope", "dev"))).status_code == 404
    assert (await client.get(rules_path(project["id"], flag["key"], "nope"))).status_code == 404
    assert (
        await client.delete(rule_path(project["id"], flag["key"], "dev", "does-not-exist"))
    ).status_code == 404
    assert (
        await client.put(
            rule_path(project["id"], flag["key"], "prod", rule["id"]),
            json={"serve": False},
        )
    ).status_code == 404


@pytest.mark.asyncio
async def test_rule_endpoints_require_authentication(anon_client):
    assert (await anon_client.get(f"{API}/flags/ai/environments/dev/rules?project_id=x")).status_code == 401


@pytest.mark.asyncio
async def test_other_user_cannot_touch_rules(anon_client):
    owner = await anon_client.post(
        "/api/v1/auth/register",
        json={"email": "owner@example.com", "password": "owner-password", "full_name": "Owner"},
    )
    assert owner.status_code == 201, owner.text
    anon_client.headers["Authorization"] = f"Bearer {owner.json()['access_token']}"

    org = await create_organization(anon_client, "Owner Org")
    project = await create_project(anon_client, org["id"], "Private")
    flag = await create_flag(anon_client, project["id"])
    rule = (
        await anon_client.post(
            rules_path(project["id"], flag["key"], "dev"),
            json={"conditions": [{"attr": "country", "op": "equals", "value": "IN"}]},
        )
    ).json()

    await anon_client.post(
        "/api/v1/auth/register",
        json={"email": "intruder@example.com", "password": "intruder-pass", "full_name": "Intruder"},
    )
    login = await anon_client.post(
        "/api/v1/auth/login", json={"email": "intruder@example.com", "password": "intruder-pass"}
    )
    anon_client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"

    path = rules_path(project["id"], flag["key"], "dev")
    single = rule_path(project["id"], flag["key"], "dev", rule["id"])
    assert (await anon_client.get(path)).status_code == 404
    assert (
        await anon_client.post(path, json={"conditions": [{"attr": "a", "op": "exists"}]})
    ).status_code == 404
    assert (await anon_client.put(single, json={"serve": False})).status_code == 404
    assert (await anon_client.delete(single)).status_code == 404


# ---------------------------------------------------------------------------
# Priority ordering
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rule_priorities_are_dense_and_reorderable(client):
    org = await create_organization(client, "Reorder Org")
    project = await create_project(client, org["id"], "Reorder")
    flag = await create_flag(client, project["id"])
    path = rules_path(project["id"], flag["key"], "dev")

    created = []
    for index, country in enumerate(["IN", "US", "DE"]):
        res = await client.post(
            path,
            json={"conditions": [{"attr": "country", "op": "equals", "value": country}]},
        )
        assert res.status_code == 201, res.text
        created.append(res.json())

    assert [rule["priority"] for rule in created] == [0, 1, 2]

    reordered = await client.put(
        f"{rules_base(flag['key'], 'dev')}/reorder?project_id={project['id']}",
        json={"rule_ids": [created[2]["id"], created[0]["id"], created[1]["id"]]},
    )
    assert reordered.status_code == 200, reordered.text
    assert [rule["id"] for rule in reordered.json()] == [created[2]["id"], created[0]["id"], created[1]["id"]]
    assert [rule["priority"] for rule in reordered.json()] == [0, 1, 2]

    # Deleting the highest priority rule closes the gap it leaves behind.
    assert (
        await client.delete(rule_path(project["id"], flag["key"], "dev", created[2]["id"]))
    ).status_code == 204
    remaining = (await client.get(path)).json()
    assert [rule["id"] for rule in remaining] == [created[0]["id"], created[1]["id"]]
    assert [rule["priority"] for rule in remaining] == [0, 1]


@pytest.mark.asyncio
async def test_reorder_requires_the_complete_rule_set(client):
    org = await create_organization(client, "Reorder Guard Org")
    project = await create_project(client, org["id"], "Reorder Guards")
    flag = await create_flag(client, project["id"])
    path = rules_path(project["id"], flag["key"], "dev")

    first = (
        await client.post(
            path, json={"conditions": [{"attr": "country", "op": "equals", "value": "IN"}]}
        )
    ).json()
    second = (
        await client.post(
            path, json={"conditions": [{"attr": "country", "op": "equals", "value": "US"}]}
        )
    ).json()

    # Partial ordering is rejected so a rule can never be dropped by accident.
    reorder = f"{rules_base(flag['key'], 'dev')}/reorder?project_id={project['id']}"
    assert (await client.put(reorder, json={"rule_ids": [first["id"]]})).status_code == 400
    assert (await client.put(reorder, json={"rule_ids": [first["id"], first["id"]]})).status_code == 400
    assert (await client.put(reorder, json={"rule_ids": [first["id"], "ghost-id"]})).status_code == 400
    assert (await client.put(reorder, json={"rule_ids": [second["id"], first["id"]]})).status_code == 200


# ---------------------------------------------------------------------------
# Cache invalidation + audit
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rule_mutations_invalidate_only_the_targeted_environment(client):
    org = await create_organization(client, "Cache Org")
    project = await create_project(client, org["id"], "Cache")
    flag = await create_flag(client, project["id"])

    dev_version, _, _ = await bootstrap_version(client, project["id"], "dev")
    prod_version, _, _ = await bootstrap_version(client, project["id"], "prod")

    created = await client.post(
        rules_path(project["id"], flag["key"], "dev"),
        json={"conditions": [{"attr": "email", "op": "ends_with", "value": "@acme.com"}]},
    )
    assert created.status_code == 201

    new_dev_version, dev_snapshot, _ = await bootstrap_version(client, project["id"], "dev")
    assert new_dev_version == dev_version + 1
    assert dev_snapshot["flags"]["ai-assistant"]["rules"][0]["conditions"] == [
        {"attr": "email", "op": "ends_with", "value": "@acme.com"}
    ]

    # A dev-scoped rule change must not invalidate the prod ETag.
    still_prod_version, _, _ = await bootstrap_version(client, project["id"], "prod")
    assert still_prod_version == prod_version

    single = rule_path(project["id"], flag["key"], "dev", created.json()["id"])
    await client.put(single, json={"serve": False})
    assert (await bootstrap_version(client, project["id"], "dev"))[0] == new_dev_version + 1
    await client.delete(single)
    assert (await bootstrap_version(client, project["id"], "dev"))[0] == new_dev_version + 2
    assert (await bootstrap_version(client, project["id"], "prod"))[0] == prod_version


@pytest.mark.asyncio
async def test_rule_mutations_are_audited_with_user_attribution(client):
    org = await create_organization(client, "Audit Org")
    project = await create_project(client, org["id"], "Audit")
    flag = await create_flag(client, project["id"])
    path = rules_path(project["id"], flag["key"], "dev")

    rule = (
        await client.post(
            path,
            json={
                "conditions": [{"attr": "email", "op": "ends_with", "value": "@acme.com"}],
                "serve": True,
            },
        )
    ).json()
    single = rule_path(project["id"], flag["key"], "dev", rule["id"])
    reorder = f"{rules_base(flag['key'], 'dev')}/reorder?project_id={project['id']}"
    await client.put(single, json={"serve": False})
    await client.put(reorder, json={"rule_ids": [rule["id"]]})
    await client.delete(single)

    logs = await client.get(f"{API}/audit?project_id={project['id']}")
    assert logs.status_code == 200
    actions = [entry["action"] for entry in logs.json()]
    assert actions[:4] == ["rule.deleted", "rule.reordered", "rule.updated", "rule.created"]

    created_entry = next(e for e in logs.json() if e["action"] == "rule.created")
    assert created_entry["user_email"] == "phase1@example.com"
    assert created_entry["user_id"] is not None
    assert created_entry["env"] == "dev"
    assert created_entry["flag_id"] == flag["id"]
    assert created_entry["after"]["conditions"][0]["attr"] == "email"

    updated_entry = next(e for e in logs.json() if e["action"] == "rule.updated")
    assert updated_entry["before"]["serve"] is True
    assert updated_entry["after"]["serve"] is False


# ---------------------------------------------------------------------------
# Rule driven evaluation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rules_drive_evaluation_by_priority(client):
    org = await create_organization(client, "Eval Org")
    project = await create_project(client, org["id"], "Eval")
    flag = await create_flag(client, project["id"])
    path = rules_path(project["id"], flag["key"], "dev")

    # Highest priority: internal employees get the feature.
    await client.post(
        path,
        json={
            "conditions": [{"attr": "email", "op": "ends_with", "value": "@acme.com"}],
            "serve": True,
        },
    )
    # Lower priority: everyone else in the beta cohort is opted out.
    await client.post(
        path,
        json={
            "conditions": [{"attr": "beta_cohort", "op": "equals", "value": True}],
            "serve": False,
        },
    )

    async def evaluate(attributes: dict) -> dict:
        res = await client.post(
            f"{API}/evaluate?project_id={project['id']}",
            json={
                "flag_key": flag["key"],
                "env": "dev",
                "context": {"user_id": "user_1", "attributes": attributes},
            },
        )
        assert res.status_code == 200, res.text
        return res.json()

    internal = await evaluate({"email": "dev@acme.com", "beta_cohort": True})
    assert internal["value"] is True
    assert internal["reason"] == "RULE_MATCH"

    beta_opted_out = await evaluate({"email": "dev@other.com", "beta_cohort": True})
    assert beta_opted_out["value"] is False
    assert beta_opted_out["reason"] == "RULE_MATCH"

    unsegmented = await evaluate({"email": "dev@other.com"})
    assert unsegmented["value"] is False
    assert unsegmented["reason"] == "DEFAULT_VALUE"

    # The rules are evaluated before the percentage rollout.
    rollout = await client.patch(
        f"{API}/flags/{flag['key']}/environments/dev?project_id={project['id']}",
        json={"percentage": 100},
    )
    assert rollout.status_code == 200
    assert (await evaluate({"email": "dev@other.com"}))["reason"] == "PERCENTAGE_ROLLOUT"

    # ... but the kill switch still wins over every rule.
    await client.patch(
        f"{API}/flags/{flag['key']}/environments/dev?project_id={project['id']}",
        json={"enabled": False, "percentage": 0},
    )
    killed = await evaluate({"email": "dev@acme.com"})
    assert killed["value"] is False
    assert killed["reason"] == "KILL_SWITCH_ACTIVE"


@pytest.mark.asyncio
async def test_matched_rule_id_is_reported(client):
    org = await create_organization(client, "Rule Id Org")
    project = await create_project(client, org["id"], "Rule Id")
    flag = await create_flag(client, project["id"])
    rule = (
        await client.post(
            rules_path(project["id"], flag["key"], "dev"),
            json={"conditions": [{"attr": "trial", "op": "exists"}], "serve": True},
        )
    ).json()

    res = await client.post(
        f"{API}/evaluate?project_id={project['id']}",
        json={
            "flag_key": flag["key"],
            "env": "dev",
            "context": {"user_id": "user_1", "attributes": {"trial": True}},
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["rule_id"] == rule["id"]
