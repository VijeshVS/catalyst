# Catalyst Python SDK

A feature flag client for the [Catalyst](https://github.com/VijeshVS/catalyst) platform that
**reads the current snapshot as it evaluates** and decides locally.

Each check is a conditional request, so an unchanged environment costs a `304`
with no body, and a toggle you flip in the dashboard is picked up on the next
check. The decision itself never leaves the process. The client talks to the
hosted API by default, so a working setup needs only a key and a project id.

```python
from catalyst_sdk import CatalystClient

client = CatalystClient(
    sdk_key="cp_prod_a1b2c3d4e5f6g7h8i9j0k1",   # API Keys tab in the dashboard
    project_id="7c9e6679-7425-40de-944b-e07fc1f90ae7",
    env="prod",
)

if client.is_enabled("new-checkout", user_id="user_123",
                     attributes={"email": "alice@acme.com"}):
    ...
```

## Install

```bash
pip install sdk-catalyst
```

The distribution is named **`sdk-catalyst`** (the `catalyst-sdk` name is taken on PyPI by an
unrelated project), but the import name is unchanged:

```python
from catalyst_sdk import CatalystClient
```

From a checkout:

```bash
uv sync            # or: pip install -e ".[dev]"
```

Only runtime dependency is [`httpx`](https://www.python-httpx.org/). Requires Python 3.11+.

## Configuration

| Argument | Required | Notes |
|---|---|---|
| `sdk_key` | yes | An SDK key from the dashboard's **API Keys** tab, sent as `X-SDK-Key`. |
| `project_id` | yes | The bootstrap endpoint is strictly project scoped. |
| `host` | no | Base URL of the Catalyst API. Omit it for the hosted API. |
| `env` | no | Snapshot to load. Defaults to `prod`. |
| `timeout` | no | Per-request HTTP timeout, seconds. Default `5.0`. |
| `default_value` | no | Served for an unknown flag or when no snapshot can be loaded. Default `False`. |
| `refresh_on_evaluate` | no | Read the snapshot as part of each check. Default `True`. |
| `failure_backoff` | no | Seconds to stop retrying after a failed read. Default `5.0`. |
| `offline` | no | Skip the API and load only from the disk cache. Implies `refresh_on_evaluate=False`. |
| `cache_path` | no | `None`/`True` uses `~/.cache/catalyst`, or a path you choose. `False` disables it. |
| `raise_on_error` | no | Let read failures raise out of evaluation instead of degrading. |

`project_id` is worth calling out: `/api/v1/bootstrap` takes it as a query
parameter, so the SDK cannot infer it from the key.

### Choosing the API host

| Source | Precedence |
|---|---|
| `host=` argument | highest |
| `CATALYST_HOST` environment variable | middle |
| hosted API (`catalyst_sdk.DEFAULT_HOST`) | default |

```python
# Staging, a self-hosted instance, or a tunnel to your laptop.
client = CatalystClient(..., host="https://catalyst-api.onrender.com")
```

## Freshness

By default every check reads, so there is no propagation delay to tune. Two
knobs matter when that is not what you want:

```python
# Evaluate from memory only; drive freshness yourself.
client = CatalystClient(..., refresh_on_evaluate=False)
client.start_auto_refresh(interval=30)

# A dead API should not add its timeout to every check.
client = CatalystClient(..., failure_backoff=15.0)
```

* Concurrent checks collapse into a single read, so a thread pool does not
  stampede the API.
* After a failure, reads are held off for `failure_backoff` seconds, so an
  unreachable API costs one timeout per window rather than one per request.
* `get_all()` reads once regardless of how many flags it holds.

## How it works

```
   is_enabled("new-checkout", user_id="u1")
        │
        ├──▶  GET /api/v1/bootstrap
        │      If-None-Match: <last etag>
        │        304            → snapshot unchanged, no body
        │        200            → replace snapshot
        │
        └──▶  local decision against the snapshot  →  bool
```

* **No startup fetch.** Constructing a client performs no I/O, so it cannot fail
  on a cold or unreachable API. The first check is what reads.
* **Conditional read.** Every check sends `If-None-Match`, so an unchanged
  environment costs a `304` with no body. The ETag derives from the project's
  environment version, which every snapshot-affecting mutation bumps.
* **Atomic swap.** A single attribute assignment replaces the snapshot, so
  evaluation never sees a half-updated view.
* **Cheap on the server.** The API answers from a Redis snapshot keyed by
  environment version, so the read does not re-query every flag, state and rule.
  Redis being unavailable only makes it slower.
* **Degrades, never throws.** A failed read keeps serving the last good
  snapshot, then the disk cache, then `default_value`. An explicit `refresh()`
  still raises `AuthorizationError`, because a rejected key will not fix itself.

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

The hot path: one conditional read, then a local decision.

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
refresh failure, including ones that were safely absorbed. Only needed with
`refresh_on_evaluate=False`; otherwise it is redundant with the per-check read.

```python
client.start_auto_refresh(interval=15, on_error=lambda e: log.warning(e))
...
client.stop_auto_refresh()
```

### Health and introspection

```python
client.is_ready      # bool  - a snapshot is loaded
client.version       # int   - environment cache version
client.flag_keys()   # list[str]  (reads memory; read after a check or refresh)
client.stats         # dict  - refresh counters, etag, host, last error
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
directory with `CATALYST_CACHE_DIR`) using an atomic write-then-rename. A read
that fails falls back to it before giving up on `default_value`, so a cold start
or a momentary outage keeps serving correct decisions.

```python
client = CatalystClient(..., offline=True)   # cache only, no network
```

## Error handling

| Exception | Meaning |
|---|---|
| `ConfigurationError` | Missing `sdk_key` / `project_id`, or an empty `host`. Raised at construction. |
| `AuthorizationError` | Key rejected or revoked. Propagates from `refresh()`; absorbed during evaluation. |
| `BootstrapError` | Any other transport or protocol failure. Logged, and the previous snapshot keeps serving. Set `raise_on_error=True` to propagate. |

Evaluation never raises. An unknown flag key, a missing snapshot, and a failed
read all resolve to `default_value` (`False` unless configured otherwise) — a
flag check inside someone else's request must not become a 500. Set
`raise_on_error=True` when you would rather find out.

## Demo

`examples/fastapi_demo/app.py` is a runnable FastAPI service that gates a
checkout endpoint and explains its decisions.

```bash
export CATALYST_SDK_KEY="cp_prod_..."
export CATALYST_PROJECT_ID="<project uuid>"
export CATALYST_ENV="prod"
# Only when running against your own API:
# export CATALYST_HOST="http://localhost:8000"

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

## Releasing

Releases are automated. `.github/workflows/publish-sdk.yml` runs on every push to `main` that
touches this package, and publishes to PyPI if the version in `pyproject.toml` is new.

To cut a release:

1. Bump `version` in `pyproject.toml`
2. Update `CHANGELOG` notes in the commit message
3. Merge to `main`

The workflow runs the SDK suite and the server parity suite **before** publishing, so a broken
version never reaches PyPI. If the version already exists on PyPI the publish is skipped, which
means a merge that only edits docs will not fail. Re-running a failed release is possible from the
Actions tab via **Run workflow**.

Publishing uses PyPI **Trusted Publishing** (OIDC), so no API token is stored in this repository.

## License

MIT
