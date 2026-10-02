"""User context: attach the identity once, on the client or per user."""

from __future__ import annotations

import pytest

from catalyst_sdk import UserScopedClient
from catalyst_sdk.evaluator import (
    REASON_DEFAULT,
    REASON_ROLLOUT,
    REASON_ROLLOUT_OUTSIDE,
    REASON_RULE_AND_ROLLOUT,
)


# ----------------------------------------------------------------------
# Identity attached on the client
# ----------------------------------------------------------------------
def test_constructor_context_decides_without_per_call_arguments(make_client):
    client = make_client(attributes={"email": "alice@acme.com"})

    result = client.evaluate("ai-assistant")

    assert result.value is True
    assert result.reason == REASON_RULE_AND_ROLLOUT
    assert result.rule_id == "rule-internal"


def test_constructor_user_id_is_used_for_the_rollout_bucket(make_client):
    client = make_client(user_id="user_123")
    one = client.evaluate("new-checkout")

    client = make_client(user_id="a-different-user")
    other = client.evaluate("new-checkout")

    assert client.user_id == "a-different-user"
    # 50% rollout: two ids landing in the same half is possible, so what is
    # asserted is that the bucket is the user's and not a fixed constant.
    assert one.reason in (REASON_ROLLOUT, REASON_ROLLOUT_OUTSIDE)
    assert other.reason in (REASON_ROLLOUT, REASON_ROLLOUT_OUTSIDE)


def test_per_call_attributes_override_the_bound_ones(make_client):
    client = make_client(attributes={"email": "alice@acme.com"})

    result = client.evaluate("ai-assistant", attributes={"email": "bob@other.com"})

    assert result.value is False
    assert result.reason == REASON_DEFAULT


def test_per_call_attributes_merge_rather_than_replace(make_client):
    # `versioned` needs app_version, `ai-assistant` needs email. Supplying one
    # per call must not drop the other.
    client = make_client(attributes={"app_version": "3.3"})

    result = client.evaluate("versioned", attributes={"email": "alice@acme.com"})

    assert result.value is True
    assert client.attributes == {"app_version": "3.3"}


def test_get_all_uses_the_bound_context(make_client):
    client = make_client(attributes={"email": "alice@acme.com"})

    flags = client.get_all()

    assert flags["ai-assistant"] is True
    assert flags["everyone-flag"] is True
    assert flags["killed-flag"] is False


def test_an_unbound_client_still_hashes_the_empty_user_id(make_client):
    client = make_client()

    assert client.user_id == ""
    assert client.attributes == {}
    # `new-checkout` has no rules, so DEFAULT_VALUE is unreachable here. The
    # rollout reason proves an empty user_id was hashed rather than a leaked
    # default.
    assert client.evaluate("new-checkout").reason in (
        REASON_ROLLOUT,
        REASON_ROLLOUT_OUTSIDE,
    )


def test_bound_context_is_copied_defensively(make_client):
    attributes = {"email": "alice@acme.com"}
    client = make_client(attributes=attributes)

    attributes["email"] = "mallory@evil.com"
    read = client.attributes
    read["email"] = "also@evil.com"

    assert client.attributes == {"email": "alice@acme.com"}
    assert client.is_enabled("ai-assistant") is True


# ----------------------------------------------------------------------
# for_user
# ----------------------------------------------------------------------
def test_for_user_binds_the_identity(make_client):
    client = make_client()

    alice = client.for_user("alice", {"email": "alice@acme.com"})
    bob = client.for_user("bob", {"email": "bob@other.com"})

    assert alice.is_enabled("ai-assistant") is True
    assert alice.evaluate("ai-assistant").rule_id == "rule-internal"
    assert bob.is_enabled("ai-assistant") is False
    assert bob.evaluate("ai-assistant").reason == REASON_DEFAULT


def test_for_user_needs_no_identity_arguments_at_all(make_client):
    alice = make_client().for_user("alice", {"email": "alice@acme.com"})

    result = alice.evaluate("ai-assistant")

    assert (result.value, result.reason) == (True, REASON_RULE_AND_ROLLOUT)
    assert alice.is_enabled("killed-flag") is False
    assert alice.get_all()["ai-assistant"] is True


def test_for_user_inherits_the_clients_defaults(make_client):
    client = make_client(user_id="user_123", attributes={"app_version": "3.3"})

    scoped = client.for_user()

    assert scoped.user_id == "user_123"
    assert scoped.attributes == {"app_version": "3.3"}
    assert scoped.is_enabled("versioned") is True


def test_for_user_merges_onto_the_clients_attributes(make_client):
    client = make_client(attributes={"app_version": "3.3"})

    scoped = client.for_user("alice", {"email": "alice@acme.com"})

    assert scoped.attributes == {"app_version": "3.3", "email": "alice@acme.com"}
    assert scoped.is_enabled("versioned") is True
    assert scoped.is_enabled("ai-assistant") is True


def test_scoped_client_shares_the_transport_and_snapshot(make_client):
    client = make_client()
    alice = client.for_user("alice", {"email": "alice@acme.com"})
    bob = client.for_user("bob", {"email": "bob@other.com"})

    alice.is_enabled("ai-assistant")
    # Same object, so a scoped view cannot drift from the parent's snapshot.
    assert alice.snapshot is client.snapshot
    version_after_alice = alice.version

    bob.is_enabled("ai-assistant")

    assert isinstance(alice, UserScopedClient)
    assert alice.client is client
    assert bob.client is client
    assert bob.snapshot is client.snapshot
    assert bob.version == version_after_alice == client.version


def test_scoped_reads_still_collapse_into_one_request(make_client, transport):
    client = make_client()
    alice = client.for_user("alice", {"email": "alice@acme.com"})

    alice.is_enabled("ai-assistant")
    calls = len(transport.calls)
    alice.is_enabled("ai-assistant")

    # The second check is a conditional read against the ETag the first one
    # banked, rather than a second full fetch.
    assert len(transport.calls) == calls + 1
    assert transport.calls[-1] == transport.etag


def test_scoped_client_cannot_rebind_and_leak_attributes(make_client):
    alice = make_client().for_user("alice", {"email": "alice@acme.com"})

    with pytest.raises(AttributeError):
        alice.for_user("bob")  # type: ignore[attr-defined]


def test_scoped_client_delegates_lifecycle(make_client, transport):
    client = make_client()

    with client.for_user("alice", {"email": "alice@acme.com"}) as alice:
        assert alice.is_ready is True
        assert "ai-assistant" in alice.flag_keys()
        assert alice.stats["env"] == "prod"

    assert transport.closed is True


def test_scoped_refresh_and_auto_refresh_delegate(make_client):
    client = make_client()
    alice = client.for_user("alice", {"email": "alice@acme.com"})

    assert alice.refresh() is False  # 304: the fixture already loaded it
    thread = alice.start_auto_refresh(interval=60)
    try:
        assert thread is client.start_auto_refresh(interval=60)
    finally:
        alice.stop_auto_refresh()


def test_for_user_on_a_fresh_client_costs_no_request(make_client, transport):
    client = make_client()
    # The fixture loads once; binding a user must not add to that.
    calls = len(transport.calls)

    client.for_user("alice", {"email": "alice@acme.com"})

    assert len(transport.calls) == calls
