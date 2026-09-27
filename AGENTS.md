**IMPORTANT**: **Whenever any important or major change is made, update this `AGENTS.md` file** to keep the codebase overview current.

# GitHub Workflow

Repository: `https://github.com/VijeshVS/catalyst`

This workflow is triggered **only when the user asks to push code to GitHub**.

1. **Create a new branch** for the finalized changes using a descriptive feature/fix name. Never push directly to `main`.
2. **Fetch the latest `main`** and check the new branch for conflicts with `main`.
3. **Resolve all conflicts** before proceeding. Do not create the PR until the branch is conflict-free.
4. **Review and validate the changes**, then commit them using **Conventional Commits** with an appropriate scope, for example:
   * `feat(backend): add user authentication`
   * `fix(frontend): resolve login validation issue`
   * `feat(docs): add API documentation`
   * `refactor(database): optimize query`
   * `chore(deps): update dependencies`
5. **Push the new branch** to GitHub.
6. **Create a Pull Request** from the new branch into `main`.
7. **Never push directly to `main`**, even if the user asks to push the code.

# Catalyst — Codebase Architecture

## Tech Stack

* **Backend:** FastAPI + Python 3.12
* **Python Package Manager:** `uv`
* **Database:** PostgreSQL 16
* **ORM:** SQLAlchemy 2.0 (async)
* **DB Driver:** `asyncpg`
* **Cache:** Redis 7
* **Authentication:** Passlib bcrypt + python-jose[cryptography]
* **Frontend:** React 19 + Vite + TypeScript
* **Client routing:** React Router v6
* **Infrastructure:** Docker Compose
* **API:** REST, versioned under `/api/v1`
* **SDK:** `sdk-catalyst` (import name `catalyst_sdk`) — standalone Python client, published to PyPI from `packages/catalyst-python-sdk`

## Project Structure

```text
catalyst/
├── render.yaml              # Render blueprint (API service; no DB, see Deployment)
├── backend/
│   ├── app/
│   │   ├── api/v1/          # auth, health, organizations, projects, flags, evaluate, bootstrap, audit + shared deps
│   │   ├── core/             # DB, Redis, settings, security/password/JWT helpers
│   │   ├── models/           # SQLAlchemy data models
│   │   ├── schemas/          # Pydantic request/response schemas
│   │   ├── services/         # evaluator, environment lifecycle/versioning, cached snapshots, targeting rules, API keys
│   │   └── main.py           # FastAPI application entry point
│   ├── migrations/           # documented one-time SQL transition for pre-auth Phase 1 DBs
│   ├── tests/                # pytest suite (self-contained, SQLite-backed)
│   └── pyproject.toml
│
├── packages/
│   └── catalyst-python-sdk/
│       ├── src/catalyst_sdk/   # client, evaluator, hashing, snapshot, transport
│       ├── tests/              # SDK suite (self-contained, no network)
│       └── examples/           # runnable FastAPI demo
│
├── frontend/
│   └── src/
│       ├── auth/              # AuthContext, protected/public route wrappers
│       ├── components/       # shell, sidebar, flag controls, rule builder, environment UI
│       ├── lib/               # attribute catalogue + operator/coercion/preview helpers
│       ├── pages/             # landing, SDK docs (/docs), onboarding, org/project, auth tabs
│       ├── workspace/         # WorkspaceContext and useProject project-data hook
│       ├── App.tsx            # React Router route table
│       ├── api.ts             # typed, auth-aware API client with refresh/retry
│       └── main.tsx           # BrowserRouter + AuthProvider entry point
│
├── visual/                   # Source-backed interactive diagrams (Archify)
│   ├── index.html            # generated hub with navigation
│   ├── <slug>.html           # generated page per diagram
│   ├── artifacts/*.html      # delivered, frozen Archify artifacts
│   ├── sources/*.json        # typed Archify IR, the editable source of truth
│   └── build-site.mjs        # regenerates the hub and the pages
│
├── backend/migrations/001_auth_ownership.sql
├── docker-compose.yml        # PostgreSQL + Redis
├── .env.example              # Environment configuration, including JWT settings
├── Makefile                  # Development commands
└── .gitignore / .dockerignore
```

## Backend Architecture

* **FastAPI** application with an async lifespan for database table verification and Redis initialization.
* **SQLAlchemy 2.0 async** is used for PostgreSQL access through `asyncpg`.
* **Redis** is the async caching layer with connection retry and health checks. `core/cache.py` owns the connection lifecycle *and* the JSON cache helpers (`cache_get_json`, `cache_set_json`, `cache_delete`), all of which swallow Redis errors and report a miss, so a cache outage is a slowdown rather than an outage.
* **Environment snapshots are cached.** `services/snapshots.py` resolves the flags, states, and rules of one project environment, serving them from `catalyst:snapshot:<project>:<env>` when the cached entry's version matches the caller's `Environment.version` and rebuilding from PostgreSQL otherwise. `/bootstrap`, `/evaluate`, and `/batch-evaluate` all read through it and report which source answered in the `X-Catalyst-Cache` header.
* Invalidation is centralized in `services/environments.py::bump_environment_versions`, which bumps `Environment.version` *and* evicts the cached entry. A stale hit is therefore not something the cache can produce on its own; `SNAPSHOT_CACHE_TTL` (default 60s) is only a backstop for a mutation that forgot to bump, and `SNAPSHOT_CACHE_ENABLED` turns the layer off entirely.
* Database and Redis connectivity are exposed through `/healthz` and `/api/v1/healthz`.
* API routes are versioned under `backend/app/api/v1/`; shared lookup helpers (`get_current_user`, `get_organization_or_404`, `get_project_or_404`, `get_environment_or_404`) live in `api/v1/deps.py`.
* Business logic is isolated in `services/`: flag evaluation and the operator catalogue in `services/evaluator.py`, environment provisioning/state seeding/version invalidation in `services/environments.py`, targeting rule ordering/audit snapshots in `services/rules.py`, and SDK key issuance in `services/api_keys.py`.
* The existing startup `Base.metadata.create_all()` path remains for fresh development/test databases. It does not upgrade an existing database; startup now verifies the auth columns and fails with an actionable migration message when an old Phase 1 schema is detected. The explicit PostgreSQL transition is documented in `backend/migrations/README.md` and `001_auth_ownership.sql`.

### Authentication & Authorization

* `User` is an existing model adapted in place, not duplicated. It has a UUID/string UUID primary key, unique indexed email, full name, and a password hash exposed as the Python attribute `hashed_password` while retaining the Phase 1 physical `password_hash` column name for compatibility.
* `Organization.owner_id` is the ownership boundary. A user can own multiple organizations; organization/project/environment lookups require the current owner and return `404` for inaccessible resources to avoid ID enumeration.
* `core/security.py` contains bcrypt hashing/verification, typed JWT creation/decoding with `python-jose[cryptography]`, and a process-local auth-request limiter. JWT settings come from `JWT_SECRET`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, and `REFRESH_TOKEN_EXPIRE_DAYS`.
* Access tokens are short-lived (15 minutes by default); refresh tokens are long-lived (7 days by default). Refresh tokens are stateless/reusable until expiry in this MVP.
* Public routes: `/`, `/healthz`, `/api/v1/healthz`, `/api/v1/auth/register`, `/api/v1/auth/login`, and `/api/v1/auth/refresh`.
* Protected routes include organizations, projects/environments, flags, single/batch evaluation, bootstrap, audit, and `/api/v1/auth/me`.
* Authenticated mutations populate the legacy `AuditLog.actor` plus nullable `user_id` and `user_email` attribution fields.
* Passwords are at least 8 characters. Password hashes are never included in response schemas.

### Multi-Tenant Hierarchy

Organizations, projects, and environments are **explicitly managed** — there is no auto-provisioned default organization/project:

* `POST /api/v1/organizations` provisions an organization owned by the authenticated user; names are unique (409).
* Creating a project auto-provisions the standard `dev`, `staging`, `prod` environments.
* Custom environments can be created per project (lowercase identifier, e.g. `qa`). Creating one seeds `FlagEnvState` rows for every existing flag in the project.
* Creating a flag seeds a state row for every environment of its project.
* **Strict project scoping:** every flag/evaluation/bootstrap/audit endpoint requires a `project_id` query parameter (`422` when missing, `404` when unknown), and all queries filter by `Flag.project_id` / `AuditLog.project_id`. Environments must also belong to the project (`404` otherwise), so identical flag keys can coexist in different projects without leaking state, evaluation results, snapshots, or audit entries.

### Core Data Models

* `User`
* `Organization`
* `Project`
* `Environment`
* `Flag`
* `FlagEnvState`
* `TargetingRule`
* `ApiKey`
* `AuditLog`

### Feature Flag Evaluation

Evaluation follows the implemented evaluator logic:

* **Emergency Kill Switch:** immediately returns the configured default value.
* **Percentage Rollout:** deterministic Murmur3 hashing based on `flag_key:user_id`.
* **Targeting Rules:** evaluates user attributes against configured conditions, first match by ascending `priority` wins. `evaluate_flag()` sorts rules itself rather than trusting the caller, so the precedence contract holds for any input order and matches the Python SDK exactly.
* Rollouts are sticky/deterministic for the same flag and evaluation user.

### Rule-Based Targeting (Phase 3)

* `TargetingRule` is **environment-scoped** (`flag_id` + `env`), ordered by `priority` where `0` is the highest. Priorities are kept dense (`0..n-1`) on create-append, reorder, and delete.
* Conditions are `{"attr", "op", "value"}` and are **ANDed** within a rule. A rule must carry 1-25 conditions; an empty condition list is an unconditional match and is rejected by the API.
* Supported operators (canonical names; `eq`/`neq`/`gt`/`gte`/`lt`/`lte`/`notExists` are accepted and normalized on write): `equals`, `not_equals`, `in`, `not_in`, `contains`, `starts_with`, `ends_with`, `greater_than`, `greater_than_or_equal`, `less_than`, `less_than_or_equal`, `exists`, `not_exists`. `in`/`not_in` accept a list or a comma-separated string; `exists`/`not_exists` ignore `value`.
* A missing attribute makes a condition false (the rule safely skips); `equals` is case-sensitive while `contains`/`starts_with`/`ends_with` are not.
* `RuleCondition`/`RuleCreate`/`RuleUpdate` live in `app/schemas/schemas.py`; ordering and audit helpers live in `app/services/rules.py`.
* Every rule mutation bumps only the mutated environment's `Environment.version` (busting that ETag only) and writes an `AuditLog` action of `rule.created`, `rule.updated`, `rule.deleted`, or `rule.reordered`.
* The `conditions_json` column is exposed as `conditions` on every wire format (flag list, rule CRUD, `/evaluate`, `/bootstrap`).

### Important APIs

* `GET /healthz` — DB + Redis health
* `POST /api/v1/auth/register` — Create account and return token pair
* `POST /api/v1/auth/login` — JSON login and token pair
* `POST /api/v1/auth/refresh` — Exchange refresh token
* `GET /api/v1/auth/me` — Current sanitized user profile
* `POST /api/v1/organizations` — Create owned organization
* `GET /api/v1/organizations` — List owned organizations (with projects, environments, flag summaries)
* `GET /api/v1/organizations/{org_id}` — Owned organization details
* `POST /api/v1/organizations/{org_id}/projects` — Create project (auto-provisions `dev`/`staging`/`prod`)
* `GET /api/v1/projects/{project_id}/environments` — List project environments
* `POST /api/v1/projects/{project_id}/environments` — Create custom environment
* `GET /api/v1/flags?project_id=` — List flags (owned project scope)
* `POST /api/v1/flags?project_id=` — Create flag
* `GET /api/v1/flags/{key}?project_id=` — Get flag
* `PATCH /api/v1/flags/{key}/environments/{env}?project_id=` — Update environment state / rollout / kill switch
* `GET /api/v1/flags/{key}/environments/{env}/rules?project_id=` — List targeting rules in priority order
* `POST /api/v1/flags/{key}/environments/{env}/rules?project_id=` — Create targeting rule
* `PUT /api/v1/flags/{key}/environments/{env}/rules/reorder?project_id=` — Re-order rules, renormalize `0..n-1`
* `PUT /api/v1/flags/{key}/environments/{env}/rules/{rule_id}?project_id=` — Update conditions / serve value / priority
* `DELETE /api/v1/flags/{key}/environments/{env}/rules/{rule_id}?project_id=` — Delete rule and close the priority gap
* `POST /api/v1/evaluate?project_id=` — Evaluate a flag
* `POST /api/v1/batch-evaluate?project_id=` — Batch flag evaluation
* `GET /api/v1/bootstrap?project_id=&env=` — SDK configuration snapshot (supports Bearer or X-SDK-Key)
* `GET /api/v1/audit?project_id=` — Audit log (owned project scope, attributed user fields)

### API Key Management (Phase 2)

* **API Key Format**: `cp_<env>_<random32>` (e.g., `cp_prod_a1b2c3d4e5f6g7h8i9j0k1`)
* **Security**: Keys are hashed with SHA-256 and stored in the database; raw keys are returned once upon creation
* **Authentication**: SDK clients send the full key in the `X-SDK-Key` header
* **Project-scoped Access**: SDK keys can only access resources within their project

* `POST /api/v1/projects/{project_id}/keys` — Create API key (returns raw key once)
* `GET /api/v1/projects/{project_id}/keys` — List all API keys for a project
* `DELETE /api/v1/projects/{project_id}/keys/{key_id}` — Revoke an API key

### Bootstrap / Caching

* `/bootstrap` provides the full SDK snapshot for a **project environment**, read through the Redis snapshot cache.
* Supports **ETag-based conditional requests**; matching `If-None-Match` requests return `304 Not Modified` with the ETag echoed back, before the snapshot body is loaded at all.
* The ETag derives from the project environment's `Environment.version`, which is incremented by every mutation that changes that snapshot (flag creation, rollout or kill-switch updates). Mutations in one project never invalidate another project's ETag.
* Authenticated bootstrap responses use private cache headers.
* **SDK Authentication**: The `/bootstrap` and `/evaluate` endpoints accept either a Bearer token (for users) or an `X-SDK-Key` header (for SDK clients). SDK keys are scoped to their project and can only access resources within that project.

## Frontend Design System

* **Theme**: Retro Black & Gold aesthetic.
* **Fonts**: `Playfair Display` (headings, stat values, brand) + `IBM Plex Mono` (all UI text, labels, code badges).
* **Palette** (CSS custom properties in `index.css`):
  * `--gold-primary: #F5C518` — primary brand accent
  * `--gold-bright: #FFD84D` — hover highlights
  * `--amber-accent: #D4862A` — secondary gradient
  * `--bg-primary: #0E0E0E` — page background
  * `--text-primary: #F0E6C8` — warm parchment text
  * `--danger-bright: #E74C3C` — kill switch / error states
  * `--success: #27AE60` — live / healthy states
* **Key visual patterns**:
  * Glassmorphism dark cards with gold `border-color` tokens
  * Left 3px gold vertical accent strip on flag cards
  * Gold gradient CTA buttons (dark text)
  * Pulsing crimson glow on kill switch when active
  * Custom gold range slider (track fill + glow thumb)
  * Dashed gold border playground boxes
  * Subtle radial gold shimmer on body background
* Design tokens are defined in `frontend/src/index.css`; component styles are in `frontend/src/App.css`.

## Frontend Architecture

* Built with **React + Vite + TypeScript** and **React Router v6**.
* `main.tsx` wraps the route tree with `BrowserRouter` and `AuthProvider`.
* `App.tsx` is a route table: public landing/auth routes, the public SDK documentation page (`/docs`), protected `/app/**`, nested project routes, and future-phase placeholders.
* `DocsPage.tsx` is the in-app SDK reference at `/docs` (public, linked from the landing page hero and footer). It documents the Python SDK with 14 sections, copyable code blocks (`CodeBlock.tsx`), and configuration / operator / error tables, and has a **search box** in the sidebar (Go button, match count, Escape to clear) that filters the table of contents. Content is kept in sync with the SDK README by hand.
* `AuthContext` restores an in-memory access token from a localStorage refresh token, exposes login/register/logout, and redirects protected routes to `/login`.
* `api.ts` attaches bearer tokens, shares a single refresh request, retries protected requests once after a `401`, and emits an auth-expired event when refresh fails. Access tokens stay in memory; refresh tokens use localStorage as a documented MVP tradeoff (not httpOnly).
* `WorkspaceContext` owns authenticated organization/project summaries, last-valid organization persistence, and organization/project creation.
* `useProject(projectId)` owns flags, environments, active environment/query state, polling, playground evaluation (with context attributes), and flag/environment/rule mutations.
* Persistent `AppShell`/`Sidebar` provides organization switching and project navigation, plus a Documentation link out to the public `/docs` SDK reference so it is reachable from every `/app/**` route. The global header contains only Catalyst branding, health status, and the user menu; organization/project/environment navigation lives in the sidebar/project header.
* Extracted reusable components include `Sidebar`, `FlagCard`, `KillSwitchButton`, `RolloutSlider`, `RuleBuilder`, `EvalPlayground`, and `EnvBadge`, plus auth/layout/flag-creation components.
* Rule conditions are built by picking from the attribute catalogue rather than typed: the attribute is a grouped select, the operator list is filtered per attribute, and the value control is derived from the attribute's kind (boolean toggle, enum select, numeric input, or token chips for `in`/`not_in`). `RuleBuilder` also renders a live match preview of the whole rule chain against the playground context.
* `frontend/src/lib/docsSearch.ts` owns the docs search index and matching (`searchSections`, `normalizeQuery`, `matchCount`) over each section's title, summary, and keywords, so the rules are unit tested without rendering the page.
* `RolloutSlider` is a debounced control: the thumb moves on a local draft, the mutation is committed after `debounceMs` (default 400ms) and flushed immediately on pointer release, key release, or blur, so a drag is one `PATCH` instead of one per pixel. It shows a "saving" indicator while an edit is in flight, and `useProject.updateRollout` applies the value optimistically under a per-flag/per-environment sequence number so a slow response cannot overwrite a newer edit.
* `frontend/src/lib/targeting.ts` owns the operator catalogue, the shared value coercion used by both rule conditions and playground attributes, list-token splitting/joining, draft validation, and attribute-input parsing (`key=value` lines or JSON).
* `frontend/src/lib/attributeCatalog.ts` owns the preset attribute catalogue (grouped, with value kind, sensible operators, enum options, and example values) and the client-side mirror of the evaluator (`previewConditionMatch` / `previewRuleMatch`) that powers the builder's match preview. The server remains the source of truth for what is actually served; the preview is advisory only.
* Existing feature flag functionality is preserved on the new pages: kill switch, rollout slider, evaluation playground, flag creation slide-over, custom environment management, and cache version display.

## Python SDK (`packages/catalyst-python-sdk`)

* Distribution is **`sdk-catalyst`** (import name `catalyst_sdk`). The `catalyst-sdk` PyPI name is taken by an unrelated project, so the distribution name differs from the import name. Hatchling build, ships `py.typed`, PEP 639 `license = "MIT"` with a bundled `LICENSE`. Only runtime dependency is `httpx`.
* Releases are automated by `.github/workflows/publish-sdk.yml`: it runs on pushes to `main` that touch the package, runs the SDK and parity suites, then publishes if the `pyproject.toml` version is new on PyPI. Auth is PyPI Trusted Publishing (OIDC), so no token is stored in the repo. To release, bump the version and merge.
* `hashing.py` vendors MurmurHash3 x86_32 so sticky bucketing needs no native extension. It is verified against the real `mmh3` library and against the server's `get_user_bucket()`.
* `evaluator.py` mirrors `app/services/evaluator.py`: kill switch → rules by ascending priority → percentage rollout → default. Operator aliases (`eq`, `gt`, `notExists`, …) are accepted and normalized.
* `client.py` **reads as it evaluates**: construction performs no I/O, and every check makes a conditional request before deciding locally. This is what makes a dashboard toggle visible on the next check. Snapshot swaps are a single attribute assignment, so readers always see a consistent view.
* Reads are conditional (`If-None-Match`), so an unchanged environment costs a `304` with no body, and the server answers them from Redis. The check itself is still sub-millisecond; `test_evaluation_is_sub_millisecond` asserts the decision cost with `refresh_on_evaluate=False`.
* `host` defaults to the deployed API (`transport.DEFAULT_HOST`), overridable per client with `host=` or per process with `CATALYST_HOST`; the argument beats the variable. An explicitly empty `host` is a `ConfigurationError` rather than a silent fallback.
* Concurrency and failure behaviour on the read path: a `_read_lock` makes concurrent checks collapse into a single request (single-flight), a failed read sets a `failure_backoff` window (default 5s) so an unreachable API costs one timeout per window instead of one per check, and a first read that fails falls back to the disk cache before `default_value`.
* `refresh_on_evaluate=False` restores in-memory-only evaluation for callers who want no I/O on the request path; `start_auto_refresh(interval, on_error)` then becomes the way to stay current. `offline=True` implies it.
* Failure policy: an explicit `refresh()` raises `AuthorizationError`, since a rejected key will not fix itself. The implicit read inside `evaluate()`/`is_enabled()` absorbs it, because a flag check inside someone else's request must not become a 500. `raise_on_error=True` makes reads propagate too.
* The last good snapshot is persisted under `~/.cache/catalyst` (`CATALYST_CACHE_DIR` overrides) with an atomic write-then-rename, so a cold start survives an unreachable API. `cache_path=False` disables it.
* `backend/tests/test_sdk_parity.py` is a **differential suite**: it fuzzes the server evaluator and the SDK evaluator with identical inputs and requires identical values, reasons, and rule ids. Run it with the backend suite. Any change to evaluation semantics on either side should keep this green.

## Local Infrastructure

Docker Compose provides:

* **PostgreSQL 16 Alpine** → `:5432`
* **Redis 7 Alpine** → `:6379`
* Both services have health checks and persistent volumes.

Environment configuration is provided through `.env.example`, including JWT secret and expiry settings.

## Deployment

The backend runs on **Render**, the frontend on **Vercel**, and the datastores sit on **Neon**
(Postgres) and **Render Key Value** (Redis). Both providers auto-deploy from `main`.

| Piece | Where | Notes |
|---|---|---|
| API | Render web service `catalyst-api` (free, `oregon`) | Native Python, no Docker, built with `uv` |
| Frontend | Vercel project `catalyst-dashboard` | `rootDirectory: frontend`, production branch `main` |
| Database | Neon project `catalyst` (`aws-us-west-2`, PG 16.15) | 9 tables, created by the app's startup `create_all()` |
| Cache | Render Key Value `catalyst-cache` (free, 25 MB) | In-memory only; empty after every restart |

### Gotchas that will bite you

* **Neon's `sslmode=require` breaks asyncpg.** The app uses `postgresql+asyncpg://`, and that driver
  rejects `sslmode` with `TypeError: connect() got an unexpected keyword argument 'sslmode'`. Strip
  it from the connection string before setting `DATABASE_URL`.
* **The Redis internal URL carries no password, by design.** `redis://<resource-id>:6379` is
  reachable only over Render's private network (`ipAllowList: []` blocks external entirely). It will
  not resolve from a laptop, so the SDK and the Flask demo cannot use that cache — point them at
  local Redis instead. The API is in the same region as the Key Value, which is what makes internal
  DNS resolve at all.
* **Render's free Postgres is deliberately not used.** It expires 30 days after creation and then
  deletes the data, so `render.yaml` declares no database and `DATABASE_URL` points at Neon.
* **The Render API's env-var path takes the KEY, not the id:**
  `PUT /v1/services/{id}/env-vars/{KEY}`. Passing an id silently *creates* a junk variable instead of
  updating. Delete junk with `DELETE /v1/services/{id}/env-vars/{KEY}`.
* **The frontend needs `VITE_API_BASE_URL` at build time.** `api.ts` falls back to the relative
  `/api/v1` used by the Vite dev proxy, which would resolve against the Vercel origin and 404.
  `frontend/vercel.json` supplies the SPA rewrite that keeps `/docs` and `/app/**` working on a hard
  refresh.
* `CORS_ORIGINS` on the API must list the deployed frontend origin, or every browser request is
  blocked.

### Free-tier limits (demo environment, not production)

* Render spins down after 15 minutes idle; a cold start takes about a minute, and Neon suspends when
  idle, so cold starts can stack.
* Neither service has backups.
* `JWT_SECRET` and `SECRET_KEY` are set with `generateValue: true` in `render.yaml`. Never deploy
  the shipped `change-this-jwt-secret-in-production` default to a public host — it would let anyone
  forge access tokens.

### Local data is not production data

Local Docker Postgres and Neon are entirely separate databases. An SDK key or project created against
`localhost:8000` does **not** exist in production, and `/api/v1/bootstrap` will answer
`404 API key not found`. To use the SDK against production, create the project and mint the key from
the production dashboard, since SDK keys are read-only and cannot be created over the API.

## Visual Documentation (`visual/`)

* Seven interactive, source-backed diagrams generated with [Archify](https://github.com/tt-a1i/archify): the runtime architecture (architecture), the SDK conditional read and the toggle-propagation chain (sequence), tenant onboarding and the SDK release pipeline (workflow), the SDK read-path state machine (lifecycle), and the evaluation PII boundary (dataflow).
* `visual/sources/*.json` is the **editable source of truth**; `visual/artifacts/*.html` is generated output. Edit the JSON, never the HTML — a delivered artifact is a frozen byte-for-byte render with a SHA-256 receipt.
* Architecture nodes carry `SRC n` badges that resolve to a `file:line` in this repository, pinned to one commit. **A diagram claim that is not true of the code is a bug in the diagram, not a bug in the code.**
* The site shell (`index.html`, `<slug>.html`, `assets/site.css`) is generated by `visual/build-site.mjs` from a manifest of editorial copy. Change the copy there, not in the generated HTML.
* Regeneration loop: `zsh visual/check.sh` validates all sources at `showcase` quality, `zsh visual/deliver.sh` renders and commits the artifacts, `zsh visual/verify.sh` collects bounded desktop browser evidence, `node visual/build-site.mjs` regenerates the pages.
* `deliver` is the only acceptance command. A non-zero exit is a failure and must never be described as success. `visual-check` is separate browser evidence, and a diagram reading well is a separate, human judgement.
* All seven hold 9/9 showcase checks with zero composition errors. Six of seven also fit a 1440x900 viewport with no scrolling; the SDK lifecycle overflows by 16px because the lifecycle renderer reserves three fixed bands and refuses a shorter `viewBox`. That trade-off is documented in `visual/README.md` — do not "fix" it by shrinking node text below the 6px readability floor.
* Editing one diagram must not disturb the others. Archify geometry controls are per-diagram, and a change that fixes a corridor collision in one source routinely creates a new one in another.

## Development Commands

```bash
# Start PostgreSQL + Redis
make up

# Start FastAPI backend
make dev-api

# Start React frontend
make dev-web

# Run backend tests (includes the server/SDK parity suite)
make test

# Run SDK tests
make test-sdk

# Build the SDK wheel
make build-sdk
```

Default development ports:

* Backend → `8000`
* Frontend → `5173`
* PostgreSQL → `5432`
* Redis → `6379`

## Testing

Backend tests are run using:

```bash
cd backend && uv run pytest
```

The suite is **self-contained**: `tests/conftest.py` points the app at a temporary SQLite database (`aiosqlite`, dev dependency) before any app module is imported, so no PostgreSQL/Redis instance is needed and the development database is never touched. The default API fixture registers an authenticated account; `anon_client` is available for auth/protection tests.

Current backend coverage includes:

* API health/root response
* Deterministic sticky rollout hashing
* Emergency Kill Switch behavior
* Targeting rule evaluation
* Targeting rule CRUD, condition validation, dense priority re-ordering, and cross-user/project/environment isolation
* Rule-driven evaluation precedence and environment-scoped cache invalidation on rule mutations
* Organization CRUD and project creation with auto-provisioned environments
* Custom environment management (validation, duplicates, seeding of flag states)
* Strict project scoping and project isolation (flags, evaluate, bootstrap, audit)
* Bootstrap ETag scoping and environment version invalidation (304 → 200 on mutation)
* Redis snapshot caching: cache hit/miss reporting, per-environment isolation, version-based invalidation on flag/state/rule mutations, `/evaluate` reading through the same cache, and degradation when Redis is absent, broken, or holding an undecodable value
* Registration/login/refresh/me, password validation/hashing, auth rate limiting
* Cross-user organization/project/flag authorization and audit attribution
* API Key management (creation, listing, revocation)
* SDK authentication via X-SDK-Key header
* Project-scoped SDK access to /bootstrap and /evaluate endpoints
* Server/SDK evaluation parity (differential fuzz over operators, precedence, and bucketing)

The suite reports **71 tests passing**.

The Python SDK has its own self-contained suite in `packages/catalyst-python-sdk`:

```bash
cd packages/catalyst-python-sdk && uv run --with pytest --with mmh3 pytest
```

It reports **87 tests passing** and needs no network or running services.

Frontend checks:

```bash
cd frontend
npm run test       # routing, auth-aware API client, targeting helpers, rule builder, rollout slider, and docs search Vitest tests
npm run lint
npm run build
```

## Continuous Integration (CI)

Automated on pull requests targeting `main` and pushes to `main` via `.github/workflows/ci.yml`:

* **`backend-tests`**: Runs on Python 3.12 with `uv` (`uv run pytest` - all SQLite-backed unit and integration tests, with a fake Redis standing in for the cache).
* **`frontend-checks`**: Runs on Node 22 (`npm ci`, `npm run test`, `npm run lint`, `npm run build`).
* **`sdk-tests`**: Runs on Python 3.12 — the SDK suite, a `uv build` wheel check, and the server/SDK parity suite inside the backend environment.
* **`Publish SDK`**: On pushes to `main` touching `packages/catalyst-python-sdk/**`, re-runs the SDK and parity suites and publishes to PyPI when the version is new. Requires a one-time Trusted Publisher config on pypi.org (owner `VijeshVS`, repo `catalyst`, workflow `publish-sdk.yml`, environment `pypi`).
* **`Render Deploy Status`**: On pushes to `main` (and manual dispatch) via `.github/workflows/render-deploy-status.yml`. Publishes the `render/deploy` commit status on the deployed SHA, plus the README badge. Requires the `RENDER_API_KEY` repository secret (an account API key, value starts with `rnd_`); `RENDER_SERVICE_ID` is an optional override, otherwise the service is found by name.
    * It runs on `main` only, **never on `pull_request`**. Render auto-deploys `main` only, so a PR branch has no Render deploy to report — a check there would describe main's deploy while appearing to describe the PR. Vercel shows a check on every PR because it builds a *preview* of the branch; Render's equivalent is a service preview, which is a deploy rather than a status. A PR-gating backend check does not exist, so nothing currently proves the API deploys or that `/healthz` returns `ok` against real Neon and Render Redis.
    * **Render has a build filter, so not every push to `main` deploys.** `render.yaml` declares `buildFilter.paths: backend/**`, so a docs- or frontend-only commit is correctly not deployed. The workflow mirrors that filter by reading the pushed commit's changed files from the GitHub API: a deploy-relevant push waits for the deploy of that exact SHA, and a non-deploy-relevant push instead reports the state of the deploy production is *actually running*. Reporting the live deploy rather than a blind success is deliberate — otherwise a still-broken deploy would be masked by a later docs commit.
    * A push to `main` races Render's own deploy trigger, so the deploy-relevant path polls up to 10 minutes for a deploy whose `commit.id` matches `github.sha`, then polls until it settles, posting `pending` once and a terminal state after. GitHub caps a commit's file list at 300 entries, so a commit at the cap is treated as deploy-relevant rather than risk a false "nothing to deploy".
    * An unrecognised Render status maps to `error`, never `success`, and a missing or rejected `RENDER_API_KEY` fails the run — the check is never allowed to pass while unconfigured.
    * The filter is duplicated in two places on purpose: `render.yaml` for Render, and the `DEPLOY_PATHS` variable in the workflow. They must be changed together, which both files say.
    * Every push shows **two** entries in the checks list, and both are needed. `Publish render/deploy status` is the Actions check run, which is created by the job itself and cannot be suppressed; `render/deploy` is the commit status the job writes. Keeping the Actions check is what makes a failure *visible* — if the workflow dies before posting (missing or rejected `RENDER_API_KEY`, cancelled, timed out) then `render/deploy` is never posted at all, so a commit would show no status rather than a red one. The job is named after the status it writes so the pair does not read as an accident.

