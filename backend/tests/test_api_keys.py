"""Tests for API Key management and SDK authentication."""

import pytest
from httpx import AsyncClient
from app.main import app

API = "/api/v1"


@pytest.mark.asyncio
async def test_create_api_key(anon_client):
    """Test creating a new API key for a project."""
    # Register and login
    register = await anon_client.post(
        f"{API}/auth/register",
        json={
            "email": "keyuser@example.com",
            "password": "password123",
            "full_name": "Key User",
        },
    )
    assert register.status_code == 201
    anon_client.headers["Authorization"] = f"Bearer {register.json()['access_token']}"

    # Create organization
    org = await anon_client.post(
        f"{API}/organizations",
        json={"name": "Test Org", "description": "Org for key tests"},
    )
    assert org.status_code == 201
    org_id = org.json()["id"]

    # Create project
    project = await anon_client.post(
        f"{API}/organizations/{org_id}/projects",
        json={"name": "Test Project"},
    )
    assert project.status_code == 201
    project_id = project.json()["id"]

    # Create API key
    key_response = await anon_client.post(
        f"{API}/projects/{project_id}/keys",
        json={"name": "Production SDK Key", "env": "prod"},
    )
    assert key_response.status_code == 201
    key_data = key_response.json()

    # Verify response structure
    assert key_data["name"] == "Production SDK Key"
    assert key_data["env"] == "prod"
    assert key_data["prefix"].startswith("cp_prod_")
    # cp_prod_ (8 chars) + 22 chars from token_urlsafe(16)
    assert len(key_data["prefix"]) == 30
    assert key_data["revoked"] is False


@pytest.mark.asyncio
async def test_list_api_keys(anon_client):
    """Test listing API keys for a project."""
    # Register and login
    register = await anon_client.post(
        f"{API}/auth/register",
        json={
            "email": "listuser@example.com",
            "password": "password123",
            "full_name": "List User",
        },
    )
    assert register.status_code == 201
    anon_client.headers["Authorization"] = f"Bearer {register.json()['access_token']}"

    # Create organization and project
    org = await anon_client.post(
        f"{API}/organizations",
        json={"name": "List Test Org"},
    )
    assert org.status_code == 201
    org_id = org.json()["id"]

    project = await anon_client.post(
        f"{API}/organizations/{org_id}/projects",
        json={"name": "List Test Project"},
    )
    assert project.status_code == 201
    project_id = project.json()["id"]

    # Create two API keys
    key1 = await anon_client.post(
        f"{API}/projects/{project_id}/keys",
        json={"name": "Dev Key", "env": "dev"},
    )
    assert key1.status_code == 201

    key2 = await anon_client.post(
        f"{API}/projects/{project_id}/keys",
        json={"name": "Prod Key", "env": "prod"},
    )
    assert key2.status_code == 201

    # List keys
    list_response = await anon_client.get(f"{API}/projects/{project_id}/keys")
    assert list_response.status_code == 200
    keys_data = list_response.json()

    assert "keys" in keys_data
    assert len(keys_data["keys"]) == 2

    # Verify key details
    key_names = [k["name"] for k in keys_data["keys"]]
    assert "Dev Key" in key_names
    assert "Prod Key" in key_names


@pytest.mark.asyncio
async def test_revoke_api_key(anon_client):
    """Test revoking an API key."""
    # Register and login
    register = await anon_client.post(
        f"{API}/auth/register",
        json={
            "email": "revokeuser@example.com",
            "password": "password123",
            "full_name": "Revoke User",
        },
    )
    assert register.status_code == 201
    anon_client.headers["Authorization"] = f"Bearer {register.json()['access_token']}"

    # Create organization and project
    org = await anon_client.post(
        f"{API}/organizations",
        json={"name": "Revoke Test Org"},
    )
    assert org.status_code == 201
    org_id = org.json()["id"]

    project = await anon_client.post(
        f"{API}/organizations/{org_id}/projects",
        json={"name": "Revoke Test Project"},
    )
    assert project.status_code == 201
    project_id = project.json()["id"]

    # Create API key
    key_response = await anon_client.post(
        f"{API}/projects/{project_id}/keys",
        json={"name": "To Be Revoked", "env": "prod"},
    )
    assert key_response.status_code == 201
    key_id = key_response.json()["id"]

    # Revoke the key
    revoke_response = await anon_client.delete(
        f"{API}/projects/{project_id}/keys/{key_id}",
    )
    assert revoke_response.status_code == 204

    # Verify key is revoked
    list_response = await anon_client.get(f"{API}/projects/{project_id}/keys")
    assert list_response.status_code == 200
    keys_data = list_response.json()

    revoked_key = next(k for k in keys_data["keys"] if k["id"] == key_id)
    assert revoked_key["revoked"] is True


@pytest.mark.asyncio
async def test_sdk_key_authentication(anon_client):
    """Test that SDK keys can authenticate to /bootstrap endpoint."""
    # Register and login
    register = await anon_client.post(
        f"{API}/auth/register",
        json={
            "email": "sdkuser@example.com",
            "password": "password123",
            "full_name": "SDK User",
        },
    )
    assert register.status_code == 201
    anon_client.headers["Authorization"] = f"Bearer {register.json()['access_token']}"

    # Create organization and project
    org = await anon_client.post(
        f"{API}/organizations",
        json={"name": "SDK Auth Org"},
    )
    assert org.status_code == 201
    org_id = org.json()["id"]

    project = await anon_client.post(
        f"{API}/organizations/{org_id}/projects",
        json={"name": "SDK Auth Project"},
    )
    assert project.status_code == 201
    project_id = project.json()["id"]

    # Create a flag for the project
    flag = await anon_client.post(
        f"{API}/flags",
        params={"project_id": project_id},
        json={"key": "test-flag", "name": "Test Flag", "default_value": True},
    )
    assert flag.status_code == 201

    # Create API key
    key_response = await anon_client.post(
        f"{API}/projects/{project_id}/keys",
        json={"name": "SDK Key", "env": "prod"},
    )
    assert key_response.status_code == 201
    api_key = key_response.json()["prefix"]

    # List keys to verify
    list_response = await anon_client.get(f"{API}/projects/{project_id}/keys")
    assert list_response.status_code == 200

    # Use SDK key to authenticate to /bootstrap
    anon_client.headers.pop("Authorization", None)
    bootstrap_response = await anon_client.get(
        f"{API}/bootstrap",
        params={"project_id": project_id, "env": "prod"},
        headers={"X-SDK-Key": api_key},
    )
    assert bootstrap_response.status_code == 200
    bootstrap_data = bootstrap_response.json()
    assert "flags" in bootstrap_data
    assert "test-flag" in bootstrap_data["flags"]


@pytest.mark.asyncio
async def test_sdk_key_with_invalid_project(anon_client):
    """Test that SDK key cannot access a different project."""
    # Register and login
    register = await anon_client.post(
        f"{API}/auth/register",
        json={
            "email": "crossuser@example.com",
            "password": "password123",
            "full_name": "Cross User",
        },
    )
    assert register.status_code == 201
    anon_client.headers["Authorization"] = f"Bearer {register.json()['access_token']}"

    # Create two orgs
    org1 = await anon_client.post(
        f"{API}/organizations",
        json={"name": "Org 1"},
    )
    assert org1.status_code == 201
    org1_id = org1.json()["id"]

    org2 = await anon_client.post(
        f"{API}/organizations",
        json={"name": "Org 2"},
    )
    assert org2.status_code == 201
    org2_id = org2.json()["id"]

    # Create project in org1
    project1 = await anon_client.post(
        f"{API}/organizations/{org1_id}/projects",
        json={"name": "Project 1"},
    )
    assert project1.status_code == 201
    project1_id = project1.json()["id"]

    # Create project in org2
    project2 = await anon_client.post(
        f"{API}/organizations/{org2_id}/projects",
        json={"name": "Project 2"},
    )
    assert project2.status_code == 201
    project2_id = project2.json()["id"]

    # Create flag in project1
    flag1 = await anon_client.post(
        f"{API}/flags",
        params={"project_id": project1_id},
        json={"key": "flag1", "name": "Flag 1", "default_value": True},
    )
    assert flag1.status_code == 201

    # Create flag in project2
    flag2 = await anon_client.post(
        f"{API}/flags",
        params={"project_id": project2_id},
        json={"key": "flag2", "name": "Flag 2", "default_value": False},
    )
    assert flag2.status_code == 201

    # Create API key for project1
    key_response = await anon_client.post(
        f"{API}/projects/{project1_id}/keys",
        json={"name": "Key 1", "env": "prod"},
    )
    assert key_response.status_code == 201
    api_key = key_response.json()["prefix"]

    # Try to access project2 with project1's API key
    anon_client.headers.pop("Authorization", None)
    response = await anon_client.get(
        f"{API}/bootstrap",
        params={"project_id": project2_id, "env": "prod"},
        headers={"X-SDK-Key": api_key},
    )
    # Should return 403 Forbidden (not 404 to distinguish from missing key)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_revoked_sdk_key_denied(anon_client):
    """Test that revoked SDK keys are denied access."""
    # Register and login
    register = await anon_client.post(
        f"{API}/auth/register",
        json={
            "email": "revokeduser@example.com",
            "password": "password123",
            "full_name": "Revoked User",
        },
    )
    assert register.status_code == 201
    anon_client.headers["Authorization"] = f"Bearer {register.json()['access_token']}"

    # Create organization and project
    org = await anon_client.post(
        f"{API}/organizations",
        json={"name": "Revoked Test Org"},
    )
    assert org.status_code == 201
    org_id = org.json()["id"]

    project = await anon_client.post(
        f"{API}/organizations/{org_id}/projects",
        json={"name": "Revoked Test Project"},
    )
    assert project.status_code == 201
    project_id = project.json()["id"]

    # Create API key
    key_response = await anon_client.post(
        f"{API}/projects/{project_id}/keys",
        json={"name": "Revoked Key", "env": "prod"},
    )
    assert key_response.status_code == 201
    api_key = key_response.json()["prefix"]

    # Revoke the key
    key_id = key_response.json()["id"]
    revoke_response = await anon_client.delete(
        f"{API}/projects/{project_id}/keys/{key_id}",
    )
    assert revoke_response.status_code == 204

    # Try to use revoked key
    anon_client.headers.pop("Authorization", None)
    response = await anon_client.get(
        f"{API}/bootstrap",
        params={"project_id": project_id, "env": "prod"},
        headers={"X-SDK-Key": api_key},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_sdk_key_cannot_access_evaluate_endpoint(anon_client):
    """Test that SDK keys can authenticate to /evaluate endpoint."""
    # Register and login
    register = await anon_client.post(
        f"{API}/auth/register",
        json={
            "email": "evaluser@example.com",
            "password": "password123",
            "full_name": "Eval User",
        },
    )
    assert register.status_code == 201
    anon_client.headers["Authorization"] = f"Bearer {register.json()['access_token']}"

    # Create organization and project
    org = await anon_client.post(
        f"{API}/organizations",
        json={"name": "Eval Auth Org"},
    )
    assert org.status_code == 201
    org_id = org.json()["id"]

    project = await anon_client.post(
        f"{API}/organizations/{org_id}/projects",
        json={"name": "Eval Auth Project"},
    )
    assert project.status_code == 201
    project_id = project.json()["id"]

    # Create a flag
    flag = await anon_client.post(
        f"{API}/flags",
        params={"project_id": project_id},
        json={"key": "eval-test", "name": "Eval Test", "default_value": True},
    )
    assert flag.status_code == 201

    # Create API key
    key_response = await anon_client.post(
        f"{API}/projects/{project_id}/keys",
        json={"name": "Eval SDK Key", "env": "prod"},
    )
    assert key_response.status_code == 201
    api_key = key_response.json()["prefix"]

    # Use SDK key to authenticate to /evaluate
    anon_client.headers.pop("Authorization", None)
    eval_response = await anon_client.post(
        f"{API}/evaluate",
        params={"project_id": project_id},
        json={
            "flag_key": "eval-test",
            "context": {"user_id": "user123", "attributes": {}},
            "env": "prod",
        },
        headers={"X-SDK-Key": api_key},
    )
    assert eval_response.status_code == 200
    eval_data = eval_response.json()
    assert eval_data["flag_key"] == "eval-test"
    assert eval_data["value"] is True
