"""Transport tests: host resolution and the conditional bootstrap request."""

from __future__ import annotations

import pytest

from catalyst_sdk import DEFAULT_HOST, HOST_ENV_VAR, CatalystClient, ConfigurationError
from catalyst_sdk.transport import BootstrapTransport, resolve_host


@pytest.fixture(autouse=True)
def clear_host_env(monkeypatch):
    """Keeps an ambient CATALYST_HOST on the developer's machine out of the tests."""
    monkeypatch.delenv(HOST_ENV_VAR, raising=False)


# ---------------------------------------------------------------------------
# Host resolution
# ---------------------------------------------------------------------------
def test_defaults_to_the_deployed_api():
    assert resolve_host() == DEFAULT_HOST
    assert DEFAULT_HOST.startswith("https://")


def test_the_client_talks_to_the_deployed_api_by_default(http):
    client = CatalystClient(sdk_key="cp_prod_x", project_id="p1", http_client=http)
    assert client.host == DEFAULT_HOST

    client.is_enabled("ai-assistant", "u1", {})

    assert len(http.requests) == 1
    assert http.requests[0]["url"] == f"{DEFAULT_HOST}/api/v1/bootstrap"
    assert http.requests[0]["params"] == {"project_id": "p1", "env": "prod"}
    assert http.requests[0]["headers"]["X-SDK-Key"] == "cp_prod_x"
    client.close()


def test_an_explicit_host_overrides_the_deployed_api(http):
    client = CatalystClient(
        sdk_key="cp_prod_x",
        project_id="p1",
        host="http://localhost:8000",
        http_client=http,
    )
    assert client.host == "http://localhost:8000"

    client.is_enabled("ai-assistant", "u1", {})

    assert http.requests[0]["url"] == "http://localhost:8000/api/v1/bootstrap"
    client.close()


def test_the_environment_variable_overrides_the_default(http, monkeypatch):
    monkeypatch.setenv(HOST_ENV_VAR, "https://staging.catalyst.example.com/")
    client = CatalystClient(sdk_key="cp_prod_x", project_id="p1", http_client=http)
    assert client.host == "https://staging.catalyst.example.com", "a trailing slash is dropped"

    client.is_enabled("ai-assistant", "u1", {})
    assert http.requests[0]["url"].startswith("https://staging.catalyst.example.com/api/v1/")
    client.close()


def test_an_explicit_host_beats_the_environment_variable(monkeypatch):
    monkeypatch.setenv(HOST_ENV_VAR, "https://from-env.example.com")
    assert resolve_host("http://localhost:8000") == "http://localhost:8000"


def test_an_empty_host_is_a_configuration_error():
    with pytest.raises(ConfigurationError, match="host"):
        resolve_host("")
    with pytest.raises(ConfigurationError, match="host"):
        CatalystClient(sdk_key="cp_prod_x", project_id="p1", host="   ")


def test_a_blank_environment_variable_falls_back_to_the_default(monkeypatch):
    monkeypatch.setenv(HOST_ENV_VAR, "  ")
    assert resolve_host() == DEFAULT_HOST


# ---------------------------------------------------------------------------
# Conditional requests
# ---------------------------------------------------------------------------
def test_the_second_read_is_conditional(http):
    client = CatalystClient(sdk_key="cp_prod_x", project_id="p1", http_client=http)

    client.is_enabled("ai-assistant", "u1", {})
    client.is_enabled("ai-assistant", "u2", {})

    assert "If-None-Match" not in http.requests[0]["headers"], "the first read has nothing cached"
    assert http.requests[1]["headers"]["If-None-Match"] == 'W/"p1:prod:1"'
    assert client.stats["not_modified"] == 1
    client.close()


def test_the_transport_reports_what_it_sent(http):
    transport = BootstrapTransport(
        sdk_key="cp_prod_x", project_id="p1", host="http://catalyst.invalid", client=http
    )
    first = transport.bootstrap()
    assert first.changed is True
    assert first.snapshot is not None
    assert first.etag == 'W/"p1:prod:1"'

    second = transport.bootstrap(etag=first.etag)
    assert second.not_modified is True
    assert second.changed is False
    assert http.requests[1]["headers"]["If-None-Match"] == 'W/"p1:prod:1"'
