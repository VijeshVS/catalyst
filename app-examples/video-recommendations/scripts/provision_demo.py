#!/usr/bin/env python3
"""Provision the Reelwise video-recommendation demo on a Catalyst deployment.

The script is safe to re-run. It signs in to (or registers) a demo account,
finds or creates the demo organization and project, creates the flags and
targeting rules, sets each flag's dev state, and mints one SDK key.

The raw SDK key is returned by the API exactly once, at creation. This script
prints it and, with --write-env, writes it to the example's local .env, which
is gitignored.

Usage:
    uv run --with httpx python scripts/provision_demo.py --write-env
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HOST = os.getenv("CATALYST_HOST", "https://catalyst-api-uakz.onrender.com")
ENV = "dev"

EMAIL = os.getenv("REELWISE_EMAIL", "reelwise-demo@example.com")
# No default: a committed demo password would be a working credential on the
# deployed API, and scanners rightly flag it. Supply it through the environment.
PASSWORD = os.getenv("REELWISE_PASSWORD", "")
FULL_NAME = "Reelwise Demo"

ORG_NAME = os.getenv("REELWISE_ORG", "Reelwise")
ORG_DESCRIPTION = "Demo account for the Catalyst video recommendation example."
PROJECT_NAME = "Video Recommendations"
KEY_NAME = "reelwise-demo"

# Each flag is deliberately a different kind of rollout so the demo can show
# the whole evaluation order: master switch, attribute rules, and a sticky
# percentage. New flags start at 0% and off, so every state is set explicitly.
FLAGS: list[dict[str, Any]] = [
    {
        "key": "recommendation-engine",
        "name": "Personalized recommendation engine",
        "description": "Master switch. Off serves the global trending rail.",
        "state": {"enabled": True, "enable_all": True, "percentage": 100},
        "rules": [],
    },
    {
        "key": "location-aware-ranking",
        "name": "Location-aware ranking",
        "description": "Boosts titles that are popular in the viewer's market.",
        "state": {"enabled": True, "enable_all": False, "percentage": 100},
        "rules": [
            {
                "name": "Supported markets",
                "conditions": [
                    {
                        "attr": "country",
                        "op": "in",
                        "value": ["IN", "US", "GB", "JP", "DE", "BR"],
                    }
                ],
                "serve": True,
            }
        ],
    },
    {
        "key": "genre-affinity-boost",
        "name": "Genre affinity boost",
        "description": "Ranks titles in the genre the viewer watches most.",
        "state": {"enabled": True, "enable_all": False, "percentage": 100},
        "rules": [
            {
                "name": "Viewer has a favourite genre",
                "conditions": [{"attr": "favorite_genre", "op": "exists", "value": True}],
                "serve": True,
            }
        ],
    },
    {
        "key": "premium-shelf",
        "name": "Premium early-access shelf",
        "description": "Shows the early-access rail to paid plans only.",
        "state": {"enabled": True, "enable_all": False, "percentage": 100},
        "rules": [
            {
                "name": "Paid plans",
                "conditions": [
                    {"attr": "plan", "op": "in", "value": ["premium", "family"]}
                ],
                "serve": True,
            }
        ],
    },
    {
        "key": "autoplay-previews",
        "name": "Autoplay previews",
        "description": "Sticky 50% rollout: the same viewer always gets the same side.",
        "state": {"enabled": True, "enable_all": False, "percentage": 50},
        "rules": [],
    },
]


def die(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def check(response: httpx.Response, expected: tuple[int, ...], what: str) -> Any:
    if response.status_code not in expected:
        die(f"{what} failed ({response.status_code}): {response.text[:400]}")
    return response.json() if response.content else None


def authenticate(client: httpx.Client) -> str:
    payload = {"email": EMAIL, "password": PASSWORD, "full_name": FULL_NAME}
    response = client.post("/api/v1/auth/register", json=payload)
    if response.status_code == 201:
        print(f"Registered demo account {EMAIL}")
        return response.json()["access_token"]
    if response.status_code != 409:
        die(f"registration failed ({response.status_code}): {response.text[:400]}")

    response = client.post(
        "/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}
    )
    if response.status_code == 401:
        die(
            f"{EMAIL} exists but the password does not match. Set REELWISE_EMAIL "
            "and REELWISE_PASSWORD to the existing demo account."
        )
    check(response, (200,), "login")
    print(f"Signed in as existing demo account {EMAIL}")
    return response.json()["access_token"]


def find_organization(client: httpx.Client) -> dict[str, Any]:
    organizations = check(client.get("/api/v1/organizations"), (200,), "list organizations")
    for organization in organizations:
        if organization["name"] == ORG_NAME:
            return organization

    response = client.post(
        "/api/v1/organizations",
        json={"name": ORG_NAME, "description": ORG_DESCRIPTION},
    )
    if response.status_code == 409:
        die(
            f"organization '{ORG_NAME}' is owned by another account on this "
            "deployment. Set REELWISE_ORG to a different name."
        )
    return check(response, (201,), "create organization")


def find_project(client: httpx.Client, organization: dict[str, Any]) -> dict[str, Any]:
    for project in organization.get("projects", []):
        if project["name"] == PROJECT_NAME:
            return project

    return check(
        client.post(
            f"/api/v1/organizations/{organization['id']}/projects",
            json={"name": PROJECT_NAME},
        ),
        (201,),
        "create project",
    )


def ensure_flags(client: httpx.Client, project_id: str) -> list[str]:
    existing = check(
        client.get("/api/v1/flags", params={"project_id": project_id}),
        (200,),
        "list flags",
    )
    by_key = {flag["key"]: flag for flag in existing}
    created: list[str] = []

    for spec in FLAGS:
        key = spec["key"]
        if key in by_key:
            print(f"  flag {key}: already exists")
            continue

        response = client.post(
            "/api/v1/flags",
            params={"project_id": project_id},
            json={
                "key": key,
                "name": spec["name"],
                "description": spec["description"],
            },
        )
        check(response, (201,), f"create flag {key}")
        created.append(key)
        print(f"  flag {key}: created")

    return created


def configure_flag(client: httpx.Client, project_id: str, spec: dict[str, Any]) -> None:
    key = spec["key"]
    base = f"/api/v1/flags/{key}/environments/{ENV}"

    check(
        client.patch(
            base,
            params={"project_id": project_id},
            json=spec["state"],
        ),
        (200,),
        f"set state for {key}",
    )

    current_rules = check(
        client.get(f"{base}/rules", params={"project_id": project_id}),
        (200,),
        f"list rules for {key}",
    )
    if current_rules:
        print(f"  {key}: {len(current_rules)} rule(s) already present")
        return

    for rule in spec["rules"]:
        check(
            client.post(
                f"{base}/rules",
                params={"project_id": project_id},
                json=rule,
            ),
            (201,),
            f"create rule for {key}",
        )
        print(f"  {key}: rule '{rule['name']}' created")


def ensure_sdk_key(client: httpx.Client, project_id: str) -> tuple[str | None, str | None]:
    listing = check(
        client.get(f"/api/v1/projects/{project_id}/keys"),
        (200,),
        "list API keys",
    )
    for key in listing["keys"]:
        if key["name"] == KEY_NAME:
            return None, key["id"]

    response = client.post(
        f"/api/v1/projects/{project_id}/keys",
        json={"name": KEY_NAME, "env": ENV},
    )
    payload = check(response, (201,), "create SDK key")
    return payload["key"], payload["id"]


def write_env(host: str, project_id: str, sdk_key: str | None) -> None:
    path = ROOT / ".env"
    existing = path.read_text() if path.exists() else ""

    def current(name: str) -> str:
        for line in existing.splitlines():
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip()
        return ""

    resolved_key = sdk_key or current("CATALYST_SDK_KEY")
    if not resolved_key:
        die(
            "an SDK key named "
            f"'{KEY_NAME}' already exists but its raw value cannot be read again. "
            "Delete it in the dashboard and re-run, or paste the key into .env."
        )

    lines = [
        "# Local-only configuration for the Reelwise demo. Never commit this file.",
        f"CATALYST_SDK_KEY={resolved_key}",
        f"CATALYST_PROJECT_ID={project_id}",
        f"CATALYST_ENV={ENV}",
    ]
    if host.rstrip("/") != "https://catalyst-api-uakz.onrender.com":
        lines.append(f"CATALYST_HOST={host.rstrip('/')}")
    lines.extend(
        [
            "",
            "# Demo account for the Catalyst dashboard (change the password after the demo).",
            f"REELWISE_EMAIL={EMAIL}",
            f"REELWISE_PASSWORD={PASSWORD}",
            "",
        ]
    )
    path.write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST, help="Catalyst API origin")
    parser.add_argument(
        "--write-env",
        action="store_true",
        help="Write CATALYST_SDK_KEY / project settings to this example's .env",
    )
    args = parser.parse_args()
    host = args.host.rstrip("/")

    if not PASSWORD:
        die(
            "REELWISE_PASSWORD is required so the script can register or sign in "
            "to the demo account. Export it first, e.g. "
            "REELWISE_PASSWORD='<password>' uv run --with httpx "
            "python scripts/provision_demo.py --write-env"
        )

    print(f"Catalyst API: {host}")
    with httpx.Client(base_url=host, timeout=90.0) as client:
        token = authenticate(client)
        client.headers["Authorization"] = f"Bearer {token}"

        organization = find_organization(client)
        print(f"Organization: {organization['name']} ({organization['id']})")

        project = find_project(client, organization)
        print(f"Project: {project['name']} ({project['id']})")

        print("Flags:")
        ensure_flags(client, project["id"])
        for spec in FLAGS:
            configure_flag(client, project["id"], spec)

        sdk_key, key_id = ensure_sdk_key(client, project["id"])

        print("\nDone.")
        print(f"  project_id: {project['id']}")
        print(f"  env:        {ENV}")
        print(f"  key_id:     {key_id}")
        if sdk_key:
            print(f"  sdk_key:    {sdk_key}")
            print("  (shown once; also written to .env with --write-env)")
        else:
            print(
                f"  sdk_key:    an existing '{KEY_NAME}' key was reused; its raw "
                "value is in .env"
            )
        print("\nDashboard: https://catalyst-service.vercel.app")

        if args.write_env:
            write_env(host, project["id"], sdk_key)
            print(f"Wrote {ROOT / '.env'}")


if __name__ == "__main__":
    main()
