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

The identity can also be attached once, either on the client or with
:meth:`CatalystClient.for_user`, so it is not repeated at every call site:

    client = CatalystClient(..., user_id="user_123",
                            attributes={"email": "alice@acme.com"})
    client.is_enabled("ai-assistant")

    alice = client.for_user("alice", {"email": "alice@acme.com"})
    alice.is_enabled("ai-assistant")

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

import logging
import threading
import time
from typing import Any, Callable, Dict, List, Mapping, Optional

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
        refresh_on_evaluate: Read the snapshot as part of each evaluation. On
            by default; set it to ``False`` to evaluate from memory only and
            drive freshness with :meth:`refresh` or :meth:`start_auto_refresh`.
        failure_backoff: Seconds to stop retrying after a failed read, so an
            unreachable API does not add its timeout to every single check.
        offline: Never touch the network and never read anything from disk.
            Implies ``refresh_on_evaluate=False``. Useful for tests.
        raise_on_error: If ``True``, read failures propagate out of evaluation
            and :meth:`refresh` re-raises transport errors, instead of
            resolving to ``False``.
        user_id: Sticky rollout key to use when a call omits one. Attach the
            identity here for a client that always acts for the same person, a
            background job, or a script.
        attributes: Context attributes to use when a call omits them. Merged
            with, not replaced by, anything passed per call.

    Use :meth:`for_user` instead when one client serves many users.

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
        refresh_on_evaluate: bool = True,
        failure_backoff: float = 5.0,
        offline: bool = False,
        raise_on_error: bool = False,
        http_client: Optional[Any] = None,
        user_id: str = "",
        attributes: Optional[Attributes] = None,
    ) -> None:
        if not sdk_key or not str(sdk_key).strip():
            raise ConfigurationError("sdk_key is required")
        if not project_id or not str(project_id).strip():
            raise ConfigurationError("project_id is required")

        self.sdk_key = sdk_key
        self.project_id = project_id
        self.host = resolve_host(host)
        self.env = env
        self.raise_on_error = bool(raise_on_error)
        # `offline` is a hard promise that no socket is opened, so it overrides
        # the per-evaluation read rather than competing with it.
        self.refresh_on_evaluate = bool(refresh_on_evaluate) and not offline
        self.failure_backoff = max(0.0, float(failure_backoff))
        # Default identity, used by any call that omits its own. Copied so a
        # later mutation of the caller's dict cannot change how this client
        # evaluates.
        self._user_id = str(user_id or "")
        self._attributes: Dict[str, Any] = dict(attributes or {})

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
        # Set when a read fails and cleared by the next successful one. While it
        # is set the snapshot is not served, so evaluation fails closed.
        self._read_failed = False
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
        """True once a snapshot is loaded and the last read succeeded."""
        return self._snapshot is not None and not self._read_failed

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    @property
    def user_id(self) -> str:
        """The default sticky rollout key, or ``""`` when none is attached."""
        return self._user_id

    @property
    def attributes(self) -> Dict[str, Any]:
        """The default context attributes. A copy, so callers cannot mutate them."""
        return dict(self._attributes)

    def for_user(
        self,
        user_id: str = "",
        attributes: Optional[Attributes] = None,
    ) -> "UserScopedClient":
        """
        Returns a view of this client bound to one user.

        The returned object shares this client's transport and snapshot, so it
        costs no extra round trip and starts no second refresh loop. It is
        meant for a process serving many users::

            sdk = CatalystClient(sdk_key=..., project_id=...)
            alice = sdk.for_user("alice", {"email": "alice@acme.com"})
            if alice.is_enabled("new-checkout"):
                ...

        The client's own defaults are inherited and merged, so a constructor
        ``attributes=`` and a ``for_user`` attribute combine instead of one
        replacing the other. A per-call argument still wins.

        There is no :meth:`for_user` on the returned view: re-binding from a
        scoped view would quietly carry the previous user's attributes over to
        the next one.
        """
        return UserScopedClient(
            self,
            user_id=str(user_id or self._user_id),
            attributes={**self._attributes, **(attributes or {})},
        )

    def _resolve_context(
        self,
        user_id: str,
        attributes: Optional[Attributes],
    ) -> tuple[str, Dict[str, Any]]:
        """
        Folds a call's arguments onto the client's default context.

        A per-call ``user_id`` replaces the default, while ``attributes``
        merge: dropping the client's attributes because one call added an
        email would be a silent targeting change.
        """
        return (
            user_id or self._user_id,
            {**self._attributes, **(attributes or {})},
        )

    @property
    def stats(self) -> Dict[str, Any]:
        """Lightweight counters, handy for health endpoints in a demo app."""
        return {
            "ready": self.is_ready,
            "read_failed": self._read_failed,
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
        evaluation sits inside someone else's request, so it must not turn a
        flag check into a 500. The SDK **fails closed**: a read that fails
        resolves to `False` rather than to a cached snapshot, because serving
        stale targeting decisions is worse than not serving the feature. A
        `304 Not Modified` is a successful read and keeps serving. After a
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

            if failure is not None:
                logger.warning(
                    "snapshot read failed; serving false (next attempt in %.1fs): %s",
                    self.failure_backoff,
                    failure,
                )

    def evaluate(
        self,
        flag_key: str,
        user_id: str = "",
        attributes: Optional[Attributes] = None,
    ) -> EvaluationResult:
        """
        Evaluates one flag and returns the full result including the reason.

        Reads the snapshot first (see :attr:`refresh_on_evaluate`), then decides
        locally. An unknown key, a snapshot that has never loaded, and a failed
        read all resolve to `False`, so neither a bad key nor an unreachable
        API can take a request down or turn a feature on by accident.
        """
        self._read_snapshot()
        return self._evaluate_cached(flag_key, user_id, attributes)

    def _evaluate_cached(
        self,
        flag_key: str,
        user_id: str = "",
        attributes: Optional[Attributes] = None,
    ) -> EvaluationResult:
        """The decision itself: pure, local, and safe to call in a loop."""
        user_id, attributes = self._resolve_context(user_id, attributes)
        snapshot = self._snapshot
        if snapshot is None or self._read_failed:
            return EvaluationResult(
                value=False,
                reason=REASON_NO_SNAPSHOT,
                flag_key=flag_key,
            )

        flag = snapshot.get(flag_key)
        if flag is None:
            return EvaluationResult(
                value=False,
                reason=REASON_FLAG_NOT_FOUND,
                flag_key=flag_key,
            )

        return evaluate_flag(
            flag_key=flag.key,
            enabled=flag.enabled,
            enable_all=flag.enable_all,
            percentage=flag.percentage,
            rules=flag.rules,
            user_id=user_id,
            attributes=attributes,
            flag_version=flag.version,
        )

    def is_enabled(
        self,
        flag_key: str,
        user_id: str = "",
        attributes: Optional[Attributes] = None,
    ) -> bool:
        """
        The hot path: one conditional read, then a local decision.

        Args:
            flag_key: The flag to check.
            user_id: Sticky rollout key. Required for percentage rollouts to
                be meaningful; an empty string is hashed like any other value.
                Falls back to the client's ``user_id``.
            attributes: Context attributes matched against targeting rules.
                Merged onto the client's ``attributes``.
        """
        return self.evaluate(flag_key, user_id, attributes).value

    def get_all(
        self,
        user_id: str = "",
        attributes: Optional[Attributes] = None,
    ) -> Dict[str, bool]:
        """
        Evaluates every flag in the snapshot, e.g. to render a UI once.

        Reads the snapshot a single time, no matter how many flags it holds.
        Both arguments default to the client's own context.
        """
        self._read_snapshot()
        return {
            key: self._evaluate_cached(key, user_id, attributes).value
            for key in self.flag_keys()
        }

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
            # A rejected key will not fix itself, so nothing is served.
            self._read_failed = True
            raise
        except BootstrapError as exc:
            self._last_error = str(exc)
            # Recorded rather than raised so the auto-refresh loop can surface
            # it through `on_error` while the request path stays unaffected.
            self._last_exception = exc
            self._defer_next_attempt()
            # Fail closed: the snapshot may still describe the flag correctly,
            # but the API can no longer confirm it, so it stops being served
            # until a read succeeds.
            self._read_failed = True
            if self.raise_on_error:
                raise
            logger.warning("bootstrap refresh failed; serving false: %s", exc)
            return False

        with self._lock:
            self._refresh_count += 1
            # The API answered, so the backoff window is over.
            self._next_attempt_at = 0.0
            if result.not_modified:
                self._not_modified_count += 1
                self._last_error = None
                self._last_exception = None
                # A 304 is a successful read, so the snapshot serves again.
                self._read_failed = False
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
                self._read_failed = False
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


class UserScopedClient:
    """
    A :class:`CatalystClient` view bound to one user.

    Created by :meth:`CatalystClient.for_user`. It holds no transport, no
    snapshot, and no refresh thread of its own: every attribute and method it
    does not define is answered by the client it was derived from, so scoping a
    client is free and two views of the same client share one snapshot and one
    conditional read.
    """

    __slots__ = ("_attributes", "_client", "_user_id")

    def __init__(
        self,
        client: CatalystClient,
        user_id: str = "",
        attributes: Optional[Attributes] = None,
    ) -> None:
        self._client = client
        self._user_id = str(user_id or "")
        self._attributes: Dict[str, Any] = dict(attributes or {})

    @property
    def client(self) -> CatalystClient:
        """The client this view was derived from."""
        return self._client

    @property
    def user_id(self) -> str:
        return self._user_id

    @property
    def attributes(self) -> Dict[str, Any]:
        """A copy of the bound attributes."""
        return dict(self._attributes)

    # -- Evaluation ----------------------------------------------------
    def evaluate(self, flag_key: str) -> EvaluationResult:
        """Evaluates one flag for the bound user. Same behaviour as the client."""
        return self._client.evaluate(flag_key, self._user_id, self._attributes)

    def is_enabled(self, flag_key: str) -> bool:
        """The hot path, with the identity already attached."""
        return self.evaluate(flag_key).value

    def get_all(self) -> Dict[str, bool]:
        """Every flag in the snapshot, decided for the bound user."""
        return self._client.get_all(self._user_id, self._attributes)

    # -- Everything else is the client's -------------------------------
    @property
    def snapshot(self) -> Optional[Snapshot]:
        return self._client.snapshot

    @property
    def version(self) -> int:
        return self._client.version

    @property
    def is_ready(self) -> bool:
        return self._client.is_ready

    @property
    def last_error(self) -> Optional[str]:
        return self._client.last_error

    @property
    def stats(self) -> Dict[str, Any]:
        return self._client.stats

    def flag_keys(self) -> List[str]:
        return self._client.flag_keys()

    def refresh(self) -> bool:
        return self._client.refresh()

    def start_auto_refresh(
        self,
        interval: float = 30.0,
        on_error: Optional[Callable[[BaseException], None]] = None,
    ) -> threading.Thread:
        return self._client.start_auto_refresh(interval, on_error)

    def stop_auto_refresh(self, timeout: float = 5.0) -> None:
        self._client.stop_auto_refresh(timeout)

    def close(self) -> None:
        """Closes the shared client. A view owns no resources of its own."""
        self._client.close()

    def __enter__(self) -> "UserScopedClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<UserScopedClient user={self._user_id or '(none)'}>"


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
    "UserScopedClient",
]
