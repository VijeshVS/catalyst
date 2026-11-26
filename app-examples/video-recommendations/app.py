"""Reelwise — a video recommendation demo gated by Catalyst feature flags.

The FastAPI process owns one Catalyst client. Every request refreshes the
snapshot once (a conditional GET, so an unchanged environment is a cheap 304)
and then evaluates the five demo flags locally for the simulated viewer.

The ranking itself is plain Python in `recommender.py`; the flags decide which
signals are allowed to run, and every response explains the decision.
"""

from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

# Allow running directly from the repository checkout even if the SDK is not
# installed as an editable package in the active Python environment.
SDK_SOURCE = Path(__file__).resolve().parents[2] / "packages" / "catalyst-python-sdk" / "src"
if SDK_SOURCE.is_dir():
    sys.path.insert(0, str(SDK_SOURCE))

from catalyst_sdk import (
    BootstrapError,
    CatalystClient,
    ConfigurationError,
    get_user_bucket,
)
from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from catalog import COUNTRY_LABELS, GENRES, PLANS
from recommender import early_access_shelf, rank_personalized, trending

load_dotenv(Path(__file__).resolve().parent / ".env")

logger = logging.getLogger("reelwise")

FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"

# (key, label, kind, description) — kind drives the badge in the UI.
FLAG_META: list[tuple[str, str, str, str]] = [
    (
        "recommendation-engine",
        "Personalized engine",
        "master",
        "Master switch. Off serves the global trending rail.",
    ),
    (
        "location-aware-ranking",
        "Location-aware ranking",
        "targeting",
        "Boosts titles that are popular in the viewer's market.",
    ),
    (
        "genre-affinity-boost",
        "Genre affinity boost",
        "targeting",
        "Ranks titles in the genre the viewer watches most.",
    ),
    (
        "premium-shelf",
        "Premium early access",
        "targeting",
        "Shows the early-access rail to paid plans only.",
    ),
    (
        "autoplay-previews",
        "Autoplay previews",
        "rollout",
        "Sticky 50% rollout: the same viewer always gets the same side.",
    ),
]

FLAG_KEYS = [key for key, *_ in FLAG_META]


def build_client() -> CatalystClient:
    """Create the SDK client from the example's local .env."""
    try:
        return CatalystClient(
            sdk_key=os.getenv("CATALYST_SDK_KEY", ""),
            project_id=os.getenv("CATALYST_PROJECT_ID", ""),
            env=os.getenv("CATALYST_ENV", "dev"),
            host=os.getenv("CATALYST_HOST") or None,
            # One explicit refresh per request, then five local decisions.
            refresh_on_evaluate=False,
        )
    except ConfigurationError as exc:
        raise RuntimeError(
            f"Catalyst SDK configuration error: {exc}. Copy .env.example to "
            ".env and fill in CATALYST_SDK_KEY and CATALYST_PROJECT_ID."
        ) from exc


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = build_client()
    app.state.catalyst = client
    try:
        # Warm the snapshot so the first browser request is served from memory.
        client.refresh()
    except BootstrapError as exc:
        logger.warning("Catalyst warm-up failed; requests will fail closed: %s", exc)
    try:
        yield
    finally:
        client.close()


app = FastAPI(
    title="Reelwise — Catalyst video recommendations",
    description="A light-themed recommendation platform whose ranking is gated by Catalyst flags.",
    lifespan=lifespan,
)


def _normalise_country(value: str) -> str:
    code = value.strip().upper()
    return code if code in COUNTRY_LABELS else ""


def _normalise_genre(value: str) -> str:
    wanted = value.strip().lower()
    for genre in GENRES:
        if genre.lower() == wanted:
            return genre
    return ""


def _normalise_plan(value: str) -> str:
    plan = value.strip().lower()
    return plan if plan in PLANS else "free"


def _flag_payload(
    client: CatalystClient, viewer: Any, user_id: str
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Evaluate every demo flag and shape it for both logic and the UI."""
    results: dict[str, Any] = {
        key: viewer.evaluate(key) for key in FLAG_KEYS
    }
    snapshot = client.snapshot
    entries: list[dict[str, Any]] = []

    for key, label, kind, description in FLAG_META:
        result = results[key]
        flag = snapshot.get(key) if snapshot else None
        percentage = flag.percentage if flag else None
        entries.append(
            {
                "key": key,
                "label": label,
                "description": description,
                "kind": kind,
                "value": result.value,
                "reason": result.reason,
                "rule_id": result.rule_id,
                "percentage": percentage,
                # A sticky bucket makes the percentage rollout concrete.
                "bucket": (
                    get_user_bucket(key, user_id)
                    if percentage is not None and percentage < 100
                    else None
                ),
            }
        )

    return results, {entry["key"]: entry for entry in entries}


@app.get("/api/recommendations")
def recommendations(
    user_id: str = Query(default="viewer-1", max_length=80),
    country: str = Query(default="IN", max_length=8),
    genre: str = Query(default="Sci-Fi", max_length=32),
    plan: str = Query(default="premium", max_length=16),
) -> JSONResponse:
    """Refresh the snapshot once, evaluate the flags, then rank locally."""
    client: CatalystClient = app.state.catalyst
    user_id = user_id.strip() or "viewer-1"
    country_code = _normalise_country(country)
    genre_value = _normalise_genre(genre)
    plan_value = _normalise_plan(plan)

    notice: str | None = None
    try:
        client.refresh()
    except BootstrapError as exc:
        logger.warning("Catalyst refresh failed; failing closed: %s", exc)

    degraded = not client.is_ready
    if degraded:
        notice = (
            "Catalyst could not be reached. The SDK failed closed, so every "
            "flag is false and Reelwise is serving its fallback rail."
        )

    attributes: dict[str, Any] = {"plan": plan_value}
    if country_code:
        attributes["country"] = country_code
    if genre_value:
        attributes["favorite_genre"] = genre_value

    viewer = client.for_user(user_id, attributes)
    results, flags_by_key = _flag_payload(client, viewer, user_id)

    engine_on = results["recommendation-engine"].value
    if engine_on and not degraded:
        items = rank_personalized(
            country_code,
            genre_value,
            use_location=results["location-aware-ranking"].value,
            use_genre=results["genre-affinity-boost"].value,
        )
        mode = "personalized"
    else:
        items = trending()
        mode = "trending"
        if not degraded and notice is None:
            notice = (
                "The recommendation-engine master switch is off, so Reelwise "
                "is serving the global trending fallback."
            )

    recommended_ids = {item["id"] for item in items}
    shelf = (
        early_access_shelf(recommended_ids)
        if results["premium-shelf"].value
        else []
    )

    snapshot = client.snapshot
    payload = {
        "audience": {
            "user_id": user_id,
            "country": country_code,
            "country_label": COUNTRY_LABELS.get(country_code, "Global"),
            "genre": genre_value,
            "genre_label": genre_value or "Surprise me",
            "plan": plan_value,
        },
        "mode": mode,
        "engine": {
            "value": results["recommendation-engine"].value,
            "reason": results["recommendation-engine"].reason,
            "rule_id": results["recommendation-engine"].rule_id,
        },
        "recommendations": items,
        "premium_shelf": shelf,
        "autoplay": {
            "value": results["autoplay-previews"].value,
            "reason": results["autoplay-previews"].reason,
            "bucket": get_user_bucket("autoplay-previews", user_id),
        },
        "flags": [flags_by_key[key] for key in FLAG_KEYS],
        "snapshot": {
            "env": snapshot.env if snapshot else os.getenv("CATALYST_ENV", "dev"),
            "version": snapshot.version if snapshot else 0,
            "host": client.host,
            "refreshes": client.stats["refreshes"],
            "not_modified": client.stats["not_modified"],
            "flag_count": len(snapshot) if snapshot else 0,
            "degraded": degraded,
        },
        "notice": notice,
    }
    return JSONResponse(payload, headers={"cache-control": "no-store"})


@app.get("/api/health")
def health() -> dict[str, Any]:
    client: CatalystClient = app.state.catalyst
    return {
        "status": "ok",
        "sdk": client.stats,
        "flags": client.flag_keys(),
    }


# Registered last so /api/* is matched before the static mount.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
