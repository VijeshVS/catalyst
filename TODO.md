# Catalyst — Implementation Roadmap (TODO)

This roadmap outlines upcoming features organized in the recommended implementation sequence. Each phase builds upon the existing core models and evaluation engine established during initialization.

---

## Phase 0: Landing Page & UX Separation (Navigation Overhaul)

> **Goal:** Replace the cluttered single-page dashboard with a proper multi-page flow:
> a public landing page → organization onboarding → a GitHub-style project list → a project
> detail view that separates flags, environments, and settings into distinct sub-pages.
>
> **Status: ✅ Complete.** The React Router v6 route tree, public landing page, full-page
> onboarding forms, persistent workspace sidebar, project navigation, environment tabs, and
> extracted page/component/state architecture are implemented. The existing flag controls,
> evaluation playground, and environment management remain available on the new project pages.

### 0-A · Public Landing Page (`/`)

- [x] **Hero section** — Headline (`"Ship features with confidence"`), sub-headline, and two CTAs: _"Get Started"_ (→ `/app`) and _"View Docs"_.
- [x] **Feature highlights** — Four cards: Feature Flags, Emergency Kill Switch, Percentage Rollout, SDK-Ready Bootstrap.
- [x] **How It Works** — Numbered steps: Create org → Create project → Add flags → Evaluate.
- [x] **Tech stack badge strip** — FastAPI · PostgreSQL · Redis · React.
- [x] **Footer** — Branding, links.
- [x] Must use the existing Retro Black & Gold design system from `frontend/src/index.css`.

### 0-B · Routing Setup

> React Router v6 is installed and configured in `frontend/src/App.tsx` / `main.tsx`.

- [x] Install and configure **React Router v6** (`react-router-dom`).
- [x] Define top-level routes:

  | Path | Component |
  |------|-----------|
  | `/` | `LandingPage` |
  | `/app` | Redirect → first/last org, or org-creation screen |
  | `/app/orgs/:orgId` | `OrgDashboard` (project list) |
  | `/app/orgs/:orgId/projects/:projectId` | `ProjectDetail` (flags tab by default) |
  | `/app/orgs/:orgId/projects/:projectId/environments` | `EnvironmentsPage` |
  | `/app/orgs/:orgId/projects/:projectId/audit` | `AuditPage` (Phase 3+ placeholder) |
  | `/app/orgs/:orgId/projects/:projectId/settings` | `SettingsPage` (Phase 3+ placeholder) |

### 0-C · Organization Onboarding Flow

- [x] **Welcome screen** (`/app` — no orgs yet): Illustrated empty state, headline _"Create your first Organization"_, and a prominent CTA.
- [x] **Create Organization** — **Full-page centered form, not a modal**:
  - Organization name field with live slug preview (e.g. `acme-inc`).
  - Optional short description.
  - Submit navigates to the new org's project list (`/app/orgs/:orgId`).
- [x] Visiting `/app` when orgs exist redirects to the last-valid organization persisted in `localStorage`, or to the first organization.
- [x] **Org switcher** in the sidebar: dropdown listing all orgs + _"+ New Organization"_ at the bottom. The "+ Org" button was removed from the global header.

### 0-D · Project List Page (`/app/orgs/:orgId`) — GitHub-style

- [x] **Persistent sidebar** (visible across all `/app/**` routes):
  - Org name + avatar initial at the top.
  - Nav links: _Projects_ (active), _Settings_ (future).
  - Org switcher dropdown at the bottom.
- [x] **Projects grid/list** — each project card shows project name, environment badges, total flag count, and last-updated timestamp; cards navigate to project detail.
- [x] **"+ New Project" flow** — **Full-page form, not a modal**:
  - Project name input.
  - Read-only preview of the three default environments that will be auto-created.
  - On submit, redirects into the new project's flags page.
- [x] Empty state when no projects exist — illustrated, with _"Create your first project"_ CTA.

### 0-E · Project Detail Page (`/app/orgs/:orgId/projects/:projectId`)

- [x] **Project header** — Breadcrumb (`OrgName / ProjectName`) and project-level environment tab strip, including custom environments.
- [x] **Tab navigation** inside a project:

  | Tab | URL suffix | Content |
  |-----|-----------|---------|
  | Feature Flags | (default, no suffix) | Flag list + create flow |
  | Environments | `/environments` | Env list + custom env creation |
  | API Keys | `/keys` | Phase 2 placeholder |
  | Audit Log | `/audit` | Phase 3+ placeholder |
  | Settings | `/settings` | Phase 3+ placeholder |

- [x] **Feature Flags sub-page**:
  - Flag cards with kill switch toggle, rollout slider, and evaluation playground.
  - _"+ Create Flag"_ opens a slide-over panel, not a fullscreen modal overlay.
  - Active environment comes from the project header/query state, not the global header.
- [x] **Environments sub-page**:
  - Lists all environments; standard environments have an _"auto-created"_ badge and custom ones a _"custom"_ badge.
  - Shows bootstrap cache version (`v{n}`) per environment.
  - Inline _"+ New Environment"_ form with lowercase identifier validation.
  - _"View flags →"_ switches to the flags tab with that environment active.
- [x] **Remove all workspace dropdowns from `<header>`**. The global header contains only brand, health indicator, and user menu.

### 0-F · State Management & Component Refactor

- [x] Introduce **`WorkspaceContext`** — owns the authenticated organization list, selected organization, project summaries, and workspace mutations.
- [x] Introduce **`useProject(projectId)`** — owns flags, environments, active environment, playground state, and flag/environment actions.
- [x] Extract pages into `frontend/src/pages/`:
  - `LandingPage.tsx`
  - `OrgDashboard.tsx` (project list)
  - `ProjectDetail.tsx` (tabs + flag list)
  - `EnvironmentsPage.tsx`
- [x] Extract reusable UI components into `frontend/src/components/`:
  - `Sidebar.tsx`
  - `FlagCard.tsx`
  - `KillSwitchButton.tsx`
  - `RolloutSlider.tsx`
  - `EvalPlayground.tsx`
  - `EnvBadge.tsx`
- [x] `npm run lint`, `npm run build`, and routing tests pass.

---

## Phase 0.5: Authentication (Register / Login)

> **Goal:** Gate the entire dashboard behind user accounts. Users must register or log in before
> they can create organizations, manage projects, or touch any flags. Auth is a prerequisite for
> meaningful audit logs, org ownership, and the API key system in Phase 2.
>
> **Status: ✅ Complete.** Registration, JSON login, typed access/refresh JWTs, protected API
> ownership checks, audit attribution, frontend token refresh, auth pages, and rate-limited auth
> endpoints are implemented. JWTs use `python-jose[cryptography]`; password hashing uses Passlib
> bcrypt.

### 0.5-A · Backend: User Model & Auth Endpoints

- [x] **User model** — the existing `User` model was adapted in place (no duplicate model) with UUID/string UUID primary key, unique indexed email, `hashed_password` Python attribute mapped to the legacy-compatible `password_hash` column, full name, and created timestamp.
- [x] **Password hashing** — Passlib bcrypt; passwords are deterministically pre-hashed only when they exceed bcrypt's 72-byte input limit.
- [x] **JWT tokens** — signed typed access tokens (15 min) and refresh tokens (7 days) using `python-jose[cryptography]` and environment-configured secret/expiry.
- [x] **Auth endpoints** under `/api/v1/auth/`:
  | Method & Path | Description |
  |---------------|-------------|
  | `POST /api/v1/auth/register` | Create account (`email`, `password`, `full_name`) and return a token pair |
  | `POST /api/v1/auth/login` | Return `access_token` + `refresh_token` (JSON body, not form) |
  | `POST /api/v1/auth/refresh` | Exchange valid refresh token for a new token pair |
  | `GET /api/v1/auth/me` | Return the current authenticated user's sanitized profile |
- [x] **Auth dependency** — `get_current_user` is injected into every protected route; unauthenticated requests get `401`.
- [x] **Exempt routes** — `/`, `/healthz`, `/api/v1/healthz`, `/api/v1/auth/register`, `/api/v1/auth/login`, and `/api/v1/auth/refresh` remain public.
- [x] **Organization ownership** — `Organization.owner_id` points to `User.id`; organization/project/environment lookups filter by the authenticated owner, returning `404` for inaccessible resources.
- [x] **Audit log enrichment** — nullable `user_id` FK and denormalized `user_email`, while retaining the Phase 1 `actor` field.
- [x] Auth tests cover registration, validation, login, refresh, `/me`, bearer protection, cross-user isolation, rate limiting, and audit attribution.
- [x] A documented one-time SQL transition for existing Phase 1 PostgreSQL databases is in `backend/migrations/001_auth_ownership.sql`; fresh/test databases continue to use the existing startup `create_all()` bootstrap.

### 0.5-B · Frontend: Auth Pages & Token Management

- [x] **`/login` page** — Email + password form, _"Don't have an account? Register"_ link, submit → stores tokens → redirects to `/app`.
- [x] **`/register` page** — Full name + email + password + confirm password, submit → auto-login → redirects to `/app`.
- [x] **Token storage** — access token remains in memory; refresh token is persisted in `localStorage` so a hard reload can restore the session. The localStorage/XSS tradeoff is documented; an httpOnly-cookie/CSRF design is deferred.
- [x] **`AuthContext`** — exposes `user`, `login()`, `logout()`, and `register()`; it restores the session and handles expiry.
- [x] **Protected route wrapper** — `<ProtectedRoute>` redirects unauthenticated users to `/login` and preserves the attempted destination.
- [x] **Auth-aware API client** (`frontend/src/api.ts`) — attaches `Authorization: Bearer <token>`, shares a single refresh promise, retries a protected request once after refresh, and clears expired sessions.
- [x] **User menu in header** — initials/avatar, signed-in email, and logout action.
- [x] **`/login` and `/register` use the landing page's Black & Gold design**.

### 0.5-C · Security Hardening (Minimum Bar)

- [x] Rate-limit `/api/v1/auth/login` and `/api/v1/auth/register` requests per client IP (five per configured window, with `429`/`Retry-After`); the limiter is process-local for the current single-process deployment.
- [x] `JWT_SECRET`, algorithm, and token expiry durations are read from environment variables; `.env.example` is updated.
- [x] Passwords must be ≥ 8 characters (validated in Pydantic schemas).
- [x] No response schema exposes `hashed_password` or `password_hash`.

---

## Phase 1: Multi-Tenant Hierarchy (Organizations, Projects & Environments)

> **Goal:** Transition from default auto-provisioned entities to explicit management of Organizations, Projects, and scoped Environments.
>
> **Status: ✅ Complete.** All items below are implemented. Auto-provisioning of the default
> organization/project was removed; every flag/evaluate/bootstrap/audit call requires an
> explicit `project_id` (422 when missing, 404 when unknown) and validates that the environment
> belongs to that project. The bootstrap ETag is project-scoped and invalidated by every
> snapshot-affecting mutation. Phase 0.5 ownership checks now apply on top of these rules.

- [x] **Backend: Organization Management**
  - `POST /api/v1/organizations` — Create organization
  - `GET /api/v1/organizations` — List the authenticated user's organizations
  - `GET /api/v1/organizations/{id}` — Get organization details
- [x] **Backend: Projects & Environments**
  - `POST /api/v1/organizations/{org_id}/projects` — Create project
  - Auto-provision standard environments (`dev`, `staging`, `prod`) on project creation
  - `POST /api/v1/projects/{project_id}/environments` — Create custom environment
  - `GET /api/v1/projects/{project_id}/environments` — List project environments
  - Scope all flag queries and mutations strictly by `project_id`
- [x] **Frontend: Workspace Navigation** _(superseded by the Phase 0 route architecture)_
  - Persistent organization/project navigation
  - Full-page project and organization creation flows
  - Project-level environment management view

---

## Phase 2: API Key Management & SDK Authentication

> **Goal:** Secure the `/bootstrap` and `/evaluate` endpoints with environment-scoped SDK tokens and provide a dashboard for managing keys.

- [x] **Backend: API Key Service & Endpoints**
  - Generate cryptographically secure keys with prefix format: `cp_<env>_<random32>`
  - Store SHA-256 hash in `api_keys` table; return raw secret key only once upon creation
  - `POST /api/v1/projects/{project_id}/keys` — Generate new API key
  - `GET /api/v1/projects/{project_id}/keys` — List active keys (prefix, env, created_at, status)
  - `DELETE /api/v1/projects/{project_id}/keys/{key_id}` — Revoke key
  - Add `X-SDK-Key` authentication middleware to `/api/v1/bootstrap` and `/api/v1/evaluate`
- [x] **Frontend: API Keys Dashboard**
  - New "API Keys" tab inside the Project Detail page (Phase 0-E)
  - Create Key modal with environment selector (`dev`, `staging`, `prod`) and descriptive name
  - "Copy to Clipboard" banner with one-time reveal of full secret key
  - Revocation confirmation dialog and status badges (`Active` / `Revoked`)

### 2-A · Backend: API Key Service & Endpoints

- [x] **API Key service** (`app/services/api_keys.py`):
  - `generate_api_key_prefix(env)` — Creates `cp_<env>_<random32>` format key
  - `hash_api_key(key)` — SHA-256 hashing for secure storage
  - `create_api_key()` — Creates key, returns raw key (only once), stores hash
  - `list_api_keys()` — Lists all keys for a project
  - `revoke_api_key()` — Marks key as revoked
- [x] **API Key schemas** (`app/schemas/schemas.py`):
  - `ApiKeyCreate` — Request body for creating a key
  - `ApiKeyResponse` — Response with key details
  - `ApiKeyListResponse` — List of keys
- [x] **API Key endpoints** (`app/api/v1/projects.py`):
  - `POST /api/v1/projects/{project_id}/keys` — Create key (returns raw key once)
  - `GET /api/v1/projects/{project_id}/keys` — List all keys
  - `DELETE /api/v1/projects/{project_id}/keys/{key_id}` — Revoke key
- [x] **Flexible auth middleware** (`app/api/v1/deps.py`):
  - `get_current_sdk_key_or_user()` — Accepts either Bearer token or X-SDK-Key
  - SDK keys can access `/bootstrap` and `/evaluate` endpoints
  - Project scoping enforced for SDK keys
- [x] **Authentication tests** (`tests/test_api_keys.py`):
  - 7 comprehensive tests covering CRUD and SDK auth
  - All 25 backend tests passing

### 2-B · Frontend: API Keys Dashboard

- [x] **API Keys tab** (`frontend/src/pages/ProjectDetail.tsx`):
  - Tab navigation with `/keys` route
  - Create Key modal with environment selector
  - List view with status badges and copy-to-clipboard
  - Revocation confirmation dialog

---

## Phase 3: Rule-Based Targeting & Visual Rule Builder

> **Goal:** Enable targeted beta rollouts based on user attributes (e.g. email domain, user role, country, app version) with an intuitive dashboard builder.
>
> **Status: ✅ Complete.** Environment-scoped rule CRUD, priority re-ordering with dense `0..n-1`
> renormalization, per-environment SDK cache invalidation, audit attribution, an expandable visual
> rule builder on every flag card, and an attribute-aware evaluation playground are implemented.

- [x] **Backend: Rule CRUD Endpoints**
  - `POST /api/v1/flags/{key}/environments/{env}/rules` — Create targeting rule
  - `PUT /api/v1/flags/{key}/environments/{env}/rules/{rule_id}` — Update conditions/priority
  - `DELETE /api/v1/flags/{key}/environments/{env}/rules/{rule_id}` — Delete rule
  - `GET /api/v1/flags/{key}/environments/{env}/rules` — List rules in priority order
  - `PUT /api/v1/flags/{key}/environments/{env}/rules/reorder` — Re-order priorities (0 = highest, renormalized to `0..n-1`)
  - Invalidate environment version on rule mutation to bust SDK cache (only the mutated environment)
- [x] **Frontend: Visual Rule Builder UI**
  - Expandable "Targeting Rules" section on each Flag Card
  - Condition builder row:
    - Attribute input (e.g. `email`, `role`, `country`, `version`)
    - Operator dropdown (`equals`, `not_equals`, `in`, `not_in`, `contains`, `starts_with`, `ends_with`, `>`, `>=`, `<`, `<=`, `exists`, `not_exists`)
    - Value input (string, comma-separated array, number, boolean)
  - Target serve value toggle (`True` / `False`)
  - Priority re-ordering (move up/down) and two-step delete confirmation
  - Integration with the live evaluation playground (pass custom attributes to verify rule match)

### 3-A · Backend: Rules Service & Endpoints

- [x] **Rule service** (`app/services/rules.py`):
  - `list_rules_for_env()` — environment-scoped rules ordered by priority
  - `next_priority()` — append position for a new rule
  - `normalize_priorities()` — dense `0..n-1` renormalization
  - `apply_ordered_ids()` — validates a reorder request lists every rule exactly once
  - `serialize_rule()` / `serialize_rules()` — audit snapshots
- [x] **Rule schemas** (`app/schemas/schemas.py`):
  - `RuleCondition` — validated `{attr, op, value}` with canonical operator normalization
  - `RuleCreate` / `RuleUpdate` / `RuleReorder`
  - `TargetingRuleResponse` — exposes `conditions` on every wire format (flag list, rule CRUD, bootstrap)
  - Conditions are required (1–25 per rule) so an unconditional catch-all rule cannot be created by accident
- [x] **Rule endpoints** (`app/api/v1/flags.py`) — all owner-scoped, environment-validated, and audited as `rule.created` / `rule.updated` / `rule.deleted` / `rule.reordered`
- [x] **Evaluator** (`app/services/evaluator.py`) — added the `exists` / `not_exists` presence operators and the `RULE_OPERATORS` / `normalize_operator()` catalogue shared by the schema layer
- [x] **Tests** (`tests/test_rules.py`) — 14 tests covering condition validation, CRUD, cross-user/cross-project/cross-environment isolation, priority density and re-ordering, environment-scoped cache invalidation, audit attribution, and rule-driven evaluation precedence

### 3-B · Frontend: Rule Builder & Attribute Playground

- [x] **Rule builder** (`frontend/src/components/RuleBuilder.tsx`) — collapsible per-flag section with read-only rule summaries, an inline condition editor, serve-value toggle, priority move up/down, and two-step delete
- [x] **Preset-driven conditions** — conditions are built by picking, not typing:
  - **Attribute catalogue** (`frontend/src/lib/attributeCatalog.ts`) — 13 typed presets grouped by Identity / Billing / Geography / Client / Account, each declaring its value kind, sensible operators, option list, and an example value
  - **Attribute** is a grouped `<select>` with a **Custom attribute…** escape hatch for anything not catalogued
  - **Operator** is filtered to the operators that make sense for the chosen attribute (`app_version` offers `>=`, not `contains`)
  - **Value** control is derived from the attribute kind: `True/False` toggle for booleans, closed option list for enums, numeric input for numbers, token chips + clickable suggestions for `in` / `not_in`
  - A newly added condition arrives pre-filled from the catalogue, so the common case needs zero typing
- [x] **Live match preview** — an ordered read-out of every rule (including the unsaved draft) against the current playground context, marking which rule wins and what it serves, backed by a client-side mirror of the evaluator in `previewConditionMatch` / `previewRuleMatch`
- [x] **Per-condition match indicator** — each row reports whether that condition matches the current context
- [x] **Playground presets** — the attribute box has grouped preset chips that append ready-made `key=value` pairs
- [x] **Targeting helpers** (`frontend/src/lib/targeting.ts`) — operator catalogue, value coercion shared by rules and the playground, list-token splitting/joining, draft validation, and attribute-input parsing
- [x] **Workspace state** (`frontend/src/workspace/useProject.ts`) — `rulesFor`, `createRule`, `updateRule`, `deleteRule`, `moveRule`, and attributes threaded into `evaluate`
- [x] **API client** (`frontend/src/api.ts`) — typed `RuleCondition`, `TargetingRule`, and the five rule endpoints
- [x] **Playground attributes** (`frontend/src/components/EvalPlayground.tsx`) — `key=value`/JSON attribute input, human-readable evaluation reasons, and matched rule id
- [x] **Styling** (`frontend/src/App.css`) — `rule-*` block reusing the existing form/button/badge primitives, plus responsive rules
- [x] **Tests** (`frontend/src/test/ruleBuilder.test.tsx`) — 33 tests over the value helpers, the attribute catalogue and match preview, and the builder's create/edit/delete/reorder flows

---

## Phase 4: Standalone Python SDK Client Library

> **Goal:** Provide a zero-latency, in-memory evaluation client library for Python applications.

- [ ] **Package Structure (`packages/catalyst-python-sdk`)**
  - Scaffolding with `pyproject.toml` (`catalyst-sdk`)
  - Standalone Murmur3 hashing and rule evaluation engine
- [ ] **SDK Features**
  - `CatalystClient(sdk_key="cp_prod_...", host="http://...")`
  - **Fetch-on-Load Initialization**: Fetch `/api/v1/bootstrap` once on startup, cache snapshot in-memory
  - **Zero-Latency Evaluation**: `client.is_enabled("flag-key", user_id="user_123", attributes={"email": "..."})` executes in `< 1ms`
  - **Conditional ETag Polling/Reload**: Check for updates using `If-None-Match` (returns `304 Not Modified` when unchanged)
  - Fallback to safe default values on network failure or unexpected flag key
- [ ] **Documentation & Demo Application**
  - Python FastAPI / Flask demo app showing SDK usage
  - Quick-start usage guide and example snippets

---

## Completed in Initialization Step

- [x] Docker Compose setup with PostgreSQL 16 Alpine & Redis 7 Alpine
- [x] Backend FastAPI application with `uv` package management
- [x] Core database models (`Organization`, `Project`, `Environment`, `Flag`, `FlagEnvState`, `TargetingRule`, `ApiKey`, `AuditLog`)
- [x] Deterministic Murmur3 sticky percentage rollout engine
- [x] Emergency Kill Switch with instant short-circuit override
- [x] Base REST APIs: `/healthz`, `/flags`, `/evaluate`, `/batch-evaluate`, `/bootstrap` (ETag/304), `/audit`
- [x] React + Vite + TypeScript dashboard with live health status, environment switcher, kill switches, and evaluation playground
- [x] Automated backend test suite (18 passing unit & integration tests, including authentication and authorization)
