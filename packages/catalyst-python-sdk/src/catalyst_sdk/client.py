"""
The Catalyst evaluation client.

Fetch-on-load, in-memory, zero-latency evaluation:

    from catalyst_sdk import CatalystClient

    client = CatalystClient(
        sdk_key="cp_prod_a1b2c3d4e5f6g7h8i9j0k1",
        project_id="7c9e6679-7425-40de-944b-e07fc1f90ae7",
        host="http://localhost:8000",
        env="prod",
    )
    client.start_auto_refresh(interval=30)

    if client.is_enabled("ai-assistant", user_id="user_123",
                         attributes={"email": "alice@acme.com"}):
        ...

``is_enabled`` never touches the network. Refreshes happen on ``refresh()`` or
on a background thread, and a failed refresh keeps serving the last good
snapshot rather than raising into the request path.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Union

from .evaluator import (
    REASON_FLAG_NOT_FOUND,
    REASON_NO_SNAPSHOT,
    EvaluationResult,
    evaluate_flag,
)
from .snapshot import FlagSnapshot, Snapshot
from .transport import (
    AuthorizationError,
    BootstrapError,
    BootstrapTransport,
    ConfigurationError,
)

logger = logging.getLogger("catalyst_sdk")

Attributes = Mapping[str, Any]


def _default_cache_path(sdk_key: str, project_id: str, env: str) -> str:
    """A stable per-project cache filename keyed by a hash of the SDK key."""
    import hashlib

    digest = hashlib.sha256(sdk_key.encode("utf-8")).hexdigest()[:16]
    base = os.environ.get("CATALYST_CACHE_DIR") or os.path.join(
        os.path.expanduser("~"), ".cache", "catalyst"
    )
    return os.path.join(base, f"{project_id}_{env}_{digest}.json")


class CatalystClient:
    """
    In-memory feature flag client.

    Args:
        sdk_key: An SDK key (``cp_<env>_<random>``) from the dashboard's API
            Keys tab. Passed as ``X-SDK-Key``.
        project_id: The project the snapshot belongs to. Required because the
            bootstrap endpoint is strictly project scoped.
        host: Base URL of the Catalyst API, e.g. ``http://localhost:8000``.
        env: Environment whose snapshot to load. Defaults to ``prod``.
        timeout: Per-request HTTP timeout in seconds.
        default_value: Value returned for an unknown flag key or when no
            snapshot has loaded yet. Fails safe to ``False``.
        offline: Start without contacting the API, loading only from the disk
            cache. Useful for tests and cold starts.
        cache_path: Where to persist the last good snapshot. ``None`` or ``True``
            uses a default location under ``~/.cache/catalyst`` (override with
            ``CATALYST_CACHE_DIR``), and ``False`` disables disk caching.
        raise_on_error: If ``True``, :meth:`refresh` re-raises transport errors
            instead of logging and keeping the current snapshot.

    Raises:
        ConfigurationError: on missing or unusable settings.
    """

    def __init__(
        self,
        sdk_key: str,
        project_id: str,
        host: str = "http://localhost:8000",
        env: str = "prod",
        timeout: float = 5.0,
        default_value: bool = False,
        offline: bool = False,
        cache_path: Optional[Union[str, bool]] = None,
        raise_on_error: bool = False,
        http_client: Optional[Any] = None,
    ) -> None:
        if not sdk_key or not str(sdk_key).strip():
            raise ConfigurationError("sdk_key is required")
        if not project_id or not str(project_id).strip():
            raise ConfigurationError("project_id is required")

        self.sdk_key = sdk_key
        self.project_id = project_id
        self.host = host
        self.env = env
        self.default_value = bool(default_value)
        self.raise_on_error = bool(raise_on_error)

        if cache_path is False:
            self.cache_path: Optional[str] = None
        elif cache_path is None or cache_path is True:
            self.cache_path = _default_cache_path(sdk_key, project_id, env)
        else:
            self.cache_path = str(cache_path)

        self._transport = BootstrapTransport(
            host=host,
            sdk_key=sdk_key,
            project_id=project_id,
            env=env,
            timeout=timeout,
            client=http_client,
        )

        # A single attribute assignment makes the snapshot swap atomic for
        # readers, so evaluation never sees a half-updated view.
        self._snapshot: Optional[Snapshot] = None
        self._lock = threading.RLock()
        self._refresh_thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

        self._last_error: Optional[str] = None
        self._last_exception: Optional[BaseException] = None
        self._last_refresh_ok: Optional[float] = None
        self._refresh_count = 0
        self._not_modified_count = 0

        if offline:
            self._load_disk_cache()
        else:
            try:
                self.refresh()
            except (BootstrapError, AuthorizationError):
                # Cold start with no network: fall back to the cache, then to
                # safe defaults. Never raise from the constructor.
                logger.warning("initial bootstrap failed; trying disk cache", exc_info=True)
                if not self._load_disk_cache():
                    logger.warning(
                        "no usable snapshot; falling back to default_value=%s",
                        self.default_value,
                    )

    # ------------------------------------------------------------------
    # Snapshot access
    # ------------------------------------------------------------------
    @property
    def snapshot(self) -> Optional[Snapshot]:
        """The currently loaded snapshot, or ``None`` before the first load."""
        return self._snapshot

    @property
    def version(self) -> int:
        """Environment cache version of the loaded snapshot."""
        return self._snapshot.version if self._snapshot else 0

    @property
    def is_ready(self) -> bool:
        """True once a snapshot is loaded, whether from the API or disk."""
        return self._snapshot is not None

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    @property
    def stats(self) -> Dict[str, Any]:
        """Lightweight counters, handy for health endpoints in a demo app."""
        return {
            "ready": self.is_ready,
            "env": self.env,
            "version": self.version,
            "flag_count": len(self._snapshot) if self._snapshot else 0,
            "etag": self._snapshot.etag if self._snapshot else None,
            "last_refresh_ok": self._last_refresh_ok,
            "last_error": self._last_error,
            "refreshes": self._refresh_count,
            "not_modified": self._not_modified_count,
        }

    def flag_keys(self) -> List[str]:
        """All flag keys present in the snapshot."""
        return sorted(self._snapshot.flags) if self._snapshot else []

    # ------------------------------------------------------------------
    # Evaluation (no network access)
    # ------------------------------------------------------------------
    def evaluate(
        self,
        flag_key: str,
        user_id: str = "",
        attributes: Optional[Attributes] = None,
        default_value: Optional[bool] = None,
    ) -> EvaluationResult:
        """
        Evaluates one flag and returns the full result including the reason.

        Unknown keys and the no-snapshot case resolve to the configured safe
        default rather than raising, so a bad key can never take a request down.
        """
        snapshot = self._snapshot
        if snapshot is None:
            return EvaluationResult(
                value=self._fallback(default_value),
                reason=REASON_NO_SNAPSHOT,
                flag_key=flag_key,
            )

        flag = snapshot.get(flag_key)
        if flag is None:
            return EvaluationResult(
                value=self._fallback(default_value),
                reason=REASON_FLAG_NOT_FOUND,
                flag_key=flag_key,
            )

        return evaluate_flag(
            flag_key=flag.key,
            default_value=flag.default_value,
            enabled=flag.enabled,
            percentage=flag.percentage,
            rules=flag.rules,
            user_id=user_id or "",
            attributes=attributes or {},
            flag_version=flag.version,
        )

    def is_enabled(
        self,
        flag_key: str,
        user_id: str = "",
        attributes: Optional[Attributes] = None,
        default_value: Optional[bool] = None,
    ) -> bool:
        """
        Zero-latency boolean check. Never performs I/O.

        Args:
            flag_key: The flag to check.
            user_id: Sticky rollout key. Required for percentage rollouts to
                be meaningful; an empty string is hashed like any other value.
            attributes: Context attributes matched against targeting rules.
            default_value: Overrides the client default for this call only.
        """
        return self.evaluate(flag_key, user_id, attributes, default_value).value

    def get_all(
        self,
        user_id: str = "",
        attributes: Optional[Attributes] = None,
    ) -> Dict[str, bool]:
        """Evaluates every flag in the snapshot, e.g. to render a UI once."""
        return {
            key: self.is_enabled(key, user_id, attributes)
            for key in self.flag_keys()
        }

    def _fallback(self, override: Optional[bool]) -> bool:
        return self.default_value if override is None else bool(override)

    # ------------------------------------------------------------------
    # Refreshing
    # ------------------------------------------------------------------
    def refresh(self) -> bool:
        """
        Conditionally re-fetches the snapshot.

        Sends ``If-None-Match`` with the cached ETag, so an unchanged
        environment returns 304 and costs no body transfer.

        Returns:
            ``True`` if a new snapshot was applied, ``False`` if unchanged.

        Raises:
            AuthorizationError: if the key is rejected. Always raised, because
                a bad key will not fix itself and silent degradation would hide
                a configuration error.
            BootstrapError: on other failures when ``raise_on_error`` is set,
                otherwise the error is logged and the previous snapshot is kept.
        """
        current_etag = self._snapshot.etag if self._snapshot else None
        try:
            result = self._transport.bootstrap(etag=current_etag)
        except AuthorizationError:
            self._last_error = "authorization failed"
            self._last_exception = None
            raise
        except BootstrapError as exc:
            self._last_error = str(exc)
            # Recorded rather than raised so the auto-refresh loop can surface
            # it through `on_error` while the request path stays unaffected.
            self._last_exception = exc
            if self.raise_on_error:
                raise
            logger.warning("bootstrap refresh failed; keeping snapshot v%s", self.version)
            return False

        with self._lock:
            self._refresh_count += 1
            if result.not_modified:
                self._not_modified_count += 1
                self._last_error = None
                self._last_exception = None
                # Keep serving the existing snapshot; only note the check time.
                if self._snapshot is not None and result.etag:
                    self._snapshot = Snapshot(
                        env=self._snapshot.env,
                        version=self._snapshot.version,
                        flags=self._snapshot.flags,
                        etag=result.etag,
                        fetched_at=time.time(),
                    )
                self._last_refresh_ok = time.time()
                return False

            if result.snapshot is not None:
                self._snapshot = result.snapshot
                self._last_refresh_ok = time.time()
                self._last_error = None
                self._last_exception = None
                self._write_disk_cache(result.snapshot)
                return True

        return False

    def start_auto_refresh(
        self,
        interval: float = 30.0,
        on_error: Optional[Callable[[BaseException], None]] = None,
    ) -> threading.Thread:
        """
        Starts a daemon thread that calls :meth:`refresh` every ``interval``.

        Failures are logged and the last good snapshot keeps serving, so a
        momentary network blip never changes what your users get.
        """
        if interval <= 0:
            raise ValueError("interval must be greater than 0")
        if self._refresh_thread is not None and self._refresh_thread.is_alive():
            return self._refresh_thread

        self._stop.clear()

        def _loop() -> None:
            while not self._stop.wait(interval):
                try:
                    self.refresh()
                except Exception as exc:  # noqa: BLE001 - thread must not die
                    logger.warning("auto-refresh failed: %s", exc)
                    pending: Optional[BaseException] = exc
                else:
                    # A swallowed transport failure still needs reporting, so
                    # pick up whatever `refresh()` recorded.
                    with self._lock:
                        pending = self._last_exception
                        self._last_exception = None

                if pending is not None and on_error is not None:
                    try:
                        on_error(pending)
                    except Exception:  # noqa: BLE001
                        logger.exception("refresh error callback raised")

        thread = threading.Thread(
            target=_loop, name="catalyst-auto-refresh", daemon=True
        )
        thread.start()
        self._refresh_thread = thread
        return thread

    def stop_auto_refresh(self, timeout: float = 5.0) -> None:
        """Signals the refresh thread to exit and waits briefly for it."""
        self._stop.set()
        thread = self._refresh_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
        self._refresh_thread = None

    # ------------------------------------------------------------------
    # Disk cache
    # ------------------------------------------------------------------
    def _write_disk_cache(self, snapshot: Snapshot) -> None:
        if not self.cache_path:
            return
        try:
            os.makedirs(os.path.dirname(self.cache_path) or ".", exist_ok=True)
            # Write to a temp file then rename so a crash cannot leave a
            # truncated snapshot that would fail to parse on next boot.
            tmp = f"{self.cache_path}.tmp"
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(snapshot.to_dict(), handle)
            os.replace(tmp, self.cache_path)
        except OSError as exc:
            logger.warning("could not write snapshot cache %s: %s", self.cache_path, exc)

    def _load_disk_cache(self) -> bool:
        if not self.cache_path or not os.path.exists(self.cache_path):
            return False
        try:
            with open(self.cache_path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
            snapshot = Snapshot.from_dict(raw)
        except (OSError, ValueError) as exc:
            logger.warning("ignoring unreadable snapshot cache: %s", exc)
            return False

        if snapshot.env and snapshot.env != self.env:
            return False

        with self._lock:
            self._snapshot = snapshot
        logger.info("loaded snapshot v%s for %s from cache", snapshot.version, self.env)
        return True

    def clear_cache(self) -> bool:
        """Deletes the on-disk snapshot. Returns True if a file was removed."""
        if not self.cache_path or not os.path.exists(self.cache_path):
            return False
        try:
            os.remove(self.cache_path)
            return True
        except OSError:
            return False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def close(self) -> None:
        """Stops auto-refresh and releases the HTTP connection pool."""
        self.stop_auto_refresh()
        self._transport.close()

    def __enter__(self) -> "CatalystClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        state = f"v{self.version}/{len(self._snapshot)} flags" if self._snapshot else "not ready"
        return f"<CatalystClient {self.project_id[:8]}… {self.env} {state}>"


__all__ = [
    "AuthorizationError",
    "BootstrapError",
    "CatalystClient",
    "ConfigurationError",
    "EvaluationResult",
    "FlagSnapshot",
    "Snapshot",
]
