# Catalyst Python SDK

A zero-latency, in-memory feature flag client for the [Catalyst](../..) platform.

Fetch the bootstrap snapshot once, then evaluate flags **locally with no network
access per call**. Typical `is_enabled()` latency is a couple of microseconds,
against a budget of 1 ms.

```python
from catalyst_sdk import CatalystClient

client = CatalystClient(
    sdk_key="cp_prod_a1b2c3d4e5f6g7h8i9j0k1",   # API Keys tab in the dashboard
    project_id="7c9e6679-7425-40de-944b-e07fc1f90ae7",
    host="http://localhost:8000",
    env="prod",
)

if client.is_enabled("new-checkout", user_id="user_123",
                     attributes={"email": "alice@acme.com"}):
    ...
```

## Install

```bash
pip install catalyst-sdk
```

From a checkout:

```bash
uv sync            # or: pip install -e ".[dev]"
```

Only runtime dependency is [`httpx`](https://www.python-httpx.org/).

## Configuration

| Argument | Required | Notes |
|---|---|---|
| `sdk_key` | yes | An SDK key from the dashboard's **API Keys** tab, sent as `X-SDK-Key`. |
| `project_id` | yes | The bootstrap endpoint is strictly project scoped. |
| `host` | no | Defaults to `http://localhost:8000`. |
| `env` | no | Snapshot to load. Defaults to `prod`. |
| `timeout` | no | Per-request HTTP timeout, seconds. Default `5.0`. |
| `default_value` | no | Served for an unknown flag or before the first load. Default `False`. |
| `offline` | no | Skip the API and load only from the disk cache. |
| `cache_path` | no | `None`/`True` uses `~/.cache/catalyst`, or a path you choose. `False` disables it. |
| `raise_on_error` | no | Re-raise refresh errors instead of keeping the last good snapshot. |

`project_id` is worth calling out: `/api/v1/bootstrap` takes it as a query
parameter, so the SDK cannot infer it from the key.

## How it works

```
                 ┌──────────────────────────────┐
   startup  ───▶ │ GET /api/v1/bootstrap        │  200 → replace snapshot
                 │ If-None-Match: <last etag>   │  304 → keep snapshot
                 └──────────────────────────────┘
                                    │
                          background refresh thread
                                    │
   is_enabled()  ──▶  in-memory snapshot  ──▶  no I/O
```

* **Fetch on load.** The snapshot is fetched in the constructor.
* **Conditional refresh.** Every refresh sends `If-None-Match`, so an unchanged
  environment costs a `304` with no body. The ETag derives from the project's
  environment version, which every snapshot-affecting mutation bumps.
* **Atomic swap.** A single attribute assignment replaces the snapshot, so
  evaluation never sees a half-updated view.
* **Degrades, never throws.** A failed refresh keeps serving the last good
  snapshot. Only `AuthorizationError` propagates, because a rejected key will
  not fix itself.

## Evaluation precedence

The SDK mirrors the server exactly, in this order:

1. **Emergency kill switch** → serve the flag default
2. **Targeting rules**, ascending `priority`, first match wins → serve its value
3. **Percentage rollout** → deterministic Murmur3 bucket over `flag_key:user_id`
4. **Flag default**

Supported operators: `equals`, `not_equals`, `in`, `not_in`, `contains`,
`starts_with`, `ends_with`, `greater_than`, `greater_than_or_equal`,
`less_than`, `less_than_or_equal`, `exists`, `not_exists`. Short aliases
(`eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `notExists`) are accepted and
normalized.

A missing context attribute makes a condition false, so the rule safely skips
instead of raising.

## API

### `is_enabled(flag_key, user_id="", attributes=None, default_value=None) -> bool`

The hot path. Never performs I/O.

### `evaluate(flag_key, ...) -> EvaluationResult`

Same evaluation, but returns the full decision:

```python
result = client.evaluate("new-checkout", user_id="user_123",
                         attributes={"email": "alice@acme.com"})
result.value        # True
result.reason       # 'RULE_MATCH' | 'PERCENTAGE_ROLLOUT' | 'KILL_SWITCH_ACTIVE'
                    # | 'DEFAULT_VALUE' | 'FLAG_NOT_FOUND' | 'NO_SNAPSHOT'
result.rule_id      # the matched rule, when a rule fired
result.flag_version # snapshot version the decision came from
```

### `get_all(user_id="", attributes=None) -> dict[str, bool]`

Evaluates the whole snapshot in one pass, for rendering a UI.

### `refresh() -> bool`

Conditionally re-fetches. Returns `True` if a new snapshot was applied,
`False` if the server replied `304 Not Modified`.

### `start_auto_refresh(interval=30.0, on_error=None) -> Thread`

Daemon thread that calls `refresh()` on an interval. `on_error` receives every
refresh failure, including ones that were safely absorbed.

```python
client.start_auto_refresh(interval=15, on_error=lambda e: log.warning(e))
...
client.stop_auto_refresh()
```

### Health and introspection

```python
client.is_ready      # bool  - a snapshot is loaded
client.version       # int   - environment cache version
client.flag_keys()   # list[str]
client.stats         # dict  - refresh counters, etag, last error
client.last_error    # str | None
```

### Lifecycle

`CatalystClient` is a context manager and closes its HTTP pool:

```python
with CatalystClient(...) as client:
    ...
```

## Offline and disk cache

The last good snapshot is written to `~/.cache/catalyst` (override the
directory with `CATALYST_CACHE_DIR`) using an atomic write-then-rename. On a
cold start with no network the SDK loads from there, so a restart keeps serving
correct decisions.

```python
client = CatalystClient(..., offline=True)   # cache only, no network
```

## Error handling

| Exception | Meaning |
|---|---|
| `ConfigurationError` | Missing `sdk_key` / `project_id` / `host`. Raised at construction. |
| `AuthorizationError` | Key rejected or revoked. Always propagates. |
| `BootstrapError` | Any other transport or protocol failure. Logged, and the previous snapshot keeps serving. Set `raise_on_error=True` to propagate. |

Evaluation never raises. An unknown flag key, a missing snapshot, and a failed
refresh all resolve to `default_value` (`False` unless configured otherwise).

## Demo

`examples/fastapi_demo/app.py` is a runnable FastAPI service that gates a
checkout endpoint and explains its decisions.

```bash
export CATALYST_SDK_KEY="cp_prod_..."
export CATALYST_PROJECT_ID="<project uuid>"
export CATALYST_HOST="http://localhost:8000"
export CATALYST_ENV="prod"

python examples/fastapi_demo/app.py

curl localhost:9000/api/checkout?user_id=user_123 -H 'x-user-email: alice@acme.com'
curl localhost:9000/api/inspect?flag=new-checkout\&user_id=user_123
curl localhost:9000/health
```

## Tests

```bash
pytest
```

Two layers guard correctness:

* The SDK's own suite covers hashing, the operator matrix, precedence, ETag
  handling, refresh, auto-refresh, and the disk cache.
* `backend/tests/test_sdk_parity.py` is a **differential test** that runs the
  server's evaluator and the SDK's evaluator over the same fuzzed inputs and
  requires identical values, reasons, and rule ids. It also checks Murmur3
  against the real `mmh3` library. Run it with the backend suite:

  ```bash
  cd backend && uv run pytest tests/test_sdk_parity.py
  ```

## License

MIT
