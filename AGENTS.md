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

## Project Structure

```text
catalyst/
├── backend/
│   ├── app/
│   │   ├── api/v1/          # auth, health, organizations, projects, flags, evaluate, bootstrap, audit + shared deps
│   │   ├── core/             # DB, Redis, settings, security/password/JWT helpers
│   │   ├── models/           # SQLAlchemy data models
│   │   ├── schemas/          # Pydantic request/response schemas
│   │   ├── services/         # evaluator, environment lifecycle/versioning, targeting rules, API keys
│   │   └── main.py           # FastAPI application entry point
│   ├── migrations/           # documented one-time SQL transition for pre-auth Phase 1 DBs
│   ├── tests/                # pytest suite (self-contained, SQLite-backed)
│   └── pyproject.toml
│
├── frontend/
│   └── src/
│       ├── auth/              # AuthContext, protected/public route wrappers
│       ├── components/       # shell, sidebar, flag controls, rule builder, environment UI
│       ├── lib/               # attribute catalogue + operator/coercion/preview helpers
│       ├── pages/             # landing, onboarding, org/project, auth and future tabs
│       ├── workspace/         # WorkspaceContext and useProject project-data hook
│       ├── App.tsx            # React Router route table
│       ├── api.ts             # typed, auth-aware API client with refresh/retry
│       └── main.tsx           # BrowserRouter + AuthProvider entry point
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
* **Redis** is the async caching layer with connection retry and health checks.
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
* **Targeting Rules:** evaluates user attributes against configured conditions, first match by ascending `priority` wins.
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

* `/bootstrap` provides the full SDK snapshot for a **project environment**.
* Supports **ETag-based conditional requests**; matching `If-None-Match` requests return `304 Not Modified` with the ETag echoed back.
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
* `App.tsx` is a route table: public landing/auth routes, protected `/app/**`, nested project routes, and future-phase placeholders.
* `AuthContext` restores an in-memory access token from a localStorage refresh token, exposes login/register/logout, and redirects protected routes to `/login`.
* `api.ts` attaches bearer tokens, shares a single refresh request, retries protected requests once after a `401`, and emits an auth-expired event when refresh fails. Access tokens stay in memory; refresh tokens use localStorage as a documented MVP tradeoff (not httpOnly).
* `WorkspaceContext` owns authenticated organization/project summaries, last-valid organization persistence, and organization/project creation.
* `useProject(projectId)` owns flags, environments, active environment/query state, polling, playground evaluation (with context attributes), and flag/environment/rule mutations.
* Persistent `AppShell`/`Sidebar` provides organization switching and project navigation. The global header contains only Catalyst branding, health status, and the user menu; organization/project/environment navigation lives in the sidebar/project header.
* Extracted reusable components include `Sidebar`, `FlagCard`, `KillSwitchButton`, `RolloutSlider`, `RuleBuilder`, `EvalPlayground`, and `EnvBadge`, plus auth/layout/flag-creation components.
* Rule conditions are built by picking from the attribute catalogue rather than typed: the attribute is a grouped select, the operator list is filtered per attribute, and the value control is derived from the attribute's kind (boolean toggle, enum select, numeric input, or token chips for `in`/`not_in`). `RuleBuilder` also renders a live match preview of the whole rule chain against the playground context.
* `frontend/src/lib/targeting.ts` owns the operator catalogue, the shared value coercion used by both rule conditions and playground attributes, list-token splitting/joining, draft validation, and attribute-input parsing (`key=value` lines or JSON).
* `frontend/src/lib/attributeCatalog.ts` owns the preset attribute catalogue (grouped, with value kind, sensible operators, enum options, and example values) and the client-side mirror of the evaluator (`previewConditionMatch` / `previewRuleMatch`) that powers the builder's match preview. The server remains the source of truth for what is actually served; the preview is advisory only.
* Existing feature flag functionality is preserved on the new pages: kill switch, rollout slider, evaluation playground, flag creation slide-over, custom environment management, and cache version display.

## Local Infrastructure

Docker Compose provides:

* **PostgreSQL 16 Alpine** → `:5432`
* **Redis 7 Alpine** → `:6379`
* Both services have health checks and persistent volumes.

Environment configuration is provided through `.env.example`, including JWT secret and expiry settings.

## Development Commands

```bash
# Start PostgreSQL + Redis
make up

# Start FastAPI backend
make dev-api

# Start React frontend
make dev-web

# Run backend tests
make test
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
* Registration/login/refresh/me, password validation/hashing, auth rate limiting
* Cross-user organization/project/flag authorization and audit attribution
* API Key management (creation, listing, revocation)
* SDK authentication via X-SDK-Key header
* Project-scoped SDK access to /bootstrap and /evaluate endpoints

The suite reports **39 tests passing**.

Frontend checks:

```bash
cd frontend
npm run test       # routing, auth-aware API client, targeting helpers, and rule builder Vitest tests
npm run lint
npm run build
```

## Continuous Integration (CI)

Automated on pull requests targeting `main` and pushes to `main` via `.github/workflows/ci.yml`:

* **`backend-tests`**: Runs on Python 3.12 with `uv` (`uv run pytest` - all 39 SQLite-backed unit and integration tests).
* **`frontend-checks`**: Runs on Node 22 (`npm ci`, `npm run test`, `npm run lint`, `npm run build`).

