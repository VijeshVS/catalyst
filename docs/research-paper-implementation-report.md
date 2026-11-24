# Catalyst Implementation Report — For an IEEE Conference-Format Paper

> **Method note (how this report was produced).** Every claim in this document was
> checked against the current source tree, not the documentation. Where
> `README.md`, `AGENTS.md`, or the older `docs/PRD.md` / `TECH_SPEC.md` /
> `USE_CASES.md` / `POC.md` disagree with the code, the code is reported as the
> source of truth and the discrepancy is called out explicitly (see
> §12 "Results and Discussion"). Major test suites were **executed and
> re-verified**; nothing was quoted from old runs without checking the current
> tree.

---

## 1. Project Overview

### 1.1 Actual purpose

Catalyst is a **feature flag control plane** — a self-hostable SaaS that lets
products ship and kill features without a deploy (`README.md:5-7`). Its core
capabilities, per the current code:

1. **Organization → project → environment hierarchy** with strict tenancy
   (`backend/app/models/models.py`, §4).
2. **Flag management**: create, list, get, edit metadata (`PATCH` name/description),
   and environment-scoped state (`enabled` emergency kill switch, `enable_all`,
   0–100 `percentage` rollout) — all in `backend/app/api/v1/flags.py`,
   `backend/app/schemas/schemas.py`, `Flag`/`FlagEnvState` models.
3. **Rule-based targeting**: AND-ed conditions per rule, ordered by `priority`,
   served/serve-false on match, full CRUD + reorder — `TargetingRule`,
   `backend/app/api/v1/flags.py` (rules endpoints), `backend/app/services/rules.py`,
   operators catalogue in `backend/app/services/evaluator.py`.
4. **Feature evaluation**: `POST /api/v1/evaluate` and `POST /api/v1/batch-evaluate`
   evaluate a flag for a `user_id` + attributes — `backend/app/api/v1/evaluate.py`.
5. **Snapshot distribution**: `GET /api/v1/bootstrap` serves a version-validated,
   Redis-cached environment snapshot with HTTP ETag/304 — `backend/app/api/v1/bootstrap.py`,
   `backend/app/services/snapshots.py`.
6. **SDK evaluation**: `catalyst_sdk.CatalystClient.is_enabled()/evaluate()`
   decides locally against a conditionally-read snapshot — `packages/catalyst-python-sdk/src/catalyst_sdk/client.py`.
7. **Dashboard**: React/Vite SPA for management, flag CRUD, kill toggles,
   rollout slider, rule builder, playground evaluation, API keys page, audit page
   (`frontend/src/App.tsx`).
8. **Audit trail**: `AuditLog` rows on authenticated mutations —
   `backend/app/api/v1/flags.py`, `projects.py`, `organizations.py`,
   `backend/app/api/v1/audit.py`.
9. **API keys** (`cp_<env>_<random>`) for SDK access — `backend/app/services/api_keys.py`,
   `backend/app/api/v1/projects.py`.

**Key architectural statement** (`README.md:5-7`): *"Ship features with
confidence: kill switches, percentage rollouts, and rule-based targeting, served
from a version-validated snapshot so a flag check is a single conditional request
and a local decision."* This is the thesis the IEEE paper can rest on: a
distributed-systems-flavored evaluation engine (rules + deterministic hashing)
with snapshot versioning/caching making local evaluation cheap.

### 1.2 Current deployed architecture and application workflow

Current workflow (implementation):

```
React/Vite dashboard (frontend/)  ──Bearer JWT + localStorage refresh──►
FastAPI API (backend/, :8000)  ──PostgreSQL 16 via asyncpg (source of truth)
                                 └──Redis 7 (optional snapshot cache)
catalyst_sdk.CatalystClient (Python) ──GET /api/v1/bootstrap (If-None-Match)──►
same FastAPI API, evaluated locally
```

Concrete data/call flow:

1. User logs in: `POST /api/v1/auth/login` → JWT access+refresh
   (`backend/app/api/v1/auth.py`).
2. Dashboard loads flags: `GET /api/v1/flags?project_id=…`
   (`frontend/src/api.ts` `fetchFlags`), re-polled every **5000 ms** by
   `useProject` (`frontend/src/workspace/useProject.ts:131`).
3. A `PATCH /flags/{key}/environments/{env}` (kill switch / percentage)
   bumps `Environment.version` and evicts the Redis snapshot
   (`backend/app/services/environments.py::bump_environment_versions`).
4. SDK check: `client.is_enabled("key", user_id=…, attributes=…)` → conditional
   GET `/api/v1/bootstrap?project_id=…&env=…` → server builds/serves the
   snapshot → client evaluates locally (`client.evaluate`).
5. Debug/playground: `POST /api/v1/evaluate` (used by the dashboard playground
   `EvalPlayground` and by thin clients).

Note: this differs from the outdated docs (see §12.3): the implementation has
**no real-time push**; freshness is per-read/per-check, which is stated and
deliberate (current `docs` describe `docs/PRD.md` V1.1 and `docs/TECH_SPEC.md`
V2.0 — the two agree with each other but not with the code; details in §12.3).

### 1.3 Website and documentation URLs (from `README.md`)

- **Website**: <https://catalyst-service.vercel.app> (README.md:9)
- **Visual docs**: <https://vijeshvs.github.io/catalyst/> (README.md:10)
- Repository: <https://github.com/VijeshVS/catalyst> (`AGENTS.md:3`)

---

## 2. Technology Stack (technologies actually present in the repository)

Backend (`backend/pyproject.toml`, `AGENTS.md`, `backend/app/main.py`):

| Area | Technology (as present) |
|---|---|
| Backend | FastAPI ≥ 0.141.1, Python 3.12, `uv` build |
| Web server (dev/prod via Render) | Uvicorn (`uvicorn app.main:app`) |
| Database | PostgreSQL 16, SQLAlchemy 2.0 async (`sqlalchemy[asyncio]`), asyncpg |
| Cache | Redis 7 (`redis.asyncio` client) |
| Auth | Passlib `CryptContext` (bcrypt), python-jose[cryptography] (HS256 JWTs) |
| Schema sync | Startup `Base.metadata.create_all()`; one-time SQL migrations in `backend/migrations/` |
| Secrets | `bcrypt` (long passwords pre-hashed to 44 bytes — `backend/app/core/security.py:27-33`) |

Frontend (`frontend/package.json`, `frontend/README.md`):

- React 19, Vite 8, TypeScript (`tsc -b && vite build`), React Router v6
- Testing: Vitest (`vitest run`), jsdom, @testing-library/react, oxlint

SDK (`packages/catalyst-python-sdk/pyproject.toml`, README):

- Distribution **`sdk-catalyst`**, import name **`catalyst_sdk`** (the
  `catalyst-sdk` name is taken by an unrelated PyPI project — README:44-45)
- Build: Hatchling (ships `py.typed`, `license = "MIT"` + bundled `LICENSE`)
- Runtime dep: **httpx** only; dev deps: pytest, mmh3
- Requires Python ≥ 3.11

Local infra (`docker-compose.yml`): PostgreSQL 16 (`postgres:16-alpine`, port
5432, appendonly Redis 7 (`redis:7-alpine`, port 6379, `--appendonly yes`).

Misc: `Makefile` targets `up/down/dev-api/dev-web/test/test-sdk/build-sdk`
(`Makefile:15-34`).

---

## 3. System Architecture

### 3.1 Frontend ↔ backend communication

`frontend/src/api.ts` is the typed, auth-aware client:

- **Base URLs**: `VITE_API_BASE_URL` (build-time) defaulting to the relative
  `/api/v1` (Vite dev proxy), `HEALTH_URL = '/healthz'` (api.ts:158-161).
  Deployment requires setting `VITE_API_BASE_URL` at build time
  (frontend/README.md:22, root `README.md` gotcha).
- **Auth flow**: `AuthProvider` restores session from the localStorage refresh
  token via `POST /auth/refresh` (`api.ts:253-287`,
  `frontend/src/auth/AuthContext.tsx`); the access token lives in memory only;
  the refresh token is in localStorage (documented MVP tradeoff).
- **401 handling**: one retry after refreshing the access token
  (`api.ts:298-323`); on failure the `auth-expired` event is emitted and the
  user is redirected to `/login` by `ProtectedRoute`.
- **Data flow (dashboard)**: `useProject(projectId)` owns flags, environments,
  active-env state, playground evaluation and mutations
  (`frontend/src/workspace/useProject.ts`); `load()` fetches `fetchFlags` +
  `fetchProjectEnvironments` and **polls every 5000 ms** (`useProject.ts:131`);
  mutations (`toggleKillSwitch`, `updateRollout`, rules CRUD) PATCH then
  re-`load()`; `RolloutSlider` is debounced (400 ms, flushed on pointer/key
  release or blur) so a drag is one PATCH (`RolloutSlider.tsx:51-93`).
- **Data flow (playground)**: `EvalPlayground` calls `projectData.evaluate()`
  → `POST /api/v1/evaluate` (`api.ts:582-604`,
  `useProject.ts:241-272`) and renders `value` + `reason`
  (`EvalPlayground.tsx:12-21` gives reason labels).

### 3.2 Backend modules and responsibilities

Entry: `backend/app/main.py` — FastAPI app, lifespan runs
`Base.metadata.create_all()` + `_verify_auth_schema()` (fails on old DBs with a
migration message), `init_redis()`; CORS middleware; `/` root returns
`{"name": "Catalyst Feature Flag Platform", "status": "operational", …}`.

`backend/app/api/v1/` (mounted at `/api/v1` by `api/v1/__init__.py`):

| Route(s) | File | Responsibility |
|---|---|---|
| `GET /healthz` | `health.py` | DB + Redis health |
| `/auth` register/login/refresh/me | `auth.py` | account auth, typed JWTs |
| `/organizations` | `organizations.py` | org CRUD, list with projects, project creation auto-provisions `dev/staging/prod` |
| `/projects/{id}/environments` (+`/keys`) | `projects.py` | env list/create; API key create/list/delete |
| `/flags` (+PATCH, rules, reorder) | `flags.py` | flag create/get/patch/rules CRUD/reorder |
| `/evaluate`, `/batch-evaluate` | `evaluate.py` | server-side flag evaluation (playground + thin clients) |
| `GET /bootstrap` | `bootstrap.py` | SDK snapshot with ETag/304 |
| `/audit` | `audit.py` | audit log list (project scoped) |

Shared lookups in `backend/app/api/v1/deps.py`: `get_current_user`,
`get_organization_or_404`, `get_project_or_404` (joins Organization, filters on
`Organization.owner_id == current_user.id`), `get_environment_or_404`
(env belongs to project AND project owned by user → `404` for inaccessible
resources, avoiding ID enumeration), and `get_current_sdk_key_or_user`
(`X-SDK-Key` → hashed lookup → `404 API key not found` for unknown keys,
`401` for revoked; or Bearer user).

Business logic in `backend/app/services/`:

- `evaluator.py` — **the evaluation engine** (`evaluate_flag`, `match_condition`,
  `match_rule`, `get_user_bucket`, operator catalogue + aliases) — §6.
- `environments.py` — provisioning of `dev/staging/prod`
  (`STANDARD_ENVIRONMENTS`), `seed_missing_flag_states` (new flag → `percentage=0`
  everywhere, `enabled=True`, `enable_all=False`), and the single invalidation
  hook `bump_environment_versions()` (bumps `Environment.version` +
  `invalidate_env_snapshots`).
- `snapshots.py` — Redis-backed environment snapshot with version validation
  (`EnvSnapshot.from_cache_entry` returns `None` if cached `version != version`
  param), `build_etag()`, `load_env_snapshot()`, `invalidate_env_snapshots()`.
- `rules.py` — dense priority renormalization, reorder validation
  (`apply_ordered_ids`: every rule must appear exactly once or `400`),
  rule serializers for audit payloads.
- `api_keys.py` — key generation/hashing/lookup/listing.

`backend/app/core/`:

- `config.py` — pydantic-settings (`JWT_SECRET`, `JWT_ALGORITHM=HS256`,
  `ACCESS_TOKEN_EXPIRE_MINUTES=15`, `REFRESH_TOKEN_EXPIRE_DAYS=7`,
  `AUTH_RATE_LIMIT=5`, `AUTH_RATE_WINDOW_SECONDS=60`,
  `DATABASE_URL`, `REDIS_URL`, `SNAPSHOT_CACHE_ENABLED=True`,
  `SNAPSHOT_CACHE_TTL=60`, `CORS_ORIGINS`).
- `db.py` — async engine, `Base`, `get_db` session dependency.
- `security.py` — bcrypt (`hash_password`/`verify_password` with 72-byte
  pre-hash), typed JWTs (`create_token` with `sub`/`type`/`iat`/`exp`,
  `decode_token` validates type), process-local auth-request limiter.
- `cache.py` — Redis connection lifecycle + `snapshot_key()` +
  `cache_get_json`/`cache_set_json`/`cache_delete` (all swallow Redis errors
  and report a miss — "a cache outage is a slowdown, not an outage").

### 3.3 Database structure and relationships

Models in `backend/app/models/models.py` (PostgreSQL, SQLAlchemy 2.0):

```text
users (User: id UUID-str PK, email unique+index, password_hash, full_name, created_at)
organizations (Organization: id, name unique, description?, owner_id FK→users.id ON DELETE SET NULL, created_at)
projects (Project: id, org_id FK→organizations.id CASCADE, name, created_at)
environments (Environment: id, project_id FK→projects.id CASCADE, name, version default 1, created_at; UNIQUE(project_id,name))
flags (Flag: id, project_id FK, key, name, description?, created_at, updated_at; UNIQUE(project_id,key))
flag_env_states (FlagEnvState: id, flag_id FK, env, enabled, enable_all, percentage, version, updated_at; UNIQUE(flag_id,env))
targeting_rules (TargetingRule: id, flag_id FK, env, name?, priority, conditions_json (JSON), serve, created_at, updated_at; INDEX(flag_id,env,priority))
api_keys (ApiKey: id, project_id FK, env, name, prefix, hash, revoked, created_at)
audit_logs (AuditLog: id, org_id, project_id(+index), flag_id?, env?, actor, user_id? FK, user_email?, action, before?, after?, created_at(+index))
```

Relationships: `Organization.projects` (cascade), `Project.organizations`,
`Project.environments`, `Project.flags`, `Project.api_keys`,
`Flag.states`, `Flag.rules` (both cascade delete-orphan).

Key facts:

- `Organization.owner_id` is the ownership boundary ("users can own multiple
  organizations" — `User.organizations`).
- `Flag` has **no** `default_value` column in current code (dropped by
  `backend/migrations/003_enable_all.sql`) — a flag is always boolean via
  switches.
- There is no archive concept: a retired flag is one with the kill switch on or
  rollout 0 (`AGENTS.md`, `FlagEnvState` docstring).
- Timestamps: `FlagEnvState.updated_at` bumped on every state mutation;
  `Flag.updated_at` on create/edit; `Environment.created_at` = provisioning time.
  (`backend/migrations/002_updated_at.sql` added these columns for existing DBs.)

### 3.4 Redis usage and caching strategy

- Snapshot cache key: `catalyst:snapshot:<project_id>:<env>`
  (`backend/app/core/cache.py::snapshot_key`, `backend/app/services/snapshots.py`).
  Entry: `{"version": <Environment.version>, "flags": {flag_key: {…}}}` with
  `ex=SNAPSHOT_CACHE_TTL` (default 60 s).
- **Version validation on read**: `EnvSnapshot.from_cache_entry` rejects an
  entry when `entry["version"] != environment.version` — "an entry written
  before the last mutation is a miss, not a stale read"
  (`snapshots.py:63-90`).
- **Version validation on write/invalidate**: every snapshot-affecting mutation
  routes through `bump_environment_versions()` (flag create/update, env-state
  PATCH, rule create/update/delete/reorder) → `Environment.version += 1` +
  `invalidate_env_snapshots()` (eager `DEL` of cached keys). The TTL is a
  backstop for a mutation that forgot to bump.
- Redis degradation: `cache_get_json` on error → miss; undecodable entries →
  miss and overwrite; `get_redis()` returning `None` → rebuild from Postgres.
  Health endpoint (`/api/v1/healthz`) treats absent Redis as **not degraded**,
  failing only on DB errors or ping failures (`backend/app/api/v1/health.py`).

### 3.5 SDK architecture and integration workflow

Files: `packages/catalyst-python-sdk/src/catalyst_sdk/{client,evaluator,hashing,snapshot,transport,__init__}.py`.

- `transport.py` — `BootstrapTransport.bootstrap(etag)` GETs
  `{host}/api/v1/bootstrap?project_id=…&env=…` with `X-SDK-Key` header, sends
  `If-None-Match: <etag>`; classifies result: `FetchResult(snapshot=…)` (200),
  `FetchResult(not_modified=True, etag=…)` (304), `AuthorizationError`
  (401/403), `BootstrapError` (other ≥400/non-JSON). `DEFAULT_HOST =
  "https://catalyst-api-uakz.onrender.com"`; override per client with `host=`
  or per process with `CATALYST_HOST` (arg wins; explicit empty `host=`
  raises `ConfigurationError`).
- `snapshot.py` — immutable `Snapshot`/`FlagSnapshot`/`Rule`/`Condition`
  dataclasses; parses camelCase `enableAll`; sorts rules defensively by
  priority.
- `hashing.py` — vendored MurmurHash3 x86_32 (`murmur3_32`, seed 0, returns
  **unsigned**) so no native extension is needed; parity-verified against the
  real `mmh3` in tests.
- `evaluator.py` — local evaluator, "byte-for-byte equivalent to the Catalyst
  server" (mirrors `app/services/evaluator.py`); adds SDK-only reasons
  `NO_SNAPSHOT` and `FLAG_NOT_FOUND` (the server's `/evaluate` answers
  `FLAG_NOT_FOUND`).
- `client.py` — `CatalystClient`: construction does **no I/O**; every check
  (`evaluate`/`is_enabled`/`get_all`) makes a conditional read first
  (single-flight via `_read_lock`), then a pure local decision; snapshot swap
  is one attribute assignment; on failure: logs, sets `_read_failed`
  (fails closed — serves `false`); `failure_backoff` (default 5 s) holds off
  automatic reads after a failure; `refresh()` raises `AuthorizationError`
  (key won't fix itself) but is absorbed inside evaluation. `for_user()`
  returns `UserScopedClient` — a `__slots__` view sharing parent transport +
  snapshot; per-call `attributes` merge onto bound ones (ADR-001).

Integration example (from `packages/catalyst-python-sdk/README.md:14-23`):

```python
from catalyst_sdk import CatalystClient

client = CatalystClient(
    sdk_key="cp_prod_a1b2c3d4e5f6g7h8i9j0k1",
    project_id="7c9e6679-7425-40de-944b-e07fc1f90ae7",
    env="prod",
)
if client.is_enabled("new-checkout", user_id="user_123",
                     attributes={"email": "alice@acme.com"}):
    ...
```

### 3.6 Deployment architecture

From `render.yaml`, `docker-compose.yml`, and AGENTS.md deployment notes:

- **API**: Render web service `catalyst-api` (plan `free`, region `oregon`,
  runtime `python`, `PYTHON_VERSION` 3.12.11, `healthCheckPath: /healthz`,
  `autoDeploy: true`). Built with `uv` (native, no Docker).
- **Render build filter**: `backend/**` — only backend pushes redeploy.
- **Database**: Neon project `catalyst` (`aws-us-west-2`, PG 16.15),
  `DATABASE_URL` injected via Render env-vars (`generateValue` unused for it;
  key-based). Neon's `sslmode=require` is stripped before asyncpg.
- **Cache**: Render Key Value `catalyst-cache` (free, 25 MB, `REDIS_URL`),
  in-memory, empty after every restart.
- **Frontend**: Vercel project `catalyst-dashboard`, rootDirectory `frontend`,
  production branch `main`; needs `VITE_API_BASE_URL` at build time.
- **Visual docs**: GitHub Pages via `pages.yml` (hosts `visual/`).
- **GitHub Workflow (AGENTS.md §GitHub Workflow)**: no direct push to `main`;
  Conventional Commits; PR title `release(<scope>): <description>`; PR body
  non-empty; enforced by `pr-hygiene.yml`.
- Render spins down after 15 min idle; Neon suspends when idle. Neither backs
  up. (AGENTS.md, "Deployment" notes.)

### 3.7 Mermaid architecture diagram

```mermaid
graph TB
    subgraph "Dashboard (frontend/)"
        FE[React 19 + Vite + TS<br/>React Router v6]
    end
    subgraph "API (backend/app)"
        API[FastAPI :8000<br/>CORS]
        DEP[deps: get_project_or_404, get_environment_or_404,<br/>get_current_user, get_current_sdk_key_or_user]
        EV[services/evaluator.py]
        SNAP[services/snapshots.py]
        FLAG[api/v1/flags.py, evaluate.py, bootstrap.py, audit.py]
    end
    subgraph "Storage / Cache"
        PG[(PostgreSQL 16<br/>via asyncpg + SQLAlchemy 2.0)]
        REDIS[(Redis 7<br/>key: catalyst:snapshot:<project>:<env>)]
    end
    subgraph "SDKs (integration points)"
        SDKPY[catalyst_sdk.CatalystClient<br/>is_enabled() / evaluate()]
    end

    FE -- Bearer JWT,<br/>localStorage refresh --o API
    FE -- POST /flags, PATCH state, rules CRUD<br/>GET /flags, GET /audit --o API
    FE -- POST /evaluate (playground) --o API
    SDKPY -- X-SDK-Key, GET /api/v1/bootstrap<br/>(If-None-Match), optional 304 --o API
    SDKPY -- local evaluation (evaluator.py) --> flagDecision[served value + reason]
    API -- select Flag/FlagEnvState/TargetingRule --o PG
    API -- read/write snapshot JSON, TTL 60s --o REDIS
    API -- mutate -- Bump Environment.version
                    + invalidate_env_snapshots --> REDIS
    API -- /healthz: DB + Redis ping --o PG
    API -- /bootstrap: ETag = W/"project:env:version" --> FE, SDKPY
```

---

## 4. Multi-Tenant Architecture

- **Hierarchy**: `Organization` (owned by `User` via `Organization.owner_id`)
  → `Project` → `Environment` → `Flag`/`FlagEnvState`/`TargetingRule`.
  `User` can own multiple organizations (`User.organizations`).
  `Organization.owner_id` is the ownership boundary; there is no default
  org/project — both are created explicitly
  (`backend/app/api/v1/organizations.py:70-94`).
- **Ownership checks**: `get_project_or_404` joins `Organization` and filters
  `Organization.owner_id == current_user.id`; same for environments
  (`deps.py:59-104`). All "404 for inaccessible resources" rules avoid ID
  enumeration (`deps.py:53-55`, `bootstrap.py:67`).
- **Uniqueness/scoping**:
  - `Organization.name` unique → `409` on duplicates (`organizations.py:76-81`).
  - `Project.name` unique within org → `409`.
  - `Flag.key` unique within project (`uq_project_flag_key`) → duplicate
    returns `400` on create (`flags.py:107-114`); same flag key can coexist in
    different projects.
  - `Environment` name unique per project (`uq_project_env_name`) → `409`.
  - **Strict project scoping**: every flag/evaluate/bootstrap/audit endpoint
    requires `project_id` (`422` missing, `404` unknown) and queries filter by
    `Flag.project_id` / `AuditLog.project_id` (`AGENTS.md`).
- **Auto-provisioning**: creating a project provisions `dev`, `staging`, `prod`
  (`environments.py:19`, `organizations.py:147-148`); creating a flag seeds a
  `FlagEnvState` for every environment of the project (`environments.py:43-81`,
  "new flag pinned to percentage=0"); creating an environment seeds missing
  states for all flags (`projects.py:67-68`).
- **Isolation**: `TargetingRule`/`FlagEnvState` are env-scoped
  (`flag_id` + `env`); evaluation resolves per-env state/rules via
  `snapshots.py::_flag_entry` which only includes `rule.env == env`.
- **Improvements from earlier implementations (documented behavior)**:
  - Version-validated snapshot cache + ETag/304 (added with auth; documented
    as "Phase 2" migrations).
  - `Environment.version` as the single invalidation counter (previously
    `FlagEnvState.version` was the main version; now version lives on
    `Environment` and drives the ETag).
  - API-key lifecycle now deletes rows (ADR-002); legacy `revoked` column is
    kept as defence-in-depth and is never set by new code.

---

## 5. Feature Flag Management

### 5.1 Flag lifecycle endpoints (current API surface)

- `POST /api/v1/flags?project_id=` — create (key regex `^[a-z0-9-_.]+$`,
  name required). `201`. Audits `flag.created`.
- `GET /api/v1/flags?project_id=` — list, ordered `created_at desc`.
- `GET /api/v1/flags/{key}?project_id=` — get.
- `PATCH /api/v1/flags/{key}?project_id=` — edit `name`/`description` only;
  bumps all env versions when changed; audits `flag.updated`.
- `DELETE` on flags — **not implemented** (no archive concept; kill switch is
  the deletion mechanism).

### 5.2 Environment state: kill switch, enable-all, rollout

`PATCH /api/v1/flags/{key}/environments/{env}?project_id=`
(`flags.py:211-285`, `FlagStateUpdate` in `schemas.py:183-187`):

- Fields: `enabled` (bool, **Emergency Kill Switch**, `false` = nobody),
  `enable_all` (bool, "serve true to everybody, with no rules and no rollout"),
  `percentage` (int, **0–100 inclusive**, `Field(ge=0, le=100)`).
- Side effects: `state.version += 1` and
  `bump_environment_versions(project_id, env_names=[env])`; audits one of
  `kill_switch.activated`, `kill_switch.deactivated`, `enable_all.activated`,
  `enable_all.deactivated`, `rollout.percentage_updated` or `flag.updated`.
- Defaults for missing state rows: `enabled=True, enable_all=False, percentage=0`
  (`flags.py:233-237`); seeded states from flag creation are pinned to
  `percentage=0` (`environments.py:69-79`).

### 5.3 Rule-based targeting

Data model: `TargetingRule` (§3.3). Management endpoints
(`flags.py:291-505`):

- `GET /flags/{key}/environments/{env}/rules` — list, priority ascending.
- `POST /flags/{key}/environments/{env}/rules` — create; `priority` optional
  (appended after the current max via `next_priority`); audits `rule.created`.
- `PUT /flags/{key}/environments/{env}/rules/reorder` — full ordering
  (`RuleReorder.rule_ids` must list every rule of the env exactly once or
  `400`); renormalizes to dense `0..n-1` (`normalize_priorities`); audits
  `rule.reordered` with before/after id orders.
- `PUT /flags/{key}/environments/{env}/rules/{rule_id}` — edit
  name/conditions/serve/priority; audits `rule.updated`.
- `DELETE /flags/{key}/environments/{env}/rules/{rule_id}` — `204`; closes
  priority gaps by renormalizing; audits `rule.deleted`.

`RuleCreate`/`RuleUpdate` validation (`schemas.py:230-254`):

- 1–25 conditions (`min_length=1, max_length=25`).
- `serve: bool = True` — the value served when every condition matches.
- `name: str = ""` — optional operator label.
- `priority: Optional[int] = Field(ge=0)` — `0` is highest.

### 5.4 Condition model and supported operators

`RuleCondition` (`schemas.py:189-227`): `attr` (1–64 chars, pattern
`^[A-Za-z0-9_.:-]+$`), `op` (string, default `"equals"`), `value` (any, ignored
by presence operators).

Canonical operators (`evaluator.py:8-22`):

```
equals, not_equals, in, not_in, contains, starts_with, ends_with,
greater_than, greater_than_or_equal, less_than, less_than_or_equal,
exists, not_exists
```

Aliases accepted on write and normalized (`normalize_operator`,
`evaluator.py:28-49`): `eq→equals`, `neq→not_equals`, `gt→greater_than`,
`gte→greater_than_or_equal`, `lt→less_than`, `lte→less_than_or_equal`,
`notexists→not_exists` (plus `not_exists` itself, `exists`).

Evaluation semantics of conditions (`evaluator.py:61-115`, mirrors in
`catalyst_sdk/evaluator.py:145-200`):

- **AND within a rule** (`match_rule` uses `all()`).
- **Missing attribute** → condition false → rule skips (no exceptions).
- `equals` case-sensitive (Python `==` on the value; booleans must be real
  booleans).
- `contains`, `starts_with`, `ends_with` are case-insensitive
  (`str(...).lower()`).
- `in`/`not_in`: list or comma-separated string (server stringifies the actual
  value in the string branch: `str(actual) in [x.strip() for x in
  str(target).split(",")]`).
- Numeric operators (`greater_than*`, `less_than*`) use `float()` and return
  `False` on `ValueError/TypeError`.
- `exists`/`not_exists` inspect presence only; `value` is normalized to a
  boolean (`schemas.py:222-227`).
- `conditions_json` is exposed as `conditions` on every wire format
  (`snapshots._flag_entry`, `rules.serialize_rule`).

The SDK mirrors this (`catalyst_sdk/evaluator.py:145-200`) and parity is
fuzz-tested (§10.5).

---

## 6. Feature Evaluation Algorithm (exact, precise)

Source of truth: `backend/app/services/evaluator.py` (server) and
`packages/catalyst-python-sdk/src/catalyst_sdk/evaluator.py` (SDK mirror).
Both are asserted identical by the differential suite (§10.5).

### 6.1 Entry point

```python
def evaluate_flag(flag_key: str, enabled: bool, enable_all: bool,
                  percentage: int, rules: List[Dict],
                  user_id: str, attributes: Dict) -> Tuple[bool, str, Optional[str]]:
```

Returns `(served_value, reason, matched_rule_id)`.

### 6.2 Exact precedence sequence (steps 1–4)

**Step 1 — Emergency Kill Switch** (`evaluator.py:162-164`):
```
if not enabled: return (False, "KILL_SWITCH_ACTIVE", None)
```

**Step 2 — Enable to all users** (`evaluator.py:166-168`):
```
if enable_all: return (True, "ENABLE_ALL_USERS", None)
```

**Step 3 — Rules decide the population** (`evaluator.py:170-184`):
```
matched = first rule in sorted(rules, key=priority) whose conditions all match
          (match_rule = all(match_condition(cond, attributes)))
if rules and matched is None:
    return (False, "DEFAULT_VALUE", None)   # filtered out; percentage irrelevant
```
Note the loop sorts by `item.get("priority", 0)` itself — the caller's order is
not trusted (`evaluator.py:176-179`); callers already pass sorted lists so this
is a no-op for them.

**Step 4 — Percentage rollout** (`evaluator.py:186-199`):
```
serve   = True if matched is None else bool(matched.get("serve", True))
rule_id = matched.get("id") if matched else None
bucket  = get_user_bucket(flag_key, user_id)
inside  = bucket < percentage
if inside:
    return (serve, "RULE_AND_ROLLOUT" if matched else "PERCENTAGE_ROLLOUT", rule_id)
return (not serve,
        "RULE_OUTSIDE_ROLLOUT" if matched else "PERCENTAGE_OUTSIDE_ROLLOUT",
        rule_id)
```

Key invariant (documented in `evaluator.py:186-190` and AGENTS.md): *a matched
user outside the bucket gets the opposite of the rule's value*, so the matched
group is partitioned exactly by the rollout.

### 6.3 `get_user_bucket` — MurmurHash3 x86_32 details (precise)

Server (`evaluator.py:52-58`):

```python
raw_hash = mmh3.hash(f"{flag_key}:{user_id}")     # seed = 0 (mmh3 default)
return (raw_hash & 0xFFFFFFFF) % 100              # bucket ∈ 0..99
```

- **Hash input**: the string `f"{flag_key}:{user_id}"` encoded UTF-8.
- **Seed**: 0.
- **Signed/unsigned**: `mmh3.hash()` returns a signed 32-bit int; the
  `& 0xFFFFFFFF` masks to the unsigned equivalent.
- **Bucket**: `unsigned_hash % 100` — a fixed integer per (flag_key, user_id).
- **Sticky**: same input → same bucket; raising the percentage only ever
  *adds* users (`bucket < p` is monotone in `p`).

SDK mirror (`catalyst_sdk/hashing.py`): vendored `murmur3_32(data, seed=0)`
returns the **unsigned** value directly (the reference `mmh3.hash()` returns
signed, so callers mask — the SDK does not), and:

```python
def get_user_bucket(flag_key: str, user_id: str) -> int:
    raw_hash = murmur3_32(f"{flag_key}:{user_id}".encode("utf-8"))
    return raw_hash % 100
```

Verified concrete examples from the current tree (`backend/app/services/evaluator.py`):

| flag_key | user_id | raw mmh3 (signed) | masked (unsigned) | `% 100` |
|---|---|---|---|---|
| `ai-assistant` | `user_1` | `-57084918` | `4237882378` | **78** |
| `ai-assistant` | `alice@acme.com` | — | — | **34** |
| `ai-assistant` | `""` (empty string) | — | — | **11** |

(With `percentage=50`, `user_1` → `78 >= 50` → outside → served the opposite of
the matched rule; at `percentage=79`, `user_1` flips inside.)

### 6.4 Boundary conditions and edge cases

- `percentage = 0` → nobody served by rollout (`bucket ∈ 0..99 < 0` is never
  true). Server column default is 100, but seeded states pin new flags to 0
  (`environments.py:69-79`).
- `percentage = 100` → everybody inside (`bucket < 100` always).
- No rules at all → Step 3 passes (`matched is None`, `rules` empty so the
  `DEFAULT_VALUE` branch is skipped because `if rules and matched is None` is
  false) → rollout applies with `serve=True`, reason `PERCENTAGE_ROLLOUT`.
- Rules exist, none match → `(False, "DEFAULT_VALUE", None)`.
- Both switches on → kill switch wins (Step 1 short-circuits; `enable_all`
  never reached).
- Both switches off, no rules, percentage `p`: users with `bucket < p` get
  `PERCENTAGE_ROLLOUT` and `True`; the rest get `PERCENTAGE_OUTSIDE_ROLLOUT`
  with value `not serve = False`. (A flag with `percentage` left at the default
  100 serves everyone.)
- Validation: `percentage` must be int in [0, 100] (`FlagStateUpdate` Field
  ge/le) → `422` on out-of-range; `enable_all` and `enabled` are plain booleans.
- `evaluate_flag` never raises on malformed attributes (condition matching
  returns `False` on `ValueError/TypeError`, `evaluator.py:85-113`); unknown
  operators normalize to `equals` or stay as-is via `normalize_operator`.

### 6.5 Reason codes (server `EvaluateResponse.reason`)

`KILL_SWITCH_ACTIVE`, `ENABLE_ALL_USERS`, `RULE_AND_ROLLOUT`,
`RULE_OUTSIDE_ROLLOUT`, `PERCENTAGE_ROLLOUT`, `PERCENTAGE_OUTSIDE_ROLLOUT`,
`DEFAULT_VALUE` (rules filtered the user out), `FLAG_NOT_FOUND` (unknown key on
`/evaluate`). SDK-only extras: `NO_SNAPSHOT` (client evaluated before any
snapshot loaded or after a failed read).

`/evaluate` response shape (`schemas.py:86-94`): `{flag_key, value, reason,
rule_id?}`.

### 6.6 Pseudocode (server, `app/services/evaluator.py:139-199`)

```python
def evaluate_flag(flag_key, enabled, enable_all, percentage, rules, user_id, attributes):
    if not enabled:                        # Step 1
        return False, "KILL_SWITCH_ACTIVE", None
    if enable_all:                         # Step 2
        return True, "ENABLE_ALL_USERS", None

    matched = next((r for r in sorted(rules, key=lambda r: r.get("priority", 0))
                    if match_rule(r.get("conditions", []), attributes)), None)

    if rules and matched is None:          # Step 3
        return False, "DEFAULT_VALUE", None

    serve = True if matched is None else matched.get("serve", True)
    bucket = get_user_bucket(flag_key, user_id)   # Step 4
    if bucket < percentage:
        return serve, ("RULE_AND_ROLLOUT" if matched else "PERCENTAGE_ROLLOUT"), matched and matched["id"]
    return (not serve), \
           ("RULE_OUTSIDE_ROLLOUT" if matched else "PERCENTAGE_OUTSIDE_ROLLOUT"), \
           matched and matched["id"]
```

SDK equivalent: `catalyst_sdk/evaluator.py:215-270` (with
`EvaluationResult(value, reason, rule_id, flag_key, flag_version)`).

---

## 7. Configuration Distribution and Performance

### 7.1 `/bootstrap` (SDK snapshot endpoint, `backend/app/api/v1/bootstrap.py`)

- Auth: `X-SDK-Key` (project-scoped) **or** user Bearer
  (`get_current_sdk_key_or_user`, `deps.py:112-171`).
- `env` query param, **default `dev`** (matches `/evaluate`, `/batch-evaluate`).
- Ownership: SDK key must belong to the requested project → `403` otherwise
  (`bootstrap.py:43-48`); users via `get_project_or_404` (owner check).
- **ETag**: `build_etag(project_id, env, version)` →
  `W/"<project_id>:<env>:<version>"` (`snapshots.py:93-94`).
- **Conditional read**: `request.headers.get("if-none-match")` compared to the
  built ETag → returns `304` with `ETag` + `Cache-Control: private, max-age=0,
  must-revalidate` **before loading the snapshot body** (`bootstrap.py:79-87`).
  Otherwise serves `200` with `ETag`, `X-Catalyst-Cache: redis|postgres`,
  `Cache-Control: private…` (private because authenticated).
- **Snapshot body** (`snapshots.EnvSnapshot.to_payload`):
  `{"env": …, "version": Environment.version, "flags": {flag_key: entry}}`
  where each entry is `{"key", "enabled", "enableAll", "percentage", "rules":
  [{"id", "priority", "conditions", "serve"}]}` (`snapshots.py:97-116`).
- `/evaluate` and `/batch-evaluate` also set `X-Catalyst-Cache` to the snapshot
  source (`evaluate.py:110`, `:134`).

### 7.2 Redis snapshot cache, version validation, invalidation

Detailed in §3.4 (keys `catalyst:snapshot:<project>:<env>`, version-equality
read validation, version bump on mutations, `SNAPSHOT_CACHE_TTL=60` backstop).
The single invalidation hook is `bump_environment_versions()` in
`services/environments.py` — called by flag create/patch, env-state PATCH, rule
create/update/delete/reorder, env creation.

### 7.3 How a flag evaluation request works (SDK, end to end)

From `packages/catalyst-python-sdk/src/catalyst_sdk/client.py:286-398` and
`transport.py:121-169`:

1. `client.is_enabled(key, user_id, attributes)` → `evaluate()` →
   `_read_snapshot()` (unless `refresh_on_evaluate=False` or offline).
2. `refresh()`: GET `/api/v1/bootstrap?project_id&env` with
   `X-SDK-Key` + `If-None-Match` → `304` → keep serving, or `200` → parse and
   swap the immutable snapshot.
3. Local decision: `snapshot.get(flag_key)` →
   `evaluate_flag(flag.key, flag.enabled, flag.enable_all, flag.percentage,
   flag.rules, user_id, attributes, flag_version=flag.version)`.
4. Return `EvaluationResult(value, reason, rule_id, flag_key, flag_version)`.

Fail-closed behavior (`client.py:286-327`, `437-463`): read failures log and
set `_read_failed` → `is_ready` false and `evaluate()` returns
`EvaluationResult(False, "NO_SNAPSHOT")`; `refresh()` sets backoff; explicit
`refresh()` raises `AuthorizationError`.

Server-side evaluation (`/evaluate`, `evaluate.py:97-121`): resolves env →
`load_env_snapshot(db, project.id, req.env, environment.version)` →
`entry = snapshot.flags.get(req.flag_key)` →
`_evaluate_entry` → `EvaluateResponse`. Missing key → `(False, "FLAG_NOT_FOUND")`.

### 7.4 Optimizations actually implemented

- **Snapshot caching** (Redis, version-validated) — the `/bootstrap` read path
  costs one indexed environment lookup on a 304, not a join over flags/states/rules.
- **ETag/If-None-Match** — a flag check with unchanged version costs a tiny
  conditional GET.
- **SDK single-flight** (`_read_lock` collapses concurrent checks into one
  request) and **failure_backoff** (default 5 s, one timeout per window).
- **Atomic snapshot swap** in the SDK (`Snapshot` is frozen; one attribute
  assignment).
- **Deterministic hashing** (Murmur3) → sticky rollouts without server round
  trips; monotone percentage → safe gradual ramp.
- Server-side: `selectinload` on `Flag.states`/`Flag.rules` (snapshots.py),
  async SQLAlchemy engine with pooling (`db.py`).
- `get_all()` reads the snapshot once regardless of flag count.

---

## 8. Security

- **Authentication (dashboard)**: typed JWTs (`core/security.py:57-88`):
  HS256 signed with `JWT_SECRET` (default `change-this-jwt-secret-in-production`),
  claims `sub` (user id), `type` (`access`/`refresh`), `iat`, `exp`.
  Access tokens default **15 min**, refresh tokens **7 days**, both stateless
  and reusable until expiry. Decode validates signature, algorithm, `sub`
  presence, `type` correctness and (optionally) expected type.
- **Tokens**: access token in memory on the frontend; refresh token in
  `localStorage` under `catalyst.refreshToken` (documented MVP tradeoff —
  api.ts:189-201); `/auth/refresh` returns a fresh token pair; retry-once on
  401.
- **Password hashing**: Passlib `CryptContext` schemes `["bcrypt"]`; passwords
  ≥ 8 chars (`UserRegisterRequest`), >72-byte inputs deterministically
  pre-hashed to a 44-byte SHA-256+base64 value so bcrypt never truncates
  (`security.py:27-33`). `verify_password` returns `False` on malformed input.
  `User` exposes `hashed_password` (physical column `password_hash`).
- **API key auth (SDK)**: keys are `cp_<env>_<22-char random>`
  (`api_keys.py:13-21`); only `sha256(raw_key)` is stored; authentication
  hashes the presented key and compares hashes only — the stored `prefix` is a
  non-secret display label, deliberately never matched (`deps.py:107-155`).
  Full key returned only in `ApiKeyCreatedResponse.key` on creation
  (`projects.py:141-149`). Unknown key → `404 API key not found` (no enumeration);
  revoked → `401`. Keys are project-scoped; `_resolve_environment` double-checks
  the key's project matches the request (`evaluate.py:39-44`, `bootstrap.py:43-48`).
  ADR-002 (docs/adr/002): keys are deleted, not revoked; the audit log is the
  durable record that a key existed.
- **Rate limiting**: process-local limiter (`security.py:91-144`) — `AUTH_RATE_LIMIT=5`
  per `(client_ip, path)` per 60 s window on `/auth/register` and `/auth/login`
  (`auth.py:46-47`, `81-82`), returning `429` with `Retry-After`.
- **Authorization checks**: ownership via `Organization.owner_id` everywhere;
  `404` (not `403`) for inaccessible orgs/projects/environments to avoid
  enumeration; API keys are read-only for `/bootstrap` + `/evaluate`.
- **Audit logging**: `AuditLog` rows on all authenticated mutations with
  `actor` (= user email), `user_id`, `user_email` (`flags.py:54-79`,
  `projects.py:126-137`, `organizations.py:150-160`); rule mutations additionally
  record `before`/`after` snapshots of the rule.

---

## 9. SDK (Python)

- **Package**: `sdk-catalyst` (PyPI, import `catalyst_sdk`), Hatchling build,
  `py.typed`, MIT + bundled `LICENSE`, single runtime dep `httpx>=0.27`
  (`pyproject.toml`).
- **Version**: 0.4.0 (`pyproject.toml:3`).
- **Initialization**: `CatalystClient(sdk_key=…, project_id=…)` — no I/O at
  construction (client.py:173-175).
- **Config fetching**: first evaluation (or `refresh()`) performs the
  conditional GET described in §7.3.
- **Local evaluation**: `evaluate_flag` in `catalyst_sdk/evaluator.py` — pure,
  no I/O; mirrors the server (§6).
- **User context**: constructor `user_id=`/`attributes=` as defaults;
  `for_user(user_id, attributes)` → `UserScopedClient` (shares transport/snapshot;
  per-call `attributes` merge onto bound ones). ADR-001.
- **Error handling/fallback**: fails closed (`false` + reason `NO_SNAPSHOT`);
  no disk cache, no `cache_path`; explicit `refresh()` raises
  `AuthorizationError`; `raise_on_error=True` propagates other read failures.
- **Public API surface** (`__init__.py:72-105`): `CatalystClient`,
  `UserScopedClient`, `Snapshot`, `FlagSnapshot`, `Rule`, `Condition`,
  `EvaluationResult`, `evaluate_flag`, `match_condition`, `match_rule`,
  `get_user_bucket`, `murmur3_32`, `normalize_operator`, `RULE_OPERATORS`,
  reason constants, `AuthorizationError`, `BootstrapError`, `ConfigurationError`,
  `BootstrapTransport`, `resolve_host`, `DEFAULT_HOST`, `HOST_ENV_VAR`.
- **Public examples** (README, `packages/catalyst-python-sdk/README.md`):

```python
client = CatalystClient(
    sdk_key="cp_prod_a1b2c3d4e5f6g7h8i9j0k1",
    project_id="7c9e6679-7425-40de-944b-e07fc1f90ae7",
    env="prod",
)
client.is_enabled("new-checkout", user_id="user_123",
                  attributes={"email": "alice@acme.com"})

client = CatalystClient(..., user_id="user_123", attributes={"email": "alice@acme.com"})
client.is_enabled("new-checkout")
alice = client.for_user("alice", {"email": "alice@acme.com"})
alice.is_enabled("new-checkout")
```

- Release process: bump `pyproject.toml` version; CI (below) re-runs SDK +
  parity suites and publishes on new version via PyPI Trusted Publishing (OIDC).

---

## 10. Testing and Validation

### 10.1 Frameworks actually present

- **Backend**: pytest (9.1.1) + pytest-asyncio (1.4.0), aiosqlite, httpx
  (`backend/pyproject.toml`, `backend/tests/`). Self-contained:
  `tests/conftest.py` points the app at a temporary SQLite database
  (`sqlite+aiosqlite:////tmp/catalyst-tests-*/…`) before any `app.*` import.
- **SDK**: pytest; suite run via
  `uv run --with pytest --with mmh3 pytest` (from `packages/catalyst-python-sdk/`,
  per Makefile `test-sdk`).
- **Frontend**: Vitest 3.2.7 (`vitest run`), jsdom, @testing-library/react
  (`frontend/package.json`), lint via **oxlint**, build via `tsc -b && vite build`.
- **Parity**: `backend/tests/test_sdk_parity.py` — a differential suite
  (see §10.5).

### 10.2 Test counts — **verified by execution in this session**

| Suite | Count | Verification |
|---|---|---|
| Backend (`cd backend && uv run pytest`, or `.venv/bin/python -m pytest -p no:cacheprovider -q`) | **113 passed** | Ran: exit 0, `113 passed, 1010 warnings in 15.22s` |
| SDK (`cd packages/catalyst-python-sdk && uv run --with pytest --with mmh3 pytest`) | **106 passed** | Ran: exit 0, 106 dots |
| Frontend (`cd frontend && npm run test`) | **99 passed in 9 files** | Ran `node_modules/.bin/vitest run`: `Test Files 9 passed (9), Tests 99 passed (99), Duration 1.55s` |

Per-file counts as produced by `pytest --collect-only` (what "passed" means —
parametrized cases count as separate items):

- Backend (`cd backend`): `test_api.py` 1, `test_api_keys.py` 9,
  `test_auth.py` 6, `test_evaluator.py` 20 (18 functions),
  `test_flag_update.py` 8, `test_multi_tenancy.py` 7, `test_rules.py` 14,
  `test_sdk_parity.py` 18 (6 functions), `test_snapshot_cache.py` 15,
  `test_timestamps.py` 15 → **113 total**.
- SDK (`cd packages/catalyst-python-sdk`): `test_client.py` 43,
  `test_evaluator.py` 37, `test_transport.py` 9, `test_user_context.py` 17
  → **106 total**.
- Frontend (`cd frontend`, `npm run test` / vitest): 9 test files —
  `api.test.ts` 2, `apiKeysPage.test.tsx` 4, `docsPage.test.tsx` 9,
  `docsSearch.test.ts` 11, `flagCard.test.tsx` 17, `projectHeader.test.tsx` 4,
  `rolloutSlider.test.tsx` 13, `routing.test.tsx` 6, `ruleBuilder.test.tsx` 33
  → **99 total**.

**Not run**: `npm run lint` / `npm run build` (frontend); `ruff` checks; live
deploy smoke tests. (Lint/build outputs are not part of the test counts
reported above.)

### 10.3 Important scenarios covered by the suites (from test names)

Backend (`backend/tests/`): health/root, sticky rollout hashing, kill switch,
rule evaluation (`test_evaluator.py`: precedence, both switches, percentage
boundaries), rule CRUD + condition validation + dense re-ordering, cross-user/
project/environment isolation (`test_multi_tenancy.py`), rule precedence and
environment-scoped cache invalidation (`test_snapshot_cache.py`), organization
and project CRUD, custom environment management, project scoping, bootstrap
ETag scoping (304 → 200 on mutation), Redis snapshot caching including
degradation when Redis is absent/broken/undecodable, registration/login/refresh/me,
password validation and hashing, auth rate limiting, cross-user authorization and
audit attribution, API key management, `X-SDK-Key` auth + project-scoped SDK
access, mutation timestamps and absence of `archived`, 0%/100% rollout endpoints,
rollout monotonicity, the rules-filtered-out case, and server/SDK parity
fuzzing.

SDK (`packages/catalyst-python-sdk/tests/`): hashing (`test_evaluator.py`),
operator matrix, precedence, ETag handling, refresh, auto-refresh, failing
closed (`test_client.py`), user context (`test_user_context.py`, ADR-001),
transport (`test_transport.py`).

### 10.4 Integration & end-to-end

- **Parity suite (server ↔ SDK)** — next section.
- Frontend: routing tests (`routing.test.tsx`), auth-aware API client
  (`api.test.ts`), rule builder, rollout slider debounce/flush behavior, docs
  search, flag card, API keys page, project header.

### 10.5 Server/SDK parity (differential)

`backend/tests/test_sdk_parity.py`:

- `test_user_bucket_matches_the_server` — 5000 random (flag, user) pairs;
  SDK vendored Murmur3 must equal the server's `mmh3.hash(& 0xFFFFFFFF) % 100`.
- `test_operator_normalization_matches_the_server` — all aliases + `None` +
  garbage.
- `test_condition_matching_matches_the_server_for_every_operator` — parametrized
  over all 13 operators × attrs × values × attribute dicts.
- `test_flag_evaluation_matches_the_server_across_fuzzed_inputs` — 3000
  fuzzed whole-flag evaluations; requires identical value, reason, **and
  matched rule id**.
- `test_sdk_reads_the_bootstrap_payload_shape` — guards the wire contract
  (`enableAll` camelCase, rule `conditions`).
- `test_parity_covers_both_switches_and_rules_on_one_flag` — explicit
  decision-table walk (`2×2×5×4×3×3` combos) comparing both evaluators.

This suite is the gate that makes "server is source of truth, SDK mirrors it"
a continuously verified claim (§12.3 covers docs-vs-code drift on this point).

---

## 11. Deployment

- **API**: Render web service `catalyst-api` (free plan, `oregon` region,
  native Python via `uv`, `healthCheckPath: /healthz`, autoDeploy from `main`).
  Build filter `backend/**` — frontend/docs-only pushes do not redeploy.
- **Frontend**: Vercel project `catalyst-dashboard`, rootDirectory `frontend`,
  production branch `main`; `frontend/vercel.json` supplies the SPA rewrite so
  `/docs` and `/app/**` survive hard reloads; `VITE_API_BASE_URL` required at
  build time for non-Vercel origins (root `README.md` gotcha).
- **Database**: Neon project `catalyst` (`aws-us-west-2`, PG 16.15),
  `DATABASE_URL` injected as a secret; tables created by startup
  `create_all()` (no app-level migrations on live DBs).
- **Cache**: Render Key Value `catalyst-cache` (free, 25 MB) — in-memory,
  empty after restarts; assigned to `REDIS_URL`.
- **Visual docs**: GitHub Pages (`pages.yml`), artifacts in `visual/artifacts/`,
  generated by `node visual/build-site.mjs` (`visual/sources/*.json` are the
  editable sources).
- **CI (`.github/workflows/ci.yml`)** — runs on `pull_request` and `push` to `main`:
  - `backend-tests` — Python 3.12 + `uv run pytest` (SQLite-backed).
  - `frontend-checks` — Node 22, `npm ci`, `npm run test`, `npm run lint`,
    `npm run build`.
  - `sdk-tests` — Python 3.12, SDK suite (`uv run --with pytest --with mmh3 pytest`),
    `uv build` wheel check, and the parity suite inside the backend env
    (`uv run pytest tests/test_sdk_parity.py`).
- **`Publish SDK`** — pushes to `main` touching `packages/catalyst-python-sdk/**`;
  runs SDK suite + parity, publishes when version is new via PyPI Trusted
  Publishing (environment `pypi`).
- **`Render Deploy Status`** — publishes the `render/deploy` commit status;
  deploy-relevant pushes wait for the deploy of that SHA, etc. (AGENTS.md §CI).
- **`PR Hygiene`** — on PR open/edit: rejects empty PR bodies and non-Conventional
  Commits.
- **Deployment status**: not verified at runtime (no live probe performed in
  this session; `/healthz` claims in code are from `backend/app/api/v1/health.py`).

---

## 12. Results and Discussion

### 12.1 Actual implemented capabilities (as of this report, `docs/` tree)

- Boolean flags with two switches (`enabled` kill switch, `enable_all`) + 0–100
  rollout per environment (`FlagEnvState`).
- Deterministic sticky percentage rollout via Murmur3 over `flag_key:user_id`
  (§6.3).
- Rule-based targeting with up to 25 ANDed conditions, 13 canonical operators +
  6 short aliases, ordered by dense priorities, full CRUD + reorder, audit
  trails (`rule.created/updated/deleted/reordered`).
- `/evaluate` + `/batch-evaluate` for programmatic clients.
- `/bootstrap` with ETag/304 + `X-Catalyst-Cache` + version-validated Redis
  snapshot cache.
- Dashboard: org/project management, flag CRUD, debounced rollout slider, kill
  switch, enable-all, rules builder with live preview (advisory client-side
  preview in `lib/attributeCatalog.ts`), playground with reason display, API
  keys page (create/list/delete), audit page, docs page (SDK reference kept in
  sync with the SDK README by hand — `DocsPage.tsx`).
- Python SDK 0.4.0 with local evaluation, conditional reads, fail-closed
  behavior, `for_user` user scoping (ADR-001).

### 12.2 Verified test results (this session)

Backend **113 passed** (15.22 s), SDK **106 passed** (exit 0), Frontend
**99 passed in 9 files** (1.55 s). Parity suite (backend) is part of the
backend run (`test_sdk_parity.py`: 5 non-parametrized + 13 parametrized operator
cases + fuzz suite). Lint/build suites were not executed (marked above).

### 12.3 Documentation vs implementation — current code is the source of truth

Discrepancies found while reading the repo (all documented by the team, none
blocking the IEEE paper if written from code):

1. `docs/PRD.md` ("PRD V1 Final", v1.1) and `docs/TECH_SPEC.md` ("TECH SPEC V2 —
   Catalyst Feature Flag Platform", v2.0) describe an **older implementation**:
   Fastify + Prisma (Node TS), `defaultValue`, "OR across rules configurable",
   k6 smoke, <5 s change propagation via SSE/polling, "JS + Python SDK" with
   shared `eval.vectors.json`. **None of the Node/Fastify/Prisma pieces exist
   in the tree** (`glob` confirms: no `apps/`, `packages/js-sdk`,
   `packages/python-sdk`, or `docker-compose` services named `api`/`web`).
2. `scripts/export_doc_pdf.py` + `dist/*.pdf` (`PRD.pdf`, `TECH_SPEC.pdf`, …)
   are generated from those old docs and carry the same stale architecture.
3. `docs/USE_CASES.md` (V2.0) still says "Fetch-on-load only — no SSE, no
   polling" and describes `sdk_key` rotation ("Rotate → old key revoked"), while
   the code implements **delete-not-revoke** (ADR-002) and, importantly, the
   **dashboard polls `/flags` every 5 s** (`useProject.ts:131`) — a real
   difference worth noting.
4. `docs/POC.md` describes an Express/SSE POC — no POC code exists in the tree.
5. Minor differences: PRD/US-1 mentions `sdk_key` on signup auto-provisioning;
   the current app has explicit org creation (`POST /api/v1/organizations`).
6. `docs/PRD.md` mentions `flag_env_state` vs `targeting_rules` — current
   models match; but the PRD's `Flag.default_value` was dropped
   (`migrations/003_enable_all.sql`) and `Flag.archived` dropped in
   `004_drop_flag_archived.sql`.

**Recommendation for the paper**: cite the current code paths and the current
`AGENTS.md`, and describe the semantics in §6 (which are the current, tested
behavior).

### 12.4 Concrete behavior examples (from this session)

- `get_user_bucket("ai-assistant", "user_1") = 78` (mmh3 raw −57084918 →
  masked 4237882378 → `4237882378 % 100 = 78`).
- With percentage 50 and no rules: `user_1` (bucket 78) →
  `PERCENTAGE_OUTSIDE_ROLLOUT`, value `False`; raising to 79 flips them inside
  (`PERCENTAGE_ROLLOUT`, value `True`) — no other user changes (monotonicity).
- Bootstrap example body: `{"env": "prod", "version": 7, "flags": {"ai-assistant":
  {"key": "ai-assistant", "enabled": true, "enableAll": false, "percentage": 25,
  "rules": [{"id": "<uuid>", "priority": 0, "conditions":
  [{"attr": "email", "op": "ends_with", "value": "@acme.com"}], "serve": true}]}}}`.

### 13. Future Scope (not yet implemented)

- Real-time propagation (SSE/WebSockets/polling fanout) — explicitly out of
  scope in current docs; the SDK instead reads conditionally per check.
- RBAC/SSO/SAML, multivariate experiments + analytics, flag scheduling/expiry,
  flag dependencies, mobile/edge SDKs (OpenFeature integration), Terraform,
  multi-region HA, SLA/SOC2 compliance, backups.
- SDK disk cache (currently in-memory only), optional auto-refresh with
  `start_auto_refresh` for `refresh_on_evaluate=False` users.
- SDK in a second language (TypeScript/JS SDK not in tree — only Python SDK).
- Frontend: drag-and-drop rule reordering (current: move-up/move-down), rule
  priority editing via reorder endpoint only.
- Migration runner: startup `create_all()` covers fresh DBs; live DB upgrades
  rely on the four manual SQL scripts in `backend/migrations/` (`001–004`).

### 14. Research Contributions

Legend: claims marked **(verified)** are observable in the current tree/tests;
claims marked **(inferred)** are opinions/analysis, not claims of novelty in the
new sense.

1. **A differential parity architecture between server and SDK evaluators**
   (**verified**: `app/services/evaluator.py` ↔ `catalyst_sdk/evaluator.py`,
   fuzzed by `backend/tests/test_sdk_parity.py` — 5000-pair bucket parity, 13
   operators × attrs × values matrix parity, 3000-case whole-flag fuzz
   requiring identical `(value, reason, rule_id)`). This makes "the SDK mirrors
   the server" an enforced invariant rather than a documentation promise.
2. **Version-validated snapshot caching with ETag/304 and single-invalidation
   hooks** (**verified**: `Environment.version` as the ETag source,
   `bump_environment_versions()` called from every snapshot-mutating endpoint,
   Redis degradation as a slowdown-not-outage).
3. **Deterministic Murmur3 sticky bucketing with monotone-increase semantics**
   (**verified**: `bucket < percentage`; tests in `test_evaluator.py` and
   `test_api.py` covering "rollout monotonicity").
4. **The "rules partition + percentage" decision model**: matched users outside
   the bucket receive the opposite of the rule's value so the rule set and
   percentage partition the population exactly — with reason codes
   (`RULE_OUTSIDE_ROLLOUT` vs `RULE_AND_ROLLOUT` vs `PERCENTAGE_*`) as
   observability primitives for an operator debugging a rollout
   (`evaluator.py:127-136`).
5. **API-key lifecycle of delete-not-revoke with audit-trail-as-record**
   (ADR-002, verified in code and `test_api_keys.py`).
6. **Accessibility/usability of the management plane**: a 5 s poll + debounced
   rollout slider (one PATCH per drag), advisory match previews, collapsed
   disclosures with `aria-expanded`, clipboard copy that reports success only if
   the copy happened (**inferred** novelty for an IEEE short paper: a small set
   of UX invariants like these may be novel at the implementation level).
7. **Fail-closed SDK client**: evaluation resolves to `false` on read failures
   and holds off retries with `failure_backoff`, while an explicit `refresh()`
   still raises for a rejected key (ADR-001 + client.py).
8. **Weaknesses/risks (honest discussion)** (**inferred**, standard for the
   section): the paper can honestly note the MVP gaps in §13 — e.g., the 5 s
   frontend poll instead of push, fetch-on-load semantics for SDK consumers,
   no RBAC (all owners have full access within an org), API-key read-only-ness
   (no SDK writes), and the process-local auth rate limiter not scaling to
   multi-process deployments.

---

*End of report.*
