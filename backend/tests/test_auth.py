"""Authentication, authorization, and audit-attribution tests."""

import pytest
from sqlalchemy import select

from app.core.db import async_session_maker
from app.core.security import verify_password
from app.models.models import User


API = "/api/v1"


async def register(client, email="owner@example.com", password="correct-horse", full_name="Owner"):
    response = await client.post(
        f"{API}/auth/register",
        json={"email": email, "password": password, "full_name": full_name},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def login(client, email="owner@example.com", password="correct-horse"):
    response = await client.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_register_login_me_and_refresh(anon_client):
    registered = await register(anon_client, "Owner@Example.com")
    assert registered["user"]["email"] == "owner@example.com"
    assert registered["user"]["full_name"] == "Owner"
    assert registered["token_type"] == "bearer"
    assert registered["access_token"] and registered["refresh_token"]
    assert "hashed_password" not in registered["user"]
    assert "password_hash" not in registered["user"]

    duplicate = await anon_client.post(
        f"{API}/auth/register",
        json={"email": "OWNER@example.com", "password": "another-password", "full_name": "Other"},
    )
    assert duplicate.status_code == 409

    logged_in = await login(anon_client)
    anon_client.headers["Authorization"] = f"Bearer {logged_in['access_token']}"
    me = await anon_client.get(f"{API}/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "owner@example.com"

    # A refresh token is not an access token.
    anon_client.headers["Authorization"] = f"Bearer {logged_in['refresh_token']}"
    assert (await anon_client.get(f"{API}/auth/me")).status_code == 401

    refreshed = await anon_client.post(
        f"{API}/auth/refresh", json={"refresh_token": logged_in["refresh_token"]}
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"]
    assert refreshed.json()["user"]["id"] == registered["user"]["id"]

    anon_client.headers["Authorization"] = f"Bearer {refreshed.json()['access_token']}"
    assert (await anon_client.get(f"{API}/auth/me")).status_code == 200


@pytest.mark.asyncio
async def test_registration_validation_and_password_is_hashed(anon_client):
    weak = await anon_client.post(
        f"{API}/auth/register",
        json={"email": "weak@example.com", "password": "short", "full_name": "Weak"},
    )
    assert weak.status_code == 422

    malformed = await anon_client.post(
        f"{API}/auth/register",
        json={"email": "not-an-email", "password": "long-enough", "full_name": "Bad Email"},
    )
    assert malformed.status_code == 422

    await register(anon_client, "hashed@example.com", "a-secure-password", "Hashed User")
    async with async_session_maker() as session:
        user = (await session.execute(select(User).where(User.email == "hashed@example.com"))).scalar_one()
        assert user.hashed_password != "a-secure-password"
        assert verify_password("a-secure-password", user.hashed_password)


@pytest.mark.asyncio
async def test_protected_routes_require_bearer_token(anon_client):
    requests = [
        ("get", f"{API}/organizations", None),
        ("get", f"{API}/flags?project_id=some-project", None),
        ("get", f"{API}/projects/some-project/environments", None),
        ("get", f"{API}/audit?project_id=some-project", None),
        ("get", f"{API}/bootstrap?project_id=some-project&env=prod", None),
        (
            "post",
            f"{API}/evaluate?project_id=some-project",
            {"flag_key": "x", "context": {"user_id": "u"}, "env": "prod"},
        ),
        (
            "post",
            f"{API}/batch-evaluate?project_id=some-project",
            {"context": {"user_id": "u"}, "env": "prod"},
        ),
    ]
    for method, path, body in requests:
        response = await getattr(anon_client, method)(path, json=body) if body else await getattr(anon_client, method)(path)
        assert response.status_code == 401, (method, path, response.text)

    me = await anon_client.get(f"{API}/auth/me")
    assert me.status_code == 401


@pytest.mark.asyncio
async def test_user_cannot_access_another_users_workspace(anon_client):
    first = await register(anon_client, "first@example.com", "first-password", "First User")
    anon_client.headers["Authorization"] = f"Bearer {first['access_token']}"
    organization_response = await anon_client.post(
        f"{API}/organizations", json={"name": "First Org", "description": "Private"}
    )
    assert organization_response.status_code == 201, organization_response.text
    organization = organization_response.json()
    project_response = await anon_client.post(
        f"{API}/organizations/{organization['id']}/projects", json={"name": "Private Project"}
    )
    assert project_response.status_code == 201, project_response.text
    project = project_response.json()
    flag_response = await anon_client.post(
        f"{API}/flags",
        params={"project_id": project["id"]},
        json={"key": "private-flag", "name": "Private Flag"},
    )
    assert flag_response.status_code == 201, flag_response.text

    # Replace the account on the same client with a second user.
    anon_client.headers.pop("Authorization", None)
    second = await register(anon_client, "second@example.com", "second-password", "Second User")
    anon_client.headers["Authorization"] = f"Bearer {second['access_token']}"

    assert (await anon_client.get(f"{API}/organizations")).json() == []
    for path in [
        f"{API}/organizations/{organization['id']}",
        f"{API}/projects/{project['id']}/environments",
        f"{API}/flags?project_id={project['id']}",
        f"{API}/audit?project_id={project['id']}",
        f"{API}/bootstrap?project_id={project['id']}&env=prod",
    ]:
        assert (await anon_client.get(path)).status_code == 404, path
    assert (
        await anon_client.post(
            f"{API}/flags",
            params={"project_id": project["id"]},
            json={"key": "intruder", "name": "Intruder"},
        )
    ).status_code == 404
    assert (
        await anon_client.post(
            f"{API}/evaluate",
            params={"project_id": project["id"]},
            json={"flag_key": "private-flag", "context": {"user_id": "u"}, "env": "prod"},
        )
    ).status_code == 404

    audit_before = await anon_client.get(f"{API}/audit", params={"project_id": project["id"]})
    assert audit_before.status_code == 404

    own_org = await anon_client.post(f"{API}/organizations", json={"name": "Second Org"})
    assert own_org.status_code == 201


@pytest.mark.asyncio
async def test_audit_entries_include_authenticated_attribution(anon_client):
    registered = await register(anon_client, "audit@example.com", "audit-password", "Audit User")
    anon_client.headers["Authorization"] = f"Bearer {registered['access_token']}"
    organization = (await anon_client.post(f"{API}/organizations", json={"name": "Audit Org"})).json()
    project = (
        await anon_client.post(
            f"{API}/organizations/{organization['id']}/projects", json={"name": "Audit Project"}
        )
    ).json()
    await anon_client.post(
        f"{API}/flags",
        params={"project_id": project["id"]},
        json={"key": "audited", "name": "Audited Flag"},
    )
    response = await anon_client.get(f"{API}/audit", params={"project_id": project["id"]})
    assert response.status_code == 200
    entry = next(item for item in response.json() if item["action"] == "flag.created")
    assert entry["user_id"] == registered["user"]["id"]
    assert entry["user_email"] == "audit@example.com"
    assert entry["actor"] == "audit@example.com"


@pytest.mark.asyncio
async def test_auth_failure_rate_limit(anon_client):
    for _ in range(5):
        response = await anon_client.post(
            f"{API}/auth/login", json={"email": "nobody@example.com", "password": "wrong-password"}
        )
        assert response.status_code == 401
    response = await anon_client.post(
        f"{API}/auth/login", json={"email": "nobody@example.com", "password": "wrong-password"}
    )
    assert response.status_code == 429
    assert "Retry-After" in response.headers
