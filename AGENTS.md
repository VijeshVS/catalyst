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

* **Backend:** FastAPI + Python
* **Python Package Manager:** `uv`
* **Database:** PostgreSQL 16
* **ORM:** SQLAlchemy 2.0 (async)
* **DB Driver:** `asyncpg`
* **Cache:** Redis 7
* **Frontend:** React + Vite + TypeScript
* **Infrastructure:** Docker Compose
* **API:** REST, versioned under `/api/v1`

## Project Structure

```text
catalyst/
├── backend/
│   ├── app/
│   │   ├── api/v1/          # Versioned API routes (health, organizations, projects, flags, evaluate, bootstrap, audit) + shared deps
│   │   ├── core/             # DB + Redis configuration
│   │   ├── models/           # SQLAlchemy data models
│   │   ├── schemas/          # Pydantic request/response schemas
│   │   ├── services/         # Business logic (evaluator, environments)
│   │   └── main.py           # FastAPI application entry point
│   ├── tests/                # pytest suite (self-contained, SQLite-backed)
│   └── pyproject.toml
│
├── frontend/
│   └── src/
│       ├── App.tsx           # Feature flag dashboard + workspace navigation
│       └── api.ts            # Typed API client (project-scoped)

├── docker-compose.yml        # PostgreSQL + Redis
├── .env.example              # Environment configuration
├── Makefile                  # Development commands
└── .gitignore / .dockerignore
```

## Backend Architecture

* **FastAPI** application with an async lifespan for service initialization.
* **SQLAlchemy 2.0 async** is used for PostgreSQL access through `asyncpg`.
* **Redis** is used as the async caching layer with connection retry and health checks.
* Database and Redis connectivity are exposed through `/healthz`.
* API routes are versioned under `backend/app/api/v1/`; shared lookup helpers (`get_organization_or_404`, `get_project_or_404`, `get_environment_or_404`) live in `api/v1/deps.py`.
* Business logic is isolated in `services/`: flag evaluation in `services/evaluator.py`, environment provisioning/state seeding/version invalidation in `services/environments.py`.

### Multi-Tenant Hierarchy

Organizations, projects, and environments are **explicitly managed** — there is no
auto-provisioned default organization/project anymore:

* `POST /api/v1/organizations` provisions an organization; names are unique (409).
* Creating a project auto-provisions the standard `dev`, `staging`, `prod` environments.
* Custom environments can be created per project (lowercase identifier, e.g. `qa`).
  Creating one seeds `FlagEnvState` rows for every existing flag in the project.
* Creating a flag seeds a state row for every environment of its project.
* **Strict project scoping:** every flag/evaluation/bootstrap/audit endpoint requires a
  `project_id` query parameter (`422` when missing, `404` when unknown), and all queries
  filter by `Flag.project_id` / `AuditLog.project_id`. Environments must also belong to
  the project (`404` otherwise), so identical flag keys can coexist in different projects
  without leaking state, evaluation results, snapshots, or audit entries.

### Core Data Models

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
* **Targeting Rules:** evaluates user attributes against configured conditions.
* Rollouts are sticky/deterministic for the same flag and user.

### Important APIs

* `GET /healthz` — DB + Redis health
* `POST /api/v1/organizations` — Create organization
* `GET /api/v1/organizations` — List organizations (with projects & environments)
* `GET /api/v1/organizations/{org_id}` — Organization details
* `POST /api/v1/organizations/{org_id}/projects` — Create project (auto-provisions `dev`/`staging`/`prod`)
* `GET /api/v1/projects/{project_id}/environments` — List project environments
* `POST /api/v1/projects/{project_id}/environments` — Create custom environment
* `GET /api/v1/flags?project_id=` — List flags (project-scoped)
* `POST /api/v1/flags?project_id=` — Create flag
* `PATCH /api/v1/flags/{key}/environments/{env}?project_id=` — Update environment state / rollout / kill switch
* `POST /api/v1/evaluate?project_id=` — Evaluate a flag
* `POST /api/v1/batch-evaluate?project_id=` — Batch flag evaluation
* `GET /api/v1/bootstrap?project_id=&env=` — SDK configuration snapshot
* `GET /api/v1/audit?project_id=` — Audit log (project-scoped)

### Bootstrap / Caching

* `/bootstrap` provides the full SDK snapshot for a **project environment**.
* Supports **ETag-based conditional requests**; matching `If-None-Match` requests return
  `304 Not Modified` with the ETag echoed back.
* The ETag derives from the project environment's `Environment.version`, which is
  incremented by every mutation that changes that snapshot (flag creation, rollout or
  kill-switch updates). Mutations in one project never invalidate another project's ETag.

## Frontend Architecture

* Built with **React + Vite + TypeScript**.
* Main dashboard is implemented in `frontend/src/App.tsx`; the typed API client is `frontend/src/api.ts`.
* Supports:

  * **Workspace navigation:** organization & project dropdown switcher in the header
  * **New Project modal** showing the auto-created `dev` / `staging` / `prod` environment badges, plus a **New Organization** onboarding flow for empty state
  * **Environment management view** (per-project): lists environments with `auto-created` / `custom` badges and cache version, and creates custom environments
  * Dynamic environment switcher driven by the selected project's environments (custom environments included)
  * PostgreSQL and Redis health indicators
  * Emergency Kill Switch
  * Percentage/canary rollout slider
  * In-dashboard flag evaluation playground
  * Feature flag creation
  * All flag data calls are strictly scoped to the selected project

## Local Infrastructure

Docker Compose provides:

* **PostgreSQL 16 Alpine** → `:5432`
* **Redis 7 Alpine** → `:6379`
* Both services have health checks and persistent volumes.

Environment configuration is provided through `.env.example`.

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
uv run pytest
```

The suite is **self-contained**: `tests/conftest.py` points the app at a temporary SQLite
database (`aiosqlite`, dev dependency) before any app module is imported, so no
PostgreSQL/Redis instance is needed and the development database is never touched.

Current test coverage:

* API health/root response
* Deterministic sticky rollout hashing
* Emergency Kill Switch behavior
* Targeting rule evaluation
* Organization CRUD and project creation with auto-provisioned environments
* Custom environment management (validation, duplicates, seeding of flag states)
* Strict project scoping and project isolation (flags, evaluate, bootstrap, audit)
* Bootstrap ETag scoping and environment version invalidation (304 → 200 on mutation)

The suite reports **12 tests passing**.

Frontend checks:

```bash
cd frontend && npm run lint && npm run build
```
