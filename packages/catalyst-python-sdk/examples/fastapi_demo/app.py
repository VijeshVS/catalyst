"""
Catalyst Python SDK demo.

Shows the three things an application actually needs from a feature flag SDK:

1. A client built once at process startup. Construction does no I/O.
2. A check that reads the current snapshot, so a dashboard toggle lands without
   a restart.
3. A warm snapshot check at boot, so an unreachable API is caught at startup
   rather than on a user's request.

Run against the hosted API (the default), or point it at your own:

    export CATALYST_SDK_KEY="cp_prod_..."
    export CATALYST_PROJECT_ID="<project uuid>"
    export CATALYST_ENV="prod"
    # export CATALYST_HOST="http://localhost:8000"

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

#: Background polling only matters when reads are turned off. With the default
#: read model, every check already picks up a change.
BACKGROUND_REFRESH = os.getenv("CATALYST_BACKGROUND_REFRESH", "").lower() in ("1", "true", "yes")
REFRESH_INTERVAL = float(os.getenv("CATALYST_REFRESH_SECONDS", "30"))

client: Optional[CatalystClient] = None


def build_client() -> CatalystClient:
    """Constructs the client. Raises a clear error if config is missing."""
    try:
        return CatalystClient(
            sdk_key=os.getenv("CATALYST_SDK_KEY", ""),
            project_id=os.getenv("CATALYST_PROJECT_ID", ""),
            # Unset means the hosted API; set it for staging or a local run.
            host=os.getenv("CATALYST_HOST"),
            env=os.getenv("CATALYST_ENV", "prod"),
            # Reads happen per check unless the demo is asked to poll instead.
            refresh_on_evaluate=not BACKGROUND_REFRESH,
        )
    except ConfigurationError as exc:
        raise SystemExit(
            f"SDK configuration error: {exc}\n"
            "Set CATALYST_SDK_KEY and CATALYST_PROJECT_ID before starting."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Warms the snapshot at boot, then reads it as checks come in."""
    global client
    try:
        client = build_client()
    except AuthorizationError as exc:
        # An invalid key is a configuration mistake, not a transient blip.
        raise SystemExit(f"Catalyst rejected the SDK key: {exc}")

    # Fail loudly here rather than discovering a bad key on a user's request.
    if not client.refresh():
        logger.warning(
            "could not read the snapshot at boot; every flag will serve false (error: %s)",
            client.last_error,
        )
    logger.info(
        "snapshot ready: v%s, %d flags for %s from %s",
        client.version, len(client.flag_keys()), client.env, client.host,
    )

    if BACKGROUND_REFRESH:
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

    ``evaluate`` makes one conditional read and then decides locally, so the
    answer reflects the current configuration. ``for_user`` binds this
    request's identity to the shared client; the returned view costs nothing and
    keeps using the one snapshot and one refresh loop the process already has.
    """
    sdk = _require_client()

    attributes: Dict[str, Any] = {}
    if x_user_email:
        attributes["email"] = x_user_email
    if x_plan:
        attributes["plan"] = x_plan

    # `for_user` attaches the identity once, so the check reads as a bare flag
    # name instead of repeating user_id and attributes on every call.
    result = sdk.for_user(user_id, attributes).evaluate("new-checkout")

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
        "flags": sdk.for_user(user_id, attributes).get_all(),
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
    result = sdk.for_user(user_id, attributes).evaluate(flag)
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

    The SDK fails closed, so a down API means every flag serves false. That is
    safe but it is also a feature going dark, so it is reported as not ``ok``.
    """
    sdk = _require_client()
    stats = sdk.stats
    return {
        "ok": sdk.is_ready,
        "degraded": not sdk.is_ready,
        "snapshot_ready": sdk.snapshot is not None,
        "last_read_failed": stats["read_failed"],
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
