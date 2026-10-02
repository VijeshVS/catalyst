"""Client tests: read-per-evaluation, ETag polling, and failing closed."""

from __future__ import annotations

import threading
import time

import httpx
import pytest

from catalyst_sdk import (
    AuthorizationError,
    BootstrapError,
    CatalystClient,
    ConfigurationError,
)
from catalyst_sdk.evaluator import (
    REASON_DEFAULT,
    REASON_ENABLE_ALL,
    REASON_FLAG_NOT_FOUND,
    REASON_KILL_SWITCH,
    REASON_NO_SNAPSHOT,
    REASON_ROLLOUT,
    REASON_ROLLOUT_OUTSIDE,
    REASON_RULE_AND_ROLLOUT,
    REASON_RULE_OUTSIDE_ROLLOUT,
)
from catalyst_sdk.transport import BootstrapTransport

from conftest import default_payload


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------
def test_requires_sdk_key_and_project():
    with pytest.raises(ConfigurationError, match="sdk_key"):
        CatalystClient(sdk_key="", project_id="p1")
    with pytest.raises(ConfigurationError, match="project_id"):
        CatalystClient(sdk_key="cp_prod_x", project_id="")
    with pytest.raises(ConfigurationError, match="host"):
        BootstrapTransport(host="", sdk_key="k", project_id="p")


def test_the_default_environment_is_dev(http):
    """The SDK defaults to dev, matching /bootstrap and /evaluate."""
    client = CatalystClient(sdk_key="cp_prod_x", project_id="p1", http_client=http)
    assert client.env == "dev"

    client.is_enabled("ai-assistant", "u1", {})
    assert http.requests[0]["params"]["env"] == "dev"
    client.close()


def test_client_exposes_snapshot_metadata(make_client):
    client = make_client()
    assert client.is_ready is True
    assert client.env == "prod"
    assert client.version == 7
    assert client.flag_keys() == [
        "ai-assistant",
        "everyone-flag",
        "killed-flag",
        "new-checkout",
        "versioned",
    ]
    stats = client.stats
    assert stats["ready"] is True
    assert stats["read_failed"] is False
    assert stats["flag_count"] == 5
    assert stats["etag"] == 'W/"p1:prod:1"'


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------
def test_rule_one_matches_and_serves_true(make_client):
    client = make_client()
    result = client.evaluate("ai-assistant", "u1", {"email": "dev@acme.com"})
    assert result.value is True
    assert result.reason == REASON_RULE_AND_ROLLOUT
    assert result.rule_id == "rule-internal"
    assert result.flag_version == 7


def test_rule_two_serves_false(make_client):
    client = make_client()
    result = client.evaluate("ai-assistant", "u1", {"plan": "trial"})
    assert result.value is False
    assert result.reason == REASON_RULE_AND_ROLLOUT
    assert result.rule_id == "rule-beta"


def test_no_rule_match_is_filtered_out(make_client):
    """Rules exist and none matched, so this user is not in the population."""
    client = make_client()
    result = client.evaluate("ai-assistant", "u1", {"plan": "pro"})
    assert result.value is False
    assert result.reason == REASON_DEFAULT


def test_a_matched_user_outside_the_rollout_gets_the_opposite_value(make_client):
    client = make_client(percentage=0)
    result = client.evaluate("ai-assistant", "u1", {"email": "dev@acme.com"})
    assert result.value is False
    assert result.reason == REASON_RULE_OUTSIDE_ROLLOUT
    assert result.rule_id == "rule-internal"


def test_kill_switch_wins_over_rules(make_client):
    client = make_client()
    result = client.evaluate("killed-flag", "u1", {"email": "a@acme.com"})
    assert result.value is False
    assert result.reason == REASON_KILL_SWITCH


def test_enable_all_wins_over_rules_and_percentage(make_client):
    # On the killed flag, to show that only the kill switch outranks it.
    client = make_client(enable_all=True)
    result = client.evaluate("ai-assistant", "u1", {"email": "a@acme.com"})
    assert result.value is True
    assert result.reason == REASON_ENABLE_ALL
    assert client.evaluate("killed-flag", "u1", {}).reason == REASON_KILL_SWITCH


def test_rollout_applies_without_a_matching_rule(make_client):
    client = make_client()
    result = client.evaluate("new-checkout", "user_123", {})
    assert result.reason in (REASON_ROLLOUT, REASON_ROLLOUT_OUTSIDE)


def test_rollout_is_sticky_per_user(make_client):
    client = make_client()
    first = client.is_enabled("new-checkout", "user_123", {})
    second = client.is_enabled("new-checkout", "user_123", {})
    assert first == second
    # Sticky but not uniform: different users land in different buckets.
    spread = {client.is_enabled("new-checkout", f"user_{i}", {}) for i in range(300)}
    assert spread == {True, False}


def test_unknown_flag_serves_false(make_client):
    client = make_client()
    result = client.evaluate("does-not-exist", "u1", {})
    assert result.value is False
    assert result.reason == REASON_FLAG_NOT_FOUND
    assert client.is_enabled("does-not-exist") is False


def test_get_all_evaluates_every_flag(make_client):
    client = make_client()
    values = client.get_all("u1", {"email": "dev@acme.com"})
    assert values["ai-assistant"] is True
    assert values["killed-flag"] is False, "the kill switch means false, not the old default"
    assert set(values) == set(client.flag_keys())


def test_evaluation_is_sub_millisecond(make_client):
    client = make_client(refresh_on_evaluate=False)
    result = client.evaluate("ai-assistant", "user_123", {"email": "dev@acme.com"})
    start = time.perf_counter()
    iterations = 2000
    for i in range(iterations):
        client.evaluate("ai-assistant", f"user_{i}", {"email": "dev@acme.com", "plan": "pro"})
    per_call_ms = (time.perf_counter() - start) / iterations * 1000
    assert result.reason == REASON_RULE_AND_ROLLOUT
    assert per_call_ms < 1.0, f"the decision took {per_call_ms:.3f}ms per call"


# ---------------------------------------------------------------------------
# Read-per-evaluation
# ---------------------------------------------------------------------------
def test_construction_does_not_read(make_client, transport):
    """A client is free to build: nothing is fetched until a flag is checked."""
    transport.calls.clear()
    client = make_client()
    assert client.is_ready is True, "the fixture primes the snapshot"
    transport.calls.clear()

    fresh = CatalystClient(
        sdk_key="cp_prod_x",
        project_id="p1",
        host="http://catalyst.invalid",
    )
    assert fresh.is_ready is False
    assert fresh.version == 0
    assert fresh.flag_keys() == []
    fresh.close()


def test_every_evaluation_issues_a_conditional_read(make_client, transport):
    client = make_client()
    transport.calls.clear()

    client.is_enabled("ai-assistant", "u1", {"email": "a@acme.com"})
    client.is_enabled("new-checkout", "u1", {})

    assert transport.calls == ['W/"p1:prod:1"', 'W/"p1:prod:1"']
    assert client.stats["not_modified"] == 2, "an unchanged environment costs a 304"
    assert client.version == 7, "a 304 must not disturb the snapshot"


def test_evaluation_picks_up_a_changed_snapshot(make_client, transport):
    client = make_client()
    assert client.is_enabled("new-checkout", "user_123", {}) is True  # 50% rollout

    payload = default_payload()
    payload["version"] = 9
    payload["flags"]["new-checkout"]["percentage"] = 100
    transport.payload = payload
    transport.etag = 'W/"p1:prod:9"'

    assert client.is_enabled("new-checkout", "user_123", {}) is True
    assert client.version == 9
    assert client.is_ready is True


def test_refresh_on_evaluate_false_stays_in_memory(make_client, transport):
    client = make_client(refresh_on_evaluate=False)
    transport.calls.clear()

    for _ in range(50):
        client.is_enabled("ai-assistant", "u1", {"email": "a@acme.com"})
    assert transport.calls == [], "opt-out mode must be purely local"

    # Freshness is then driven explicitly.
    assert client.refresh() is False
    assert transport.calls == ['W/"p1:prod:1"']


def test_get_all_reads_once_for_every_flag(make_client, transport):
    client = make_client()
    transport.calls.clear()

    values = client.get_all("u1", {"email": "dev@acme.com"})

    assert set(values) == set(client.flag_keys())
    assert len(transport.calls) == 1, "a bulk read must not cost one request per flag"


def test_offline_client_never_reads_on_evaluation():
    client = CatalystClient(
        sdk_key="cp_prod_x",
        project_id="p1",
        host="http://catalyst.invalid",
        offline=True,
    )
    assert client.refresh_on_evaluate is False
    assert client.is_enabled("anything") is False
    client.close()


def test_concurrent_evaluations_collapse_into_one_read(make_client, transport, monkeypatch):
    client = make_client()
    transport.calls.clear()
    # Hold the first read open long enough that every other thread piles up
    # behind the read lock, which is the situation single-flight exists for.
    original = transport.bootstrap

    def slow_bootstrap(etag=None):
        time.sleep(0.05)
        return original(etag)

    monkeypatch.setattr(transport, "bootstrap", slow_bootstrap)
    barrier = threading.Barrier(8, timeout=5)
    results: list = []

    def check() -> None:
        barrier.wait()
        results.append(client.is_enabled("ai-assistant", "u1", {"email": "a@acme.com"}))

    threads = [threading.Thread(target=check) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert len(results) == 8
    assert all(results)
    assert len(transport.calls) == 1, "a stampede must not become eight requests"


# ---------------------------------------------------------------------------
# Read failures
# ---------------------------------------------------------------------------
def test_a_failed_read_is_recorded(make_client, transport):
    client = make_client()
    transport.calls.clear()
    transport.raise_next = BootstrapError("connection reset")

    # Fails closed: no cached fallback serves stale targeting decisions.
    assert client.is_enabled("ai-assistant", "u1", {"email": "dev@acme.com"}) is False
    assert "connection reset" in (client.last_error or "")
    assert client.version == 7, "the snapshot itself is retained for when the API returns"


def test_reads_back_off_after_a_failure(make_client, transport):
    client = make_client(failure_backoff=30.0)
    transport.calls.clear()
    transport.raise_next = BootstrapError("connection reset")

    client.is_enabled("ai-assistant", "u1", {"email": "dev@acme.com"})
    assert transport.calls == ['W/"p1:prod:1"']

    # The window is open, so further checks are served without retrying, which
    # is what stops an unreachable API from adding its timeout to every call.
    for _ in range(5):
        assert client.is_enabled("ai-assistant", "u1", {"email": "dev@acme.com"}) is False
    assert transport.calls == ['W/"p1:prod:1"'], "the backoff window must suppress retries"

    # An explicit refresh is a deliberate act, so it ignores the window.
    client._next_attempt_at = 0.0
    client.refresh()
    assert len(transport.calls) == 2


def test_a_successful_read_ends_the_backoff_window(make_client, transport):
    client = make_client(failure_backoff=30.0)
    transport.calls.clear()
    transport.raise_next = BootstrapError("connection reset")
    client.is_enabled("ai-assistant", "u1", {})

    client._next_attempt_at = 0.0
    assert client.refresh() is False
    client.is_enabled("ai-assistant", "u1", {"email": "dev@acme.com"})
    assert len(transport.calls) == 3, "a healthy API must be polled again"


def test_a_rejected_key_does_not_break_evaluation(make_client, transport):
    """A revoked key must not turn every flag check into an exception."""
    client = make_client()
    transport.calls.clear()
    transport.raise_next = AuthorizationError("HTTP 401")

    # It fails closed rather than raising, and rather than serving a snapshot
    # the API can no longer vouch for.
    assert client.is_enabled("ai-assistant", "u1", {"email": "dev@acme.com"}) is False
    assert client.last_error == "authorization failed"

    # An explicit refresh still raises, because that is where a bad key is fixed.
    client._next_attempt_at = 0.0
    transport.raise_next = AuthorizationError("HTTP 401")
    with pytest.raises(AuthorizationError):
        client.refresh()


def test_raise_on_error_propagates_out_of_evaluation(make_client, transport):
    client = make_client(raise_on_error=True)
    transport.calls.clear()
    transport.raise_next = BootstrapError("api is down")

    with pytest.raises(BootstrapError, match="api is down"):
        client.is_enabled("ai-assistant", "u1", {})


def test_evaluates_to_false_before_any_snapshot():
    client = CatalystClient(
        sdk_key="cp_prod_x",
        project_id="p1",
        host="http://catalyst.invalid",
        offline=True,
    )
    assert client.is_ready is False
    result = client.evaluate("ai-assistant", "u1", {})
    assert result.value is False
    assert result.reason == REASON_NO_SNAPSHOT
    assert client.version == 0
    assert client.flag_keys() == []
    client.close()


# ---------------------------------------------------------------------------
# ETag conditional refresh
# ---------------------------------------------------------------------------
def test_first_load_sends_no_etag(make_client, transport):
    make_client()
    assert transport.calls[0] is None


def test_unchanged_environment_sends_if_none_match_and_gets_304(make_client, transport):
    client = make_client()
    transport.calls.clear()

    changed = client.refresh()
    assert changed is False, "a 304 must not replace the snapshot"
    assert transport.calls == ['W/"p1:prod:1"']
    assert client.version == 7
    assert client.stats["not_modified"] == 1
    assert client.stats["refreshes"] == 1
    assert client.last_error is None


def test_changed_environment_replaces_the_snapshot(make_client, transport):
    client = make_client()
    new_payload = default_payload()
    new_payload["version"] = 9
    new_payload["flags"]["ai-assistant"]["percentage"] = 100
    transport.payload = new_payload
    transport.etag = 'W/"p1:prod:9"'

    assert client.refresh() is True
    assert client.version == 9
    assert client.snapshot.etag == 'W/"p1:prod:9"'
    # "ai-assistant" has rules, so this user must match one to be served.
    assert client.is_enabled("ai-assistant", "user_123", {"email": "dev@acme.com"}) is True


def test_failed_refresh_keeps_serving_the_last_good_snapshot(make_client, transport):
    client = make_client()
    transport.raise_next = BootstrapError("connection reset")
    transport.calls.clear()

    assert client.refresh() is False
    assert client.version == 7, "version must not change on a failed refresh"
    assert client.snapshot is not None, "the last good snapshot is retained"
    assert "connection reset" in (client.last_error or "")
    assert transport.calls == ['W/"p1:prod:1"']

    # Reading through evaluate() after that failure serves false.
    client._next_attempt_at = 0.0
    transport.raise_next = BootstrapError("still down")
    assert client.is_enabled("ai-assistant", "u1", {"email": "dev@acme.com"}) is False


def test_authorization_failure_always_raises(make_client, transport):
    """A bad key will not fix itself, so it must not be swallowed."""
    client = make_client()
    transport.calls.clear()
    transport.raise_next = AuthorizationError("HTTP 401")
    with pytest.raises(AuthorizationError):
        client.refresh()


def test_raise_on_error_propagates_transport_failures(make_client, transport):
    client = make_client(raise_on_error=True)
    transport.raise_next = BootstrapError("boom")
    with pytest.raises(BootstrapError, match="boom"):
        client.refresh()


# ---------------------------------------------------------------------------
# Auto refresh
# ---------------------------------------------------------------------------
def test_auto_refresh_updates_the_snapshot(make_client, transport):
    client = make_client()
    new_payload = default_payload()
    new_payload["version"] = 11
    transport.payload = new_payload
    transport.etag = 'W/"p1:prod:11"'

    client.start_auto_refresh(interval=0.05)
    deadline = time.time() + 3
    while time.time() < deadline and client.version != 11:
        time.sleep(0.02)
    client.stop_auto_refresh()

    assert client.version == 11
    assert transport._thread_alive is False if hasattr(transport, "_thread_alive") else True


def test_auto_refresh_survives_a_transient_failure(make_client, transport):
    client = make_client()
    errors = []
    client.start_auto_refresh(interval=0.05, on_error=errors.append)

    time.sleep(0.07)
    transport.raise_next = BootstrapError("temporary blip")
    time.sleep(0.2)

    client.stop_auto_refresh()
    assert client.is_ready is True
    assert client.version == 7, "a blip must not wipe the snapshot"
    assert errors, "the error callback should have been notified"


def test_stop_auto_refresh_is_idempotent(make_client):
    client = make_client()
    client.start_auto_refresh(interval=0.05)
    client.stop_auto_refresh()
    client.stop_auto_refresh()
    client.close()


def test_refresh_interval_must_be_positive(make_client):
    client = make_client()
    with pytest.raises(ValueError):
        client.start_auto_refresh(interval=0)


# ---------------------------------------------------------------------------
# Failing closed
# ---------------------------------------------------------------------------
class _ExplodingHttp:
    """An HTTP client whose every request fails, standing in for a dead API."""

    def get(self, *args, **kwargs):
        raise httpx.ConnectError("connection refused")

    def close(self):
        pass


def test_a_first_read_failure_serves_false():
    client = CatalystClient(
        sdk_key="cp_prod_x",
        project_id="p1",
        host="http://catalyst.invalid",
        http_client=_ExplodingHttp(),
    )
    assert client.is_enabled("new-checkout", "user_123", {}) is False
    assert client.is_ready is False
    client.close()


def test_a_failed_read_serves_false_even_with_a_snapshot_in_memory(make_client, transport):
    """
    2-E: there is no cached fallback anywhere. Serving a stale targeting
    decision is worse than not serving the feature, so a dead API means false.
    """
    client = make_client(percentage=100)
    assert client.is_enabled("new-checkout", "user_123", {}) is True

    client._next_attempt_at = 0.0
    transport.raise_next = BootstrapError("api is down")
    assert client.is_enabled("new-checkout", "user_123", {}) is False

    # And it recovers as soon as the API answers again.
    client._next_attempt_at = 0.0
    assert client.is_enabled("new-checkout", "user_123", {}) is True


def test_a_304_is_a_successful_read(make_client, transport):
    """Only a genuine failure flips to false; an unchanged environment is fine."""
    client = make_client(percentage=100)
    assert client.is_enabled("new-checkout", "user_123", {}) is True

    transport.calls.clear()
    assert client.refresh() is False, "304 means unchanged"
    assert transport.calls == ['W/"p1:prod:1"']
    assert client.is_enabled("new-checkout", "user_123", {}) is True


def test_no_snapshot_has_ever_been_written_to_disk():
    """
    The disk cache is gone entirely: no constructor argument, no method, no
    environment variable, and nothing under ~/.cache/catalyst.
    """
    import inspect

    signature = inspect.signature(CatalystClient.__init__)
    assert "cache_path" not in signature.parameters
    assert not hasattr(CatalystClient, "clear_cache")
    for name in ("_write_disk_cache", "_load_disk_cache"):
        assert not hasattr(CatalystClient, name), name

    source = inspect.getsource(CatalystClient)
    assert "CATALYST_CACHE_DIR" not in source
    assert ".cache/catalyst" not in source


def test_the_client_takes_no_default_value_argument():
    """2-C removed it along with Flag.default_value."""
    import inspect

    assert "default_value" not in inspect.signature(CatalystClient.__init__).parameters
    assert "default_value" not in inspect.signature(CatalystClient.evaluate).parameters
    assert "default_value" not in inspect.signature(CatalystClient.is_enabled).parameters


def test_client_is_a_context_manager():
    with CatalystClient(
        sdk_key="cp_prod_x",
        project_id="p1",
        host="http://catalyst.invalid",
        offline=True,
    ) as client:
        assert client.is_ready is False
