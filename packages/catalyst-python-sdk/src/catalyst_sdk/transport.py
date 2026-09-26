"""
HTTP transport for the bootstrap endpoint.

Responsibilities are deliberately narrow: build the request, send it, and
classify the result as *fresh*, *not modified*, or *failed*. All caching
decisions live in :mod:`catalyst_sdk.client`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import httpx

from .snapshot import Snapshot


class CatalystError(Exception):
    """Base error for the SDK."""


class ConfigurationError(CatalystError):
    """The client was constructed with unusable settings."""


class BootstrapError(CatalystError):
    """The bootstrap request failed and no usable snapshot exists."""


class AuthorizationError(BootstrapError):
    """The SDK key or host was rejected."""


@dataclass
class FetchResult:
    """Outcome of a single conditional bootstrap attempt."""

    #: A new snapshot was returned (HTTP 200).
    snapshot: Optional[Snapshot] = None
    #: Server confirmed the cached snapshot is still current (HTTP 304).
    not_modified: bool = False
    #: ETag echoed by the server, for either a 200 or a 304.
    etag: Optional[str] = None

    @property
    def changed(self) -> bool:
        return self.snapshot is not None


class BootstrapTransport:
    """Fetches ``/api/v1/bootstrap`` with conditional-request support."""

    def __init__(
        self,
        host: str,
        sdk_key: str,
        project_id: str,
        env: str = "prod",
        timeout: float = 5.0,
        client: Optional[httpx.Client] = None,
    ) -> None:
        if not host:
            raise ConfigurationError("host is required, e.g. http://localhost:8000")
        if not sdk_key:
            raise ConfigurationError(
                "sdk_key is required. Create one from the API Keys tab in the dashboard."
            )
        if not project_id:
            raise ConfigurationError(
                "project_id is required because the bootstrap endpoint is project scoped."
            )

        self.host = host.rstrip("/")
        self.sdk_key = sdk_key
        self.project_id = project_id
        self.env = env
        self.timeout = timeout
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=timeout)

    def close(self) -> None:
        """Closes the underlying HTTP client if this transport created it."""
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "BootstrapTransport":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def bootstrap(self, etag: Optional[str] = None) -> FetchResult:
        """
        Requests the snapshot.

        When ``etag`` is supplied it is sent as ``If-None-Match`` so an unchanged
        environment costs a 304 with no body.

        Raises:
            AuthorizationError: the key or project was rejected.
            BootstrapError: any other transport or protocol failure.
        """
        url = f"{self.host}/api/v1/bootstrap"
        params = {"project_id": self.project_id, "env": self.env}
        headers = {"X-SDK-Key": self.sdk_key, "Accept": "application/json"}
        if etag:
            headers["If-None-Match"] = etag

        try:
            response = self._client.get(url, params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise BootstrapError(f"bootstrap request failed: {exc}") from exc

        if response.status_code == 304:
            return FetchResult(not_modified=True, etag=response.headers.get("ETag") or etag)

        if response.status_code in (401, 403):
            raise AuthorizationError(
                f"bootstrap rejected (HTTP {response.status_code}). "
                "Check that the SDK key is active and belongs to this project."
            )

        if response.status_code >= 400:
            raise BootstrapError(
                f"bootstrap failed (HTTP {response.status_code}): {response.text[:200]}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise BootstrapError(f"bootstrap returned a non-JSON body: {exc}") from exc

        import time

        return FetchResult(
            snapshot=Snapshot.from_payload(
                payload,
                etag=response.headers.get("ETag"),
                fetched_at=time.time(),
            ),
            etag=response.headers.get("ETag"),
        )
