"""Shop checkout API demonstrating a request-time Catalyst feature flag."""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from uuid import uuid4

# Allow running directly from the repository checkout even if Uvicorn's Python
# environment does not have the SDK installed as an editable package.
SDK_SOURCE = Path(__file__).resolve().parents[2] / "packages" / "catalyst-python-sdk" / "src"
if SDK_SOURCE.is_dir():
    sys.path.insert(0, str(SDK_SOURCE))

from catalyst_sdk import CatalystClient, ConfigurationError
from dotenv import load_dotenv
from fastapi import FastAPI, Header
from pydantic import BaseModel, Field

load_dotenv()

FLAG_KEY = "express-checkout"


def build_client() -> CatalystClient:
    """Create the SDK client from environment configuration."""
    try:
        return CatalystClient(
            sdk_key=os.getenv("CATALYST_SDK_KEY", ""),
            project_id=os.getenv("CATALYST_PROJECT_ID", ""),
            env=os.getenv("CATALYST_ENV", "dev"),
            host=os.getenv("CATALYST_HOST") or None,
        )
    except ConfigurationError as exc:
        raise RuntimeError(
            f"Catalyst SDK configuration error: {exc}. Set CATALYST_SDK_KEY "
            "and CATALYST_PROJECT_ID before starting the app."
        ) from exc


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.catalyst = build_client()
    try:
        yield
    finally:
        app.state.catalyst.close()


app = FastAPI(title="Catalyst Shop Checkout", lifespan=lifespan)


class CartItem(BaseModel):
    name: str = Field(min_length=1)
    price: float = Field(gt=0)
    quantity: int = Field(gt=0)


class CheckoutRequest(BaseModel):
    items: list[CartItem] = Field(min_length=1)


@app.get("/")
def home() -> dict[str, str]:
    return {
        "app": "Catalyst Shop Checkout",
        "feature_flag": FLAG_KEY,
        "try": "POST /checkout (see /docs for the request body)",
    }


@app.post("/checkout")
def checkout(
    request: CheckoutRequest,
    user_id: Annotated[str, Header(alias="x-user-id")] = "demo-customer",
    plan: Annotated[str, Header(alias="x-plan")] = "standard",
) -> dict[str, object]:
    """Preview a checkout using the flag decision for this customer."""
    sdk: CatalystClient = app.state.catalyst
    result = sdk.for_user(user_id, {"plan": plan, "email": "demo@yahoo.com"}).evaluate(FLAG_KEY)
    # result = sdk.for_user(user_id, {"plan": plan}).evaluate(FLAG_KEY)
    total = round(sum(item.price * item.quantity for item in request.items), 2)

    if result.value:
        flow = "express"
        message = "Express checkout is available; confirm the order in one step."
    else:
        flow = "standard"
        message = "Continue through the standard payment-details checkout."

    return {
        "order_id": str(uuid4()),
        "user_id": user_id,
        "items": [item.model_dump() for item in request.items],
        "total": total,
        "checkout_flow": flow,
        "message": message, 
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "feature_flag": FLAG_KEY}
