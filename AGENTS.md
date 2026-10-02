# Catalyst

Repository: `https://github.com/VijeshVS/catalyst`

Feature flag service: FastAPI API, React dashboard, and a Python SDK. REST, versioned under `/api/v1`.

- **Update this file** whenever an important or major change is made.
- Keep the content here factual and terse; it describes the current state of the code, not history or rationale.

## GitHub Workflow

Applies when the user asks to push code to GitHub.

- Never push directly to `main`, even when explicitly asked.
- Create a descriptive feature/fix branch for the finalized changes.
- Fetch the latest `main` and confirm the branch is conflict-free before opening a PR.
- Commit using Conventional Commits: `<type>(<scope>): <description>`, e.g. `feat(backend): add user authentication`, `fix(frontend): resolve login validation issue`, `docs(redis): document cache TTLs`.
- Push the branch, then open a PR into `main`.
- PR title must be `release(<scope>): <description>` with a free-form scope (`backend`, `sdk`, `ci`, `visual`, …).
- PR body must not be empty. Both are enforced by the `PR Hygiene` workflow.

## Tech Stack

- **Backend:** FastAPI, Python 3.12, `uv`
- **Database:** PostgreSQL 16 via SQLAlchemy 2.0 async + `asyncpg`
- **Cache:** Redis 7
- **Auth:** Passlib bcrypt + `python-jose[cryptography]`
- **Frontend:** React 19, Vite, TypeScript, React Router v6
- **Local infra:** Docker Compose
- **SDK:** `sdk-catalyst` (import name `catalyst_sdk`), published to PyPI from `packages/catalyst-python-sdk`

## Project Structure

```text
catalyst/
├── render.yaml              # Render blueprint for the API service
├── backend/
│   ├── app/
│   │   ├── api/v1/          # auth, health, organizations, projects, flags, evaluate, bootstrap, audit, deps
│   │   ├── core/            # DB, Redis, settings, security/password/JWT
│   │   ├── models/          # SQLAlchemy models
│   │   ├── schemas/         # Pydantic request/response schemas
│   │   ├── services/        # evaluator, environments, snapshots, rules, api_keys
│   │   └── main.py          # FastAPI entry point
│   ├── migrations/          # one-time SQL for pre-auth databases
│   ├── tests/               # self-contained pytest suite (SQLite-backed)
│   └── pyproject.toml
├── packages/catalyst-python-sdk/
│   ├── src/catalyst_sdk/    # client, evaluator, hashing, snapshot, transport
│   ├── tests/
│   └── examples/
├── frontend/src/
│   ├── auth/                # AuthContext, protected/public route wrappers
│   ├── components/          # shell, sidebar, flag controls, rule builder, env UI
│   ├── lib/                 # targeting helpers, attribute catalogue, docs search
│   ├── pages/               # landing, /docs, onboarding, org/project, auth tabs
│   ├── workspace/           # WorkspaceContext, useProject
│   ├── App.tsx              # route table
│   ├── api.ts               # typed auth-aware client with refresh/retry
│   └── main.tsx             # BrowserRouter + AuthProvider
├── visual/                  # Archify diagrams (sources/*.json is the source of truth)
├── docker-compose.yml       # PostgreSQL + Redis
├── .env.example
└── Makefile
```

## Backend

- FastAPI app with an async lifespan for table verification and Redis init.
- Routes live in `app/api/v1/`; shared lookups (`get_current_user`, `get_organization_or_404`, `get_project_or_404`, `get_environment_or_404`) in `api/v1/deps.py`.
- Business logic is isolated in `app/services/`:
  - `evaluator.py` — flag evaluation and the operator catalogue
  - `environments.py` — provisioning, state seeding, version invalidation (`bump_environment_versions`)
  - `snapshots.py` — cached per-environment flag/state/rule resolution
  - `rules.py` — targeting rule ordering and audit snapshots
  - `api_keys.py` — SDK key issuance
- `core/cache.py` owns the Redis connection and the JSON helpers (`cache_get_json`, `cache_set_json`, `cache_delete`); all swallow Redis errors and report a miss, so a cache outage is a slowdown, not an outage.
- `SNAPSHOT_CACHE_TTL` (default 60s) is a backstop for a mutation that forgot to bump the version; `SNAPSHOT_CACHE_ENABLED` disables the layer.
- Startup still runs `Base.metadata.create_all()` for fresh dev/test databases. It does not upgrade an existing database.
- Startup verifies the auth columns and fails with an actionable migration message on an old schema; the transition is documented in `backend/migrations/`.
- DB and Redis connectivity are exposed via `/healthz` and `/api/v1/healthz`.

## Auth and Authorization

- `Organization.owner_id` is the ownership boundary. A user can own multiple organizations.
- Org/project/environment lookups require the current owner and return `404` for inaccessible resources, avoiding ID enumeration.
- `core/security.py` holds bcrypt hashing/verification, typed JWT create/decode, and a process-local auth-request limiter.
- JWT settings: `JWT_SECRET`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`.
- Access tokens 15 minutes, refresh tokens 7 days by default. Refresh tokens are stateless and reusable until expiry.
- `User` uses a string UUID primary key, unique indexed email, full name, and a password hash exposed as `hashed_password` while retaining the physical `password_hash` column.
- Passwords must be at least 8 characters; hashes are never returned by any schema.
- Public: `/`, `/healthz`, `/api/v1/healthz`, `/api/v1/auth/register`, `/api/v1/auth/login`, `/api/v1/auth/refresh`.
- Protected: organizations, projects/environments, flags, evaluate, batch-evaluate, bootstrap, audit, `/api/v1/auth/me`.
- Authenticated mutations populate `AuditLog.actor` plus nullable `user_id` and `user_email`.

## Tenancy and Data Model

Models: `User`, `Organization`, `Project`, `Environment`, `Flag`, `FlagEnvState`, `TargetingRule`, `ApiKey`, `AuditLog`.

- There is no auto-provisioned default organization or project; both are created explicitly.
- Organization names are unique (409).
- Creating a project auto-provisions `dev`, `staging`, and `prod`.
- Custom environments are lowercase identifiers (e.g. `qa`); creating one seeds `FlagEnvState` for every existing flag.
- Creating a flag seeds a state row for every environment of its project.
- Strict project scoping: every flag/evaluate/bootstrap/audit endpoint requires `project_id` (`422` missing, `404` unknown), and queries filter by `Flag.project_id` / `AuditLog.project_id`.
- Environments must belong to the project (`404` otherwise), so identical flag keys can coexist in different projects without leaking state, results, snapshots, or audit entries.

## Evaluation and Targeting

Evaluation order: kill switch → rules by ascending priority → percentage rollout → default value.

- Kill switch immediately returns the configured default value.
- Percentage rollout is deterministic Murmur3 hashing of `flag_key:user_id`; sticky for the same flag and user.
- `evaluate_flag()` sorts rules itself rather than trusting the caller's order.
- `TargetingRule` is environment-scoped (`flag_id` + `env`), ordered by `priority` where `0` is highest, kept dense (`0..n-1`) on create-append, reorder, and delete.
- Conditions are `{"attr", "op", "value"}`, ANDed within a rule. A rule needs 1–25 conditions; an empty list is rejected.
- Operators: `equals`, `not_equals`, `in`, `not_in`, `contains`, `starts_with`, `ends_with`, `greater_than`, `greater_than_or_equal`, `less_than`, `less_than_or_equal`, `exists`, `not_exists`.
- Aliases `eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `notExists` are accepted and normalized on write.
- `in`/`not_in` accept a list or a comma-separated string; `exists`/`not_exists` ignore `value`.
- A missing attribute makes a condition false (the rule skips). `equals` is case-sensitive; `contains`/`starts_with`/`ends_with` are not.
- Rule mutations bump only the mutated environment's `Environment.version` and write an audit action of `rule.created`, `rule.updated`, `rule.deleted`, or `rule.reordered`.
- `conditions_json` is exposed as `conditions` on every wire format (flag list, rule CRUD, `/evaluate`, `/bootstrap`).
- Schemas (`RuleCondition`/`RuleCreate`/`RuleUpdate`) are in `app/schemas/schemas.py`.

## API Surface

- `GET /healthz` — DB + Redis health
- `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `POST /api/v1/auth/refresh`, `GET /api/v1/auth/me`
- `POST /api/v1/organizations` — create owned organization
- `GET /api/v1/organizations` — list owned organizations with projects, environments, flag summaries
- `GET /api/v1/organizations/{org_id}` — organization details
- `POST /api/v1/organizations/{org_id}/projects` — create project, auto-provisions `dev`/`staging`/`prod`
- `GET|POST /api/v1/projects/{project_id}/environments` — list / create environments
- `GET|POST /api/v1/flags?project_id=` — list / create flags
- `GET /api/v1/flags/{key}?project_id=` — get flag
- `PATCH /api/v1/flags/{key}/environments/{env}?project_id=` — state, rollout, kill switch
- `GET|POST /api/v1/flags/{key}/environments/{env}/rules?project_id=` — list / create rules
- `PUT /api/v1/flags/{key}/environments/{env}/rules/reorder?project_id=` — re-order, renormalize `0..n-1`
- `PUT|DELETE /api/v1/flags/{key}/environments/{env}/rules/{rule_id}?project_id=`
- `POST /api/v1/evaluate?project_id=`, `POST /api/v1/batch-evaluate?project_id=`
- `GET /api/v1/bootstrap?project_id=&env=` — SDK snapshot, Bearer or `X-SDK-Key`
- `GET /api/v1/audit?project_id=`

## API Keys

- Format `cp_<env>_<random32>`, e.g. `cp_prod_a1b2c3d4e5f6g7h8i9j0k1`.
- Hashed with SHA-256 before storage; the raw key is returned only on creation, as `key` on `ApiKeyCreatedResponse`.
- SDK clients send the full key in `X-SDK-Key`. Authentication hashes it and compares hashes only; the stored `prefix` column is a non-secret label and is never matched.
- No response other than creation returns any part of a key.
- `env` defaults to `dev` on `/bootstrap`, `/evaluate`, and the SDK client, so one system never defaults to two environments.
- Keys are project-scoped and cannot access resources outside their project.
- Keys issued before the Phase 0 fix are compromised: their 12-character prefix authenticated, and it was shown on the Keys page. Revoke and reissue each one.
- `POST /api/v1/projects/{project_id}/keys` — create
- `GET /api/v1/projects/{project_id}/keys` — list
- `DELETE /api/v1/projects/{project_id}/keys/{key_id}` — revoke

## Bootstrap and Caching

- `/bootstrap` returns the full SDK snapshot for one project environment, read through the Redis snapshot cache.
- `services/snapshots.py` serves from `catalyst:snapshot:<project>:<env>` when the cached version matches the caller's `Environment.version`, and rebuilds from PostgreSQL otherwise.
- `/bootstrap`, `/evaluate`, and `/batch-evaluate` all read through the snapshot service and report the source in `X-Catalyst-Cache`.
- ETag support: a matching `If-None-Match` returns `304` with the ETag echoed, before the snapshot body is loaded.
- The ETag derives from `Environment.version`; a mutation in one project never invalidates another project's ETag.
- Authenticated bootstrap responses use private cache headers.
- `/bootstrap` and `/evaluate` accept either a user Bearer token or a project-scoped `X-SDK-Key`.

## Frontend

Architecture:

- `main.tsx` wraps the route tree with `BrowserRouter` and `AuthProvider`; `App.tsx` is the route table.
- `AuthContext` restores an in-memory access token from a localStorage refresh token, exposes login/register/logout, and redirects protected routes to `/login`.
- `api.ts` attaches bearer tokens, shares a single refresh request, retries once after a `401`, and emits an auth-expired event when refresh fails. Access tokens stay in memory; the refresh token uses localStorage (documented MVP tradeoff, not httpOnly).
- `WorkspaceContext` owns org/project summaries, last-valid organization persistence, and org/project creation.
- `useProject(projectId)` owns flags, environments, active environment/query state, polling, playground evaluation, and flag/environment/rule mutations.
- `AppShell`/`Sidebar` handle organization switching and project navigation and link out to the public `/docs` SDK reference. The global header holds only branding, health status, and the user menu.
- `DocsPage.tsx` is the public SDK reference at `/docs`, kept in sync with the SDK README by hand.
- `lib/docsSearch.ts` owns the docs search index and matching so it is unit tested without rendering.
- `lib/targeting.ts` owns the operator catalogue, shared value coercion, list-token splitting/joining, draft validation, and attribute-input parsing (`key=value` lines or JSON).
- `lib/attributeCatalog.ts` owns the preset attribute catalogue and the client-side evaluator mirror (`previewConditionMatch`/`previewRuleMatch`) used for the builder's match preview. The server stays the source of truth; the preview is advisory.
- Reusable components: `Sidebar`, `FlagCard`, `KillSwitchButton`, `RolloutSlider`, `RuleBuilder`, `EvalPlayground`, `EnvBadge`, plus auth/layout/flag-creation components.
- `RuleBuilder` derives its value control from the attribute's value kind (boolean toggle, enum select, numeric input, token chips for `in`/`not_in`) and renders a live match preview of the whole rule chain.
- `RolloutSlider` is debounced: the thumb moves on a local draft, the mutation commits after `debounceMs` (default 400ms) and flushes on pointer/key release or blur, so a drag is one `PATCH`. `useProject.updateRollout` applies values optimistically under a per-flag/per-environment sequence number so a slow response cannot overwrite a newer edit.

Design system (Retro Black & Gold):

- Fonts: `Playfair Display` for headings, stat values, brand; `IBM Plex Mono` for UI text, labels, code badges.
- Palette tokens in `index.css`: `--gold-primary: #F5C518`, `--gold-bright: #FFD84D`, `--amber-accent: #D4862A`, `--bg-primary: #0E0E0E`, `--text-primary: #F0E6C8`, `--danger-bright: #E74C3C`, `--success: #27AE60`.
- Patterns: glassmorphism dark cards with gold borders, 3px gold accent strip on flag cards, gold gradient CTA buttons, pulsing crimson kill-switch glow, custom gold range slider, dashed gold playground boxes, radial gold shimmer on the body.
- Tokens live in `index.css`; component styles in `App.css`.

## Python SDK

- Distribution `sdk-catalyst`, import name `catalyst_sdk` (the `catalyst-sdk` PyPI name is taken by an unrelated project). Hatchling build, ships `py.typed`, `license = "MIT"` with a bundled `LICENSE`, only runtime dependency `httpx`.
- `hashing.py` vendors MurmurHash3 x86_32 so bucketing needs no native extension; verified against `mmh3` and the server's `get_user_bucket()`.
- `evaluator.py` mirrors `app/services/evaluator.py`: kill switch → rules by ascending priority → percentage rollout → default, with operator aliases normalized.
- `client.py` reads as it evaluates: construction does no I/O, and every check makes a conditional request before deciding locally, so a dashboard toggle shows on the next check. Snapshot swaps are a single attribute assignment, so readers see a consistent view.
- Reads are conditional (`If-None-Match`), so an unchanged environment costs a `304` with no body. `test_evaluation_is_sub_millisecond` asserts decision cost with `refresh_on_evaluate=False`.
- `host` defaults to `transport.DEFAULT_HOST`, overridable per client with `host=` or per process with `CATALYST_HOST`; the argument wins. An explicitly empty `host` raises `ConfigurationError`.
- A `_read_lock` collapses concurrent checks into one request (single-flight). A failed read sets a `failure_backoff` window (default 5s), so an unreachable API costs one timeout per window. A first read that fails falls back to the disk cache before `default_value`.
- `refresh_on_evaluate=False` gives in-memory-only evaluation; `start_auto_refresh(interval, on_error)` is then how to stay current. `offline=True` implies it.
- An explicit `refresh()` raises `AuthorizationError` because a rejected key will not fix itself; the implicit read inside `evaluate()`/`is_enabled()` absorbs it so a flag check inside someone else's request is not a 500. `raise_on_error=True` propagates reads too.
- The last good snapshot is persisted under `~/.cache/catalyst` (`CATALYST_CACHE_DIR` overrides) with an atomic write-then-rename. `cache_path=False` disables it.
- `backend/tests/test_sdk_parity.py` is a differential suite: it fuzzes both evaluators with identical inputs and requires identical values, reasons, and rule ids. Any change to evaluation semantics should keep it green.
- Release: bump `pyproject.toml` version and merge. `.github/workflows/publish-sdk.yml` re-runs the SDK and parity suites and publishes to PyPI when the version is new, using Trusted Publishing (OIDC) so no token is stored in the repo.

## Local Development

- `make up` — start PostgreSQL (`:5432`) and Redis (`:6379`), both with health checks and persistent volumes.
- `make dev-api` — FastAPI on `:8000`
- `make dev-web` — Vite on `:5173`
- `make test` — backend suite including the parity suite
- `make test-sdk` — SDK suite
- `make build-sdk` — build the SDK wheel
- Configuration lives in `.env.example`, including JWT settings.

## Testing

Backend (`cd backend && uv run pytest`):

- Self-contained: `tests/conftest.py` points the app at a temporary SQLite database (`aiosqlite`) before any app module is imported, so no PostgreSQL/Redis is needed and the dev database is untouched.
- The default API fixture registers an authenticated account; `anon_client` covers auth and protection tests.
- Coverage: health/root, sticky rollout hashing, kill switch, rule evaluation, rule CRUD with condition validation and dense re-ordering, cross-user/project/environment isolation, rule precedence and environment-scoped cache invalidation, organization and project CRUD, custom environment management, project scoping, bootstrap ETag scoping (304 → 200 on mutation), Redis snapshot caching including degradation when Redis is absent/broken/undecodable, registration/login/refresh/me, password validation and hashing, auth rate limiting, cross-user authorization and audit attribution, API key management, `X-SDK-Key` auth and project-scoped SDK access, and server/SDK parity fuzzing.
- **77 tests passing.**

SDK (`cd packages/catalyst-python-sdk && uv run --with pytest --with mmh3 pytest`):

- Self-contained, no network or running services.
- **87 tests passing.**

Frontend (`cd frontend`):

- `npm run test` — routing, auth-aware API client, targeting helpers, rule builder, rollout slider, docs search
- `npm run lint`
- `npm run build`
- **82 tests passing** across 8 files.

## Deployment

- API: Render web service `catalyst-api` (free, `oregon`), native Python, built with `uv`, no Docker.
- Frontend: Vercel project `catalyst-dashboard`, `rootDirectory: frontend`, production branch `main`.
- Database: Neon project `catalyst` (`aws-us-west-2`, PG 16.15), tables created by startup `create_all()`.
- Cache: Render Key Value `catalyst-cache` (free, 25 MB), in-memory only and empty after every restart.
- Both providers auto-deploy from `main`. Render declares `buildFilter.paths: backend/**`, so docs- or frontend-only pushes are correctly not deployed.
- Render spins down after 15 minutes idle and cold starts take about a minute; Neon suspends when idle, so cold starts can stack. Neither service has backups.
- `JWT_SECRET` and `SECRET_KEY` use `generateValue: true` in `render.yaml`. Never deploy the shipped `change-this-jwt-secret-in-production` default to a public host.

Gotchas:

- Neon's `sslmode=require` breaks `postgresql+asyncpg://` with `TypeError: connect() got an unexpected keyword argument 'sslmode'`. Strip it before setting `DATABASE_URL`.
- The Redis internal URL carries no password and is reachable only over Render's private network (`ipAllowList: []`). It will not resolve from a laptop; point local SDK work at local Redis. The API is in the same region as the Key Value, which is what makes internal DNS resolve.
- Render's free Postgres is deliberately unused because it deletes data after 30 days.
- The Render API env-var path takes the KEY, not the id: `PUT /v1/services/{id}/env-vars/{KEY}`. Passing an id silently creates a junk variable. Delete with `DELETE /v1/services/{id}/env-vars/{KEY}`.
- The frontend needs `VITE_API_BASE_URL` at build time; `api.ts` otherwise falls back to the relative `/api/v1` dev proxy path, which resolves against the Vercel origin and 404s. `frontend/vercel.json` supplies the SPA rewrite that keeps `/docs` and `/app/**` working on a hard refresh.
- `CORS_ORIGINS` on the API must list the deployed frontend origin.
- Local Postgres and Neon are separate databases. An SDK key or project created against `localhost:8000` does not exist in production and `/api/v1/bootstrap` answers `404 API key not found`. SDK keys are read-only and cannot be created over the API, so mint production keys from the production dashboard.

## Visual Documentation (`visual/`)

- Seven interactive source-backed diagrams generated with Archify: runtime architecture, SDK conditional read, toggle propagation, tenant onboarding, SDK release pipeline, SDK read-path lifecycle, and the evaluation PII boundary.
- `visual/sources/*.json` is the editable source of truth; `visual/artifacts/*.html` is generated, delivered output with a SHA-256 receipt. Edit the JSON, never the HTML.
- `index.html`, `<slug>.html`, and `assets/site.css` are generated by `visual/build-site.mjs` from a manifest of editorial copy. Change the copy in the build script, not the generated HTML.
- `SRC n` badges resolve to a `file:line` in this repository, pinned to one commit. A diagram claim that is not true of the code is a bug in the diagram, not in the code.
- Regeneration loop: `zsh visual/check.sh` validates all sources at `showcase` quality, `zsh visual/deliver.sh` renders and commits artifacts, `zsh visual/verify.sh` collects bounded desktop browser evidence, `node visual/build-site.mjs` regenerates the pages.
- `deliver` is the only acceptance command. A non-zero exit is a failure and must never be described as success. Diagram readability is a separate human judgement.
- All seven hold 9/9 showcase checks with zero composition errors. Six of seven fit a 1440x900 viewport with no scrolling; the SDK lifecycle overflows by 16px because the lifecycle renderer reserves three fixed bands and refuses a shorter `viewBox`. Do not fix that by shrinking node text below the 6px readability floor.
- Geometry controls are per-diagram, so a change that fixes a corridor collision in one source routinely creates one in another.

## CI

- **`backend-tests`** (`ci.yml`): Python 3.12 with `uv run pytest`, SQLite-backed, with a fake Redis standing in for the cache.
- **`frontend-checks`** (`ci.yml`): Node 22 — `npm ci`, `npm run test`, `npm run lint`, `npm run build`.
- **`sdk-tests`** (`ci.yml`): Python 3.12 — SDK suite, a `uv build` wheel check, and the parity suite inside the backend environment.
- **`Publish SDK`** (`publish-sdk.yml`): on pushes to `main` touching `packages/catalyst-python-sdk/**`; requires a one-time Trusted Publisher config on pypi.org (owner `VijeshVS`, repo `catalyst`, workflow `publish-sdk.yml`, environment `pypi`).
- **`Render Deploy Status`** (`render-deploy-status.yml`): on pushes to `main` and manual dispatch; publishes the `render/deploy` commit status and the README badge. Requires the `RENDER_API_KEY` secret (account key starting with `rnd_`); `RENDER_SERVICE_ID` is an optional override.
  - Runs on `main` only, never on `pull_request`: Render auto-deploys `main` only, so a PR branch has no deploy to report. No PR-gating backend check exists, so nothing proves the API deploys or that `/healthz` is `ok` against real Neon and Render Redis.
  - Mirrors the Render build filter by reading the pushed commit's changed files: a deploy-relevant push waits for the deploy of that exact SHA, a non-deploy-relevant push reports the state of the deploy production is actually running, so a broken deploy is not masked by a later docs commit.
  - A push to `main` races Render's trigger, so the deploy-relevant path polls up to 10 minutes for a deploy whose `commit.id` matches `github.sha`, then polls until it settles, posting `pending` once and a terminal state after.
  - GitHub caps a commit's file list at 300 entries; a commit at the cap is treated as deploy-relevant rather than risk a false "nothing to deploy".
  - An unrecognised Render status maps to `error`, never `success`, and a missing or rejected `RENDER_API_KEY` fails the run.
  - The deploy filter is duplicated in `render.yaml` and the workflow's `DEPLOY_PATHS` on purpose; change them together.
  - Every push shows two check entries by design: the Actions check run, which makes a failure visible, and the `render/deploy` commit status it writes. If the job dies before posting, no status is written at all, so the Actions check is what turns that into a red X.
- **`PR Hygiene`** (`pr-hygiene.yml`): on `opened`, `edited`, `synchronize`, `reopened`. Fails a PR whose title is not `release(<scope>): <description>`, whose body is empty, or whose commits break Conventional Commits.
  - Hand-written rather than a third-party action: it gates every merge and needs no third-party code or token scope. It reads the PR through the API instead of checking out untrusted branch code, so it is fork-safe, and holds only `contents: read` and `pull-re-requests: read`.
  - PR title and body are attacker-controlled, so they arrive as `env:` vars and are never interpolated into the script body.
  - Merge commits are skipped because `git merge` produces a subject nobody controls.
  - A failing check is advisory until it is marked required in branch protection; nothing in the repo can make that change.
  - The title rule rejects the repository's entire PR history (0 of 30 match), while the commit rule is compatible with practice (39 of the last 40 subjects match). The scope is free-form and matches the commit rule.
