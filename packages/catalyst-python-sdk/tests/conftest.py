"""Shared fixtures for the SDK test suite. No network access is required."""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))


class FakeTransport:
    """
    Stands in for :class:`BootstrapTransport`.

    Records the ETag sent on each call and replays queued responses so tests can
    drive the 200 / 304 / error paths deterministically.
    """

    def __init__(
        self,
        payload: Optional[Dict[str, Any]] = None,
        etag: str = 'W/"p1:prod:1"',
    ) -> None:
        self.payload = payload if payload is not None else default_payload()
        self.etag = etag
        self.calls: List[Optional[str]] = []
        self.raise_next: Optional[BaseException] = None
        self.closed = False
        self.project_id = "project-1"
        self.env = "prod"

    def bootstrap(self, etag: Optional[str] = None):
        from catalyst_sdk.transport import FetchResult
        from catalyst_sdk.snapshot import Snapshot
        import time

        self.calls.append(etag)
        if self.raise_next is not None:
            error = self.raise_next
            self.raise_next = None
            raise error

        if etag and etag == self.etag:
            return FetchResult(not_modified=True, etag=self.etag)

        return FetchResult(
            snapshot=Snapshot.from_payload(self.payload, etag=self.etag, fetched_at=time.time()),
            etag=self.etag,
        )

    def close(self) -> None:
        self.closed = True


def default_payload() -> Dict[str, Any]:
    """A snapshot exercising every evaluation branch."""
    return {
        "env": "prod",
        "version": 7,
        "flags": {
            "ai-assistant": {
                "key": "ai-assistant",
                "defaultValue": False,
                "enabled": True,
                "percentage": 0,
                "rules": [
                    {
                        "id": "rule-internal",
                        "priority": 0,
                        "serve": True,
                        "conditions": [
                            {"attr": "email", "op": "ends_with", "value": "@acme.com"}
                        ],
                    },
                    {
                        "id": "rule-beta",
                        "priority": 1,
                        "serve": False,
                        "conditions": [
                            {"attr": "plan", "op": "in", "value": ["free", "trial"]}
                        ],
                    },
                ],
            },
            "new-checkout": {
                "key": "new-checkout",
                "defaultValue": False,
                "enabled": True,
                "percentage": 50,
                "rules": [],
            },
            "killed-flag": {
                "key": "killed-flag",
                "defaultValue": True,
                "enabled": False,
                "percentage": 100,
                "rules": [
                    {
                        "id": "rule-should-not-run",
                        "priority": 0,
                        "serve": True,
                        "conditions": [{"attr": "email", "op": "exists"}],
                    }
                ],
            },
            "versioned": {
                "key": "versioned",
                "defaultValue": False,
                "enabled": True,
                "percentage": 0,
                "rules": [
                    {
                        "id": "rule-version",
                        "priority": 0,
                        "serve": True,
                        "conditions": [
                            {"attr": "app_version", "op": "greater_than_or_equal", "value": "3.2"}
                        ],
                    }
                ],
            },
        },
    }


@pytest.fixture
def transport() -> FakeTransport:
    return FakeTransport()


@pytest.fixture
def make_client(transport, tmp_path):
    """Builds a client wired to the fake transport and an isolated cache dir."""
    from catalyst_sdk import CatalystClient

    created = []

    def _make(**kwargs: Any):
        params = {
            "sdk_key": "cp_prod_testkey000000000000",
            "project_id": "project-1",
            "host": "http://catalyst.invalid",
            "env": "prod",
            "cache_path": str(tmp_path / "cache.json"),
        }
        params.update(kwargs)
        client = CatalystClient(**params)
        # Swap in the fake after construction so no socket is ever opened.
        client._transport = transport
        client._snapshot = None
        try:
            client.refresh()
        except Exception:  # pragma: no cover - only on a broken fixture
            pass
        # The fixture performs the initial load, so zero the counters and let
        # each test assert only the refreshes it triggers itself.
        client._refresh_count = 0
        client._not_modified_count = 0
        created.append(client)
        return client

    yield _make

    for client in created:
        try:
            client.stop_auto_refresh()
        except Exception:  # pragma: no cover
            pass
