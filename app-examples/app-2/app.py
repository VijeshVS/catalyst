"""Inventory report CLI demonstrating a Catalyst-gated low-stock feature."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Allow running directly from the repository checkout even if the SDK is not
# installed as an editable package in the active Python environment.
SDK_SOURCE = Path(__file__).resolve().parents[2] / "packages" / "catalyst-python-sdk" / "src"
if SDK_SOURCE.is_dir():
    sys.path.insert(0, str(SDK_SOURCE))

from catalyst_sdk import CatalystClient, ConfigurationError
from dotenv import load_dotenv

load_dotenv()

FLAG_KEY = "low-stock-alerts"
INVENTORY = [
    {"name": "Coffee beans", "stock": 4, "reorder_at": 8},
    {"name": "Paper cups", "stock": 32, "reorder_at": 20},
    {"name": "Oat milk", "stock": 6, "reorder_at": 10},
    {"name": "Vanilla syrup", "stock": 2, "reorder_at": 5},
]


def build_client() -> CatalystClient:
    try:
        return CatalystClient(
            sdk_key=os.getenv("CATALYST_SDK_KEY", ""),
            project_id=os.getenv("CATALYST_PROJECT_ID", ""),
            env=os.getenv("CATALYST_ENV", "dev"),
            host=os.getenv("CATALYST_HOST") or None,
        )
    except ConfigurationError as exc:
        raise SystemExit(
            f"Catalyst SDK configuration error: {exc}. Set CATALYST_SDK_KEY "
            "and CATALYST_PROJECT_ID before running this app."
        ) from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Print a sample store inventory report.")
    parser.add_argument("--user-id", default="warehouse-operator", help="Flag targeting user ID")
    parser.add_argument("--plan", default="pro", help="User plan attribute for targeting rules")
    return parser.parse_args()


def print_report(client: CatalystClient, user_id: str, plan: str) -> None:
    # To target by email, include it with the other user attributes:
    # email = "operator@example.com"  # Usually read from the operator's profile.
    # result = client.for_user(user_id, {"plan": plan, "email": email}).evaluate(FLAG_KEY)
    result = client.for_user(user_id, {"plan": plan}).evaluate(FLAG_KEY)

    print("INVENTORY REPORT")
    print("----------------")
    for item in INVENTORY:
        print(f"{item['name']:<18} {item['stock']:>3} in stock")

    print(f"\nFeature: {FLAG_KEY} = {str(result.value).lower()} ({result.reason})")
    if not result.value:
        print("Low-stock alerts are not enabled for this operator.")
        return

    low_stock = [item for item in INVENTORY if item["stock"] <= item["reorder_at"]]
    print("\nLOW-STOCK ALERTS")
    if not low_stock:
        print("All items are above their reorder points.")
        return

    for item in low_stock:
        print(
            f"- Reorder {item['name']}: {item['stock']} left "
            f"(reorder point: {item['reorder_at']})"
        )


def main() -> None:
    args = parse_args()
    try:
        with build_client() as client:
            print_report(client, args.user_id, args.plan)
    except KeyboardInterrupt:
        print("\nReport cancelled.", file=sys.stderr)
        raise SystemExit(130)


if __name__ == "__main__":
    main()
