"""
Catalyst Python SDK demo.

Shows the three things an application actually needs from a feature flag SDK:

1. Fetch-on-load initialisation, done once at process startup.
2. A background refresh thread so config changes land without a restart.
3. Sub-millisecond, network-free checks inside request handlers.

Run the Catalyst API first (see the repository README), then:

    export CATALYST_SDK_KEY="cp_prod_..."
    export CATALYST_PROJECT_ID="<project uuid>"
    export CATALYST_HOST="http://localhost:8000"
    export CATALYST_ENV="prod"

    python examples/fastapi_demo/app.py

Then try:

    curl localhost:9000/api/checkout?user_id=user_123 \\
      -H 'x-user-email: alice@acme.com' -H 'x-plan: pro'
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from fastapi import FastAPI, Header, HTTPException, Query

from catalyst_sdk import (
    AuthorizationError,
    BootstrapError,
    CatalystClient,
    ConfigurationError,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("catalyst-demo")

REFRESH_INTERVAL = float(os.getenv("CATALYST_REFRESH_SECONDS", "30"))

client: Optional[CatalystClient] = None


def build_client() -> CatalystClient:
    """Constructs the client. Raises a clear error if config is missing."""
    try:
        return CatalystClient(
            sdk_key=os.getenv("CATALYST_SDK_KEY", ""),
            project_id=os.getenv("CATALYST_PROJECT_ID", ""),
            host=os.getenv("CATALYST_HOST", "http://localhost:8000"),
            env=os.getenv("CATALYST_ENV", "prod"),
            # Seed the snapshot from disk first so a restart is instant and can
            # survive a momentarily unreachable API.
            cache_path=None if os.getenv("CATALYST_NO_CACHE") else True,
        )
    except ConfigurationError as exc:
        raise SystemExit(
            f"SDK configuration error: {exc}\n"
            "Set CATALYST_SDK_KEY and CATALYST_PROJECT_ID before starting."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Loads the snapshot once, then keeps it fresh in the background."""
    global client
    try:
        client = build_client()
    except AuthorizationError as exc:
        # An invalid key is a configuration mistake, not a transient blip.
        raise SystemExit(f"Catalyst rejected the SDK key: {exc}")

    if client.is_ready:
        logger.info(
            "snapshot ready: v%s, %d flags for %s",
            client.version, len(client.flag_keys()), client.env,
        )
    else:
        logger.warning(
            "no snapshot available; every flag will serve its safe default (network: %s)",
            client.last_error,
        )

    client.start_auto_refresh(
        interval=REFRESH_INTERVAL,
        on_error=lambda exc: logger.warning("refresh failed: %s", exc),
    )
    try:
        yield
    finally:
        client.stop_auto_refresh()
        client.close()


app = FastAPI(title="Catalyst SDK demo", lifespan=lifespan)


def _require_client() -> CatalystClient:
    if client is None:  # pragma: no cover - lifespan always sets it
        raise HTTPException(status_code=503, detail="SDK not initialised")
    return client


@app.get("/")
def index() -> Dict[str, Any]:
    return {
        "service": "sdk-catalyst-demo",
        "endpoints": [
            "GET /api/checkout?user_id=...  (x-user-email / x-plan headers)",
            "GET /api/flags?user_id=...     (evaluate every flag once)",
            "GET /api/inspect?flag=...      (explain a single decision)",
            "GET /health                   (snapshot freshness + stats)",
        ],
    }


@app.get("/api/checkout")
def checkout(
    user_id: str = Query("user_123"),
    x_user_email: Optional[str] = Header(default=None),
    x_plan: Optional[str] = Query(default=None, alias="plan"),
) -> Dict[str, Any]:
    """
    The classic use case: gate a feature with a flag and show which rule fired.

    ``is_enabled`` is a local, in-memory lookup, so this handler does no I/O.
    """
    sdk = _require_client()

    attributes: Dict[str, Any] = {}
    if x_user_email:
        attributes["email"] = x_user_email
    if x_plan:
        attributes["plan"] = x_plan

    result = sdk.evaluate("new-checkout", user_id=user_id, attributes=attributes)

    # Contrast the SDK against the server so the demo shows they agree.
    return {
        "user_id": user_id,
        "attributes": attributes,
        "feature_enabled": result.value,
        "reason": result.reason,
        "matched_rule_id": result.rule_id,
        "snapshot_version": result.flag_version,
        "ui": {
            "button_label": "Place order" if result.value else "Coming soon",
            "express_checkout": result.value,
        },
    }


@app.get("/api/flags")
def all_flags(
    user_id: str = Query("user_123"),
    plan: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    """Evaluates the whole snapshot in one pass, e.g. to render a config."""
    sdk = _require_client()
    attributes = {"plan": plan} if plan else {}
    return {
        "user_id": user_id,
        "attributes": attributes,
        "flags": sdk.get_all(user_id=user_id, attributes=attributes),
    }


@app.get("/api/inspect")
def inspect(
    flag: str = Query(...),
    user_id: str = Query("user_123"),
    email: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    """Explains a decision, which is what you reach for when debugging."""
    sdk = _require_client()
    attributes = {"email": email} if email else {}
    result = sdk.evaluate(flag, user_id=user_id, attributes=attributes)
    return {
        "flag": flag,
        "user_id": user_id,
        "attributes": attributes,
        "value": result.value,
        "reason": result.reason,
        "matched_rule_id": result.rule_id,
        "known_flag": flag in sdk.flag_keys(),
    }


@app.get("/health")
def health() -> Dict[str, Any]:
    """
    Distinguishes "API is down" from "API is reachable and we are current".

    ``ok`` stays true while a stale snapshot is being served, because the
    service is still returning correct-but-older decisions.
    """
    sdk = _require_client()
    stats = sdk.stats
    return {
        "ok": True,
        "degraded": not sdk.is_ready,
        "snapshot_ready": sdk.is_ready,
        "snapshot_version": stats["version"],
        "last_successful_refresh": (
            time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(stats["last_refresh_ok"]))
            if stats["last_refresh_ok"]
            else None
        ),
        "last_error": stats["last_error"],
        **stats,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "9000")))
