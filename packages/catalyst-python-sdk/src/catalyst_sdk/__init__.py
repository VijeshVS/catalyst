"""
Catalyst Python SDK.

A feature flag client that reads your environment snapshot as it evaluates.
The hosted API is used by default; pass `host=` to point somewhere else.

    from catalyst_sdk import CatalystClient

    client = CatalystClient(
        sdk_key="cp_prod_a1b2c3d4e5f6g7h8i9j0k1",
        project_id="7c9e6679-7425-40de-944b-e07fc1f90ae7",
        env="prod",
    )

    client.is_enabled("ai-assistant", user_id="user_123",
                      attributes={"email": "alice@acme.com"})

Each check sends a conditional request, so an unchanged environment costs a 304
with no body, and the decision itself is made locally. Pass
`refresh_on_evaluate=False` to evaluate purely from memory instead.
"""

from .client import CatalystClient
from .evaluator import (
    PRESENCE_OPERATORS,
    REASON_DEFAULT,
    REASON_FLAG_NOT_FOUND,
    REASON_KILL_SWITCH,
    REASON_NO_SNAPSHOT,
    REASON_ROLLOUT,
    REASON_RULE_MATCH,
    RULE_OPERATORS,
    Condition,
    EvaluationResult,
    Rule,
    evaluate_flag,
    match_condition,
    match_rule,
    normalize_operator,
)
from .hashing import get_user_bucket, murmur3_32
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

__version__ = "0.2.0"

__all__ = [
    "DEFAULT_HOST",
    "HOST_ENV_VAR",
    "AuthorizationError",
    "BootstrapError",
    "BootstrapTransport",
    "CatalystClient",
    "Condition",
    "ConfigurationError",
    "EvaluationResult",
    "FlagSnapshot",
    "PRESENCE_OPERATORS",
    "REASON_DEFAULT",
    "REASON_FLAG_NOT_FOUND",
    "REASON_KILL_SWITCH",
    "REASON_NO_SNAPSHOT",
    "REASON_ROLLOUT",
    "REASON_RULE_MATCH",
    "RULE_OPERATORS",
    "Rule",
    "Snapshot",
    "__version__",
    "evaluate_flag",
    "get_user_bucket",
    "match_condition",
    "match_rule",
    "murmur3_32",
    "normalize_operator",
    "resolve_host",
]
