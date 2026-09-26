"""Client tests: fetch-on-load, ETag polling, safe defaults, refresh, cache."""

from __future__ import annotations

import json
import os
import time

import pytest

from catalyst_sdk import (
    AuthorizationError,
    BootstrapError,
    CatalystClient,
    ConfigurationError,
    Snapshot,
)
from catalyst_sdk.evaluator import (
    REASON_DEFAULT,
    REASON_FLAG_NOT_FOUND,
    REASON_KILL_SWITCH,
    REASON_NO_SNAPSHOT,
    REASON_ROLLOUT,
    REASON_RULE_MATCH,
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


def test_client_exposes_snapshot_metadata(make_client):
    client = make_client()
    assert client.is_ready is True
    assert client.env == "prod"
    assert client.version == 7
    assert client.flag_keys() == ["ai-assistant", "killed-flag", "new-checkout", "versioned"]
    stats = client.stats
    assert stats["ready"] is True
    assert stats["flag_count"] == 4
    assert stats["etag"] == 'W/"p1:prod:1"'


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------
def test_rule_one_matches_and_serves_true(make_client):
    client = make_client()
    result = client.evaluate("ai-assistant", "u1", {"email": "dev@acme.com"})
    assert result.value is True
    assert result.reason == REASON_RULE_MATCH
    assert result.rule_id == "rule-internal"
    assert result.flag_version == 7


def test_rule_two_serves_false(make_client):
    client = make_client()
    result = client.evaluate("ai-assistant", "u1", {"plan": "trial"})
    assert result.value is False
    assert result.reason == REASON_RULE_MATCH
    assert result.rule_id == "rule-beta"


def test_no_match_falls_through_to_default(make_client):
    client = make_client()
    result = client.evaluate("ai-assistant", "u1", {"plan": "pro"})
    assert result.value is False
    assert result.reason == REASON_DEFAULT


def test_kill_switch_wins_over_rules(make_client):
    client = make_client()
    result = client.evaluate("killed-flag", "u1", {"email": "a@acme.com"})
    assert result.value is True  # flag default
    assert result.reason == REASON_KILL_SWITCH


def test_rollout_applies_without_a_matching_rule(make_client):
    client = make_client()
    result = client.evaluate("new-checkout", "user_123", {})
    assert result.reason == REASON_ROLLOUT


def test_rollout_is_sticky_per_user(make_client):
    client = make_client()
    first = client.is_enabled("new-checkout", "user_123", {})
    second = client.is_enabled("new-checkout", "user_123", {})
    assert first == second
    # Sticky but not uniform: different users land in different buckets.
    spread = {client.is_enabled("new-checkout", f"user_{i}", {}) for i in range(300)}
    assert spread == {True, False}


def test_unknown_flag_falls_back_to_the_safe_default(make_client):
    client = make_client()
    result = client.evaluate("does-not-exist", "u1", {})
    assert result.value is False
    assert result.reason == REASON_FLAG_NOT_FOUND
    assert client.is_enabled("does-not-exist") is False


def test_safe_default_is_configurable(make_client):
    client = make_client(default_value=True)
    assert client.is_enabled("does-not-exist") is True
    # A per-call override wins over the client default.
    assert client.is_enabled("does-not-exist", default_value=False) is False


def test_get_all_evaluates_every_flag(make_client):
    client = make_client()
    values = client.get_all("u1", {"email": "dev@acme.com"})
    assert values["ai-assistant"] is True
    assert values["killed-flag"] is True
    assert set(values) == set(client.flag_keys())


def test_evaluation_never_touches_the_network(make_client, transport):
    client = make_client()
    transport.calls.clear()
    for _ in range(50):
        client.is_enabled("ai-assistant", "u1", {"email": "a@acme.com"})
    assert transport.calls == [], "is_enabled must be purely local"


def test_evaluation_is_sub_millisecond(make_client):
    client = make_client()
    result = client.evaluate("ai-assistant", "user_123", {"email": "dev@acme.com"})
    start = time.perf_counter()
    iterations = 2000
    for i in range(iterations):
        client.evaluate("ai-assistant", f"user_{i}", {"email": "dev@acme.com", "plan": "pro"})
    per_call_ms = (time.perf_counter() - start) / iterations * 1000
    assert result.reason == REASON_RULE_MATCH
    assert per_call_ms < 1.0, f"evaluation took {per_call_ms:.3f}ms per call"


# ---------------------------------------------------------------------------
# No-snapshot behaviour
# ---------------------------------------------------------------------------
def test_evaluates_to_default_before_any_snapshot(tmp_path):
    client = CatalystClient(
        sdk_key="cp_prod_x",
        project_id="p1",
        host="http://catalyst.invalid",
        cache_path=False,
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
    assert client.is_enabled("ai-assistant", "user_123", {}) is True


def test_failed_refresh_keeps_serving_the_last_good_snapshot(make_client, transport):
    client = make_client()
    transport.raise_next = BootstrapError("connection reset")
    transport.calls.clear()

    assert client.refresh() is False
    assert client.version == 7, "version must not change on a failed refresh"
    assert client.is_enabled("ai-assistant", "u1", {"email": "dev@acme.com"}) is True
    assert "connection reset" in (client.last_error or "")
    assert transport.calls == ['W/"p1:prod:1"']


def test_authorization_failure_always_raises(make_client, transport):
    """A bad key will not fix itself, so it must not be swallowed."""
    client = make_client()
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
# Disk cache
# ---------------------------------------------------------------------------
def test_snapshot_is_written_to_the_disk_cache(make_client, tmp_path):
    client = make_client()
    assert os.path.exists(client.cache_path)
    with open(client.cache_path, encoding="utf-8") as handle:
        stored = json.load(handle)
    assert stored["version"] == 7
    assert stored["env"] == "prod"
    assert stored["flags"]["ai-assistant"]["rules"][0]["id"] == "rule-internal"


def test_offline_start_loads_from_the_disk_cache(tmp_path):
    cache = tmp_path / "boot.json"
    payload = default_payload()
    payload["version"] = 42
    Snapshot.from_payload(payload, etag='W/"p1:prod:42"').to_dict()
    with open(cache, "w", encoding="utf-8") as handle:
        json.dump(Snapshot.from_payload(payload, etag='W/"p1:prod:42"').to_dict(), handle)

    client = CatalystClient(
        sdk_key="cp_prod_x",
        project_id="project-1",
        host="http://catalyst.invalid",
        cache_path=str(cache),
        offline=True,
    )
    assert client.is_ready is True
    assert client.version == 42
    assert client.is_enabled("ai-assistant", "u1", {"email": "dev@acme.com"}) is True
    client.close()


def test_corrupt_disk_cache_is_ignored(tmp_path):
    cache = tmp_path / "broken.json"
    cache.write_text("{not json", encoding="utf-8")
    client = CatalystClient(
        sdk_key="cp_prod_x",
        project_id="p1",
        host="http://catalyst.invalid",
        cache_path=str(cache),
        offline=True,
    )
    assert client.is_ready is False
    assert client.is_enabled("anything") is False
    client.close()


def test_cache_for_a_different_environment_is_ignored(tmp_path):
    cache = tmp_path / "prod.json"
    with open(cache, "w", encoding="utf-8") as handle:
        json.dump(Snapshot.from_payload(default_payload(), etag="x").to_dict(), handle)
    client = CatalystClient(
        sdk_key="cp_prod_x",
        project_id="p1",
        host="http://catalyst.invalid",
        env="staging",
        cache_path=str(cache),
        offline=True,
    )
    assert client.is_ready is False
    client.close()


def test_clear_cache_removes_the_file(make_client):
    client = make_client()
    assert os.path.exists(client.cache_path)
    assert client.clear_cache() is True
    assert not os.path.exists(client.cache_path)
    assert client.clear_cache() is False


def test_cache_path_true_uses_the_default_location(monkeypatch, tmp_path):
    """`cache_path=True` means "use the default", not the literal string "True"."""
    monkeypatch.setenv("CATALYST_CACHE_DIR", str(tmp_path / "default-cache"))
    client = CatalystClient(
        sdk_key="cp_prod_x",
        project_id="project-1",
        host="http://catalyst.invalid",
        cache_path=True,
        offline=True,
    )
    assert client.cache_path is not None
    assert client.cache_path != "True"
    assert client.cache_path.endswith(".json")
    assert "project-1_prod" in client.cache_path
    client.close()


def test_disk_cache_can_be_disabled(tmp_path):
    client = CatalystClient(
        sdk_key="cp_prod_x",
        project_id="p1",
        host="http://catalyst.invalid",
        cache_path=False,
        offline=True,
    )
    assert client.cache_path is None
    client.close()


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------
def test_client_is_a_context_manager():
    with CatalystClient(
        sdk_key="cp_prod_x",
        project_id="p1",
        host="http://catalyst.invalid",
        cache_path=False,
        offline=True,
    ) as client:
        assert client.is_ready is False
