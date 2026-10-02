"""
The Catalyst evaluation client.

Reads the environment snapshot when it evaluates, not at import time:

    from catalyst_sdk import CatalystClient

    client = CatalystClient(
        sdk_key="cp_prod_a1b2c3d4e5f6g7h8i9j0k1",
        project_id="7c9e6679-7425-40de-944b-e07fc1f90ae7",
        env="prod",
    )

    if client.is_enabled("ai-assistant", user_id="user_123",
                         attributes={"email": "alice@acme.com"}):
        ...

The client talks to the hosted API by default; pass ``host=`` (or set
``CATALYST_HOST``) to point it somewhere else.

Every evaluation issues a conditional read: the current ETag goes out as
``If-None-Match`` and an unchanged environment answers ``304`` with no body, so
a check costs one small round trip and never a full snapshot transfer. The
decision itself is then made locally against the returned snapshot, which is
swapped in atomically.

A failed read keeps serving the last good snapshot rather than raising into the
request path, so a momentary network blip never changes what your users get. Pass
``refresh_on_evaluate=False`` to evaluate purely from memory and drive freshness
yourself with :meth:`refresh` or :meth:`start_auto_refresh`.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Callable, Dict, List, Mapping, Optional, Union

from .evaluator import (
    REASON_FLAG_NOT_FOUND,
    REASON_NO_SNAPSHOT,
    EvaluationResult,
    evaluate_flag,
)
from .snapshot import FlagSnapshot, Snapshot
from .transport import (
    DEFAULT_HOST,
    HOST_ENV_VAR,
    AuthorizationError,
    BootstrapError,
    BootstrapTransport,
    ConfigurationError,
    resolve_host,
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
    Feature flag client that reads its snapshot as it evaluates.

    Args:
        sdk_key: An SDK key (``cp_<env>_<random>``) from the dashboard's API
            Keys tab. Passed as ``X-SDK-Key``.
        project_id: The project the snapshot belongs to. Required because the
            bootstrap endpoint is strictly project scoped.
        host: Base URL of the Catalyst API. Omit it to use the hosted API
            (:data:`~catalyst_sdk.transport.DEFAULT_HOST`); set ``CATALYST_HOST``
            to change the default for a whole process.
        env: Environment whose snapshot to load. Defaults to ``dev``, matching
            ``/api/v1/bootstrap`` and ``/api/v1/evaluate``.
        timeout: Per-request HTTP timeout in seconds.
        default_value: Value returned for an unknown flag key or when no
            snapshot has loaded yet. Fails safe to ``False``.
        refresh_on_evaluate: Read the snapshot as part of each evaluation. On
            by default; set it to ``False`` to evaluate from memory only and
            drive freshness with :meth:`refresh` or :meth:`start_auto_refresh`.
        failure_backoff: Seconds to stop retrying after a failed read, so an
            unreachable API does not add its timeout to every single check.
        offline: Never touch the network; load only from the disk cache. Implies
            ``refresh_on_evaluate=False``. Useful for tests and cold starts.
        cache_path: Where to persist the last good snapshot. ``None`` or ``True``
            uses a default location under ``~/.cache/catalyst`` (override with
            ``CATALYST_CACHE_DIR``), and ``False`` disables disk caching.
        raise_on_error: If ``True``, read failures propagate out of evaluation
            and :meth:`refresh` re-raises transport errors, instead of degrading
            to the last good snapshot.

    Raises:
        ConfigurationError: on missing or unusable settings.
    """

    def __init__(
        self,
        sdk_key: str,
        project_id: str,
        host: Optional[str] = None,
        env: str = "dev",
        timeout: float = 5.0,
        default_value: bool = False,
        refresh_on_evaluate: bool = True,
        failure_backoff: float = 5.0,
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
        self.host = resolve_host(host)
        self.env = env
        self.default_value = bool(default_value)
        self.raise_on_error = bool(raise_on_error)
        # `offline` is a hard promise that no socket is opened, so it overrides
        # the per-evaluation read rather than competing with it.
        self.refresh_on_evaluate = bool(refresh_on_evaluate) and not offline
        self.failure_backoff = max(0.0, float(failure_backoff))

        if cache_path is False:
            self.cache_path: Optional[str] = None
        elif cache_path is None or cache_path is True:
            self.cache_path = _default_cache_path(sdk_key, project_id, env)
        else:
            self.cache_path = str(cache_path)

        self._transport = BootstrapTransport(
            host=self.host,
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
        # Held only for the duration of a read, so concurrent evaluations
        # collapse into one request instead of stampeding the API.
        self._read_lock = threading.Lock()
        self._refresh_thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

        self._last_error: Optional[str] = None
        self._last_exception: Optional[BaseException] = None
        self._last_refresh_ok: Optional[float] = None
        self._refresh_count = 0
        self._not_modified_count = 0
        self._next_attempt_at = 0.0

        if offline:
            if not self._load_disk_cache():
                logger.warning(
                    "offline start found no cached snapshot; falling back to default_value=%s",
                    self.default_value,
                )
        # Nothing is fetched here on purpose. A snapshot is read when it is
        # needed, so constructing a client is free and cannot fail on a cold or
        # unreachable API.

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
        """True once a snapshot is loaded, whether from a read or the disk cache."""
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
            "host": self.host,
            "version": self.version,
            "flag_count": len(self._snapshot) if self._snapshot else 0,
            "etag": self._snapshot.etag if self._snapshot else None,
            "last_refresh_ok": self._last_refresh_ok,
            "last_error": self._last_error,
            "refreshes": self._refresh_count,
            "not_modified": self._not_modified_count,
        }

    def flag_keys(self) -> List[str]:
        """
        All flag keys in the snapshot currently held.

        Reads from memory, so call it after an evaluation (or :meth:`refresh`) if
        the client has not evaluated yet.
        """
        return sorted(self._snapshot.flags) if self._snapshot else []

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------
    def _read_snapshot(self) -> None:
        """
        Refreshes the snapshot, coalescing concurrent readers into one request.

        Runs before every evaluation. Failure is absorbed here on purpose: an
        evaluation sits inside someone else's request, so it degrades to the last
        good snapshot rather than turning a flag check into a 500. After a
        failure the next read is held off for `failure_backoff` seconds, so a
        dead API costs one timeout per window instead of one per check.
        """
        if not self.refresh_on_evaluate:
            return

        # Read before locking: if another thread already refreshed while this one
        # waited for the lock, there is nothing left to ask for.
        observed = self._refresh_count
        if time.monotonic() < self._next_attempt_at:
            return

        with self._read_lock:
            if self._refresh_count != observed:
                return
            if time.monotonic() < self._next_attempt_at:
                return
            try:
                self.refresh()
            except (AuthorizationError, BootstrapError) as exc:
                if self.raise_on_error:
                    raise
                failure: Optional[BaseException] = exc
            else:
                failure = None

            if self._snapshot is None:
                # Cold start with nothing to serve: the last known good snapshot
                # on disk is the last resort before the configured default.
                self._load_disk_cache()

            if failure is not None:
                logger.warning(
                    "snapshot read failed; serving v%s (next attempt in %.1fs): %s",
                    self.version,
                    self.failure_backoff,
                    failure,
                )

    def evaluate(
        self,
        flag_key: str,
        user_id: str = "",
        attributes: Optional[Attributes] = None,
        default_value: Optional[bool] = None,
    ) -> EvaluationResult:
        """
        Evaluates one flag and returns the full result including the reason.

        Reads the snapshot first (see :attr:`refresh_on_evaluate`), then decides
        locally. Unknown keys and the no-snapshot case resolve to the configured
        safe default rather than raising, so a bad key can never take a request
        down.
        """
        self._read_snapshot()
        return self._evaluate_cached(flag_key, user_id, attributes, default_value)

    def _evaluate_cached(
        self,
        flag_key: str,
        user_id: str = "",
        attributes: Optional[Attributes] = None,
        default_value: Optional[bool] = None,
    ) -> EvaluationResult:
        """The decision itself: pure, local, and safe to call in a loop."""
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
        The hot path: one conditional read, then a local decision.

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
        """
        Evaluates every flag in the snapshot, e.g. to render a UI once.

        Reads the snapshot a single time, no matter how many flags it holds.
        """
        self._read_snapshot()
        return {
            key: self._evaluate_cached(key, user_id, attributes).value
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

        A failure starts a `failure_backoff` window, during which a read triggered
        by :meth:`evaluate` is skipped rather than retried.

        Returns:
            ``True`` if a new snapshot was applied, ``False`` if unchanged or if
            the read failed and the previous snapshot is being kept.

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
            self._defer_next_attempt()
            raise
        except BootstrapError as exc:
            self._last_error = str(exc)
            # Recorded rather than raised so the auto-refresh loop can surface
            # it through `on_error` while the request path stays unaffected.
            self._last_exception = exc
            self._defer_next_attempt()
            if self.raise_on_error:
                raise
            logger.warning("bootstrap refresh failed; keeping snapshot v%s", self.version)
            return False

        with self._lock:
            self._refresh_count += 1
            # The API answered, so the backoff window is over.
            self._next_attempt_at = 0.0
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

    def _defer_next_attempt(self) -> None:
        """Holds off automatic reads for `failure_backoff` seconds."""
        if self.failure_backoff > 0:
            self._next_attempt_at = time.monotonic() + self.failure_backoff

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
    "DEFAULT_HOST",
    "HOST_ENV_VAR",
    "AuthorizationError",
    "BootstrapError",
    "CatalystClient",
    "ConfigurationError",
    "EvaluationResult",
    "FlagSnapshot",
    "Snapshot",
]
