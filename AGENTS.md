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
│   │   ├── api/v1/          # Versioned API routes
│   │   ├── core/             # DB + Redis configuration
│   │   ├── models/           # SQLAlchemy data models
│   │   ├── services/         # Business logic / evaluation engine
│   │   └── main.py           # FastAPI application entry point
│   ├── tests/
│   └── pyproject.toml
│
├── frontend/
│   └── src/
│       └── App.tsx           # Feature flag management dashboard
│
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
* API routes are versioned under `backend/app/api/v1/`.
* Business logic for feature flag evaluation is isolated in `services/evaluator.py`.

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
* `GET /api/v1/flags` — List flags
* `POST /api/v1/flags` — Create flag
* `PATCH /api/v1/flags/{key}/environments/{env}` — Update environment state / rollout / kill switch
* `POST /api/v1/evaluate` — Evaluate a flag
* `POST /api/v1/batch-evaluate` — Batch flag evaluation
* `GET /api/v1/bootstrap` — SDK configuration snapshot
* `GET /api/v1/audit` — Audit log

### Bootstrap / Caching

* `/bootstrap` provides the full SDK snapshot for an environment.
* Supports **ETag-based conditional requests**.
* Matching `If-None-Match` requests return `304 Not Modified`.

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
* Design tokens are defined in `frontend/src/index.css`; component styles in `frontend/src/App.css`.

## Frontend Architecture

* Built with **React + Vite + TypeScript**.
* Main dashboard is implemented in `frontend/src/App.tsx`.
* Supports:

  * `DEV / STAGING / PROD` environment switching
  * PostgreSQL and Redis health indicators
  * Emergency Kill Switch
  * Percentage/canary rollout slider
  * In-dashboard flag evaluation playground
  * Feature flag creation

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

Current initialization tests cover:

* API health/root response
* Deterministic sticky rollout hashing
* Emergency Kill Switch behavior
* Targeting rule evaluation

The initialization walkthrough reports **5 tests passing**.
