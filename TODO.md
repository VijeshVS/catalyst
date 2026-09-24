# Catalyst — Implementation Roadmap (TODO)

This roadmap outlines upcoming features organized in the recommended implementation sequence. Each phase builds upon the existing core models and evaluation engine established during initialization.

---

## Phase 0: Landing Page & UX Separation (Navigation Overhaul)

> **Goal:** Replace the cluttered single-page dashboard with a proper multi-page flow:
> a public landing page → organization onboarding → a GitHub-style project list → a project
> detail view that separates flags, environments, and settings into distinct sub-pages.
>
> **Status: 🔲 Not started.**

### 0-A · Public Landing Page (`/`)

The app currently has no landing page — first paint drops straight into the dashboard. A dedicated, visually rich marketing page is needed:

- [ ] **Hero section** — Headline (`"Ship features with confidence"`), sub-headline, and two CTAs: _"Get Started"_ (→ `/app`) and _"View Docs"_.
- [ ] **Feature highlights** — Four cards: Feature Flags, Emergency Kill Switch, Percentage Rollout, SDK-Ready Bootstrap.
- [ ] **How It Works** — Numbered steps: Create org → Create project → Add flags → Evaluate.
- [ ] **Tech stack badge strip** — FastAPI · PostgreSQL · Redis · React.
- [ ] **Footer** — Branding, links.
- [ ] Must use the existing Retro Black & Gold design system from `frontend/src/index.css`.

### 0-B · Routing Setup

> The app has zero client-side routing today. React Router must be introduced.

- [ ] Install and configure **React Router v6** (`react-router-dom`).
- [ ] Define top-level routes:

  | Path | Component |
  |------|-----------|
  | `/` | `LandingPage` |
  | `/app` | Redirect → first org, or org-creation screen |
  | `/app/orgs/:orgId` | `OrgDashboard` (project list) |
  | `/app/orgs/:orgId/projects/:projectId` | `ProjectDetail` (flags tab by default) |
  | `/app/orgs/:orgId/projects/:projectId/environments` | `EnvironmentsPage` |
  | `/app/orgs/:orgId/projects/:projectId/audit` | `AuditPage` (Phase 3+) |
  | `/app/orgs/:orgId/projects/:projectId/settings` | `SettingsPage` (Phase 3+) |

### 0-C · Organization Onboarding Flow

> The current no-org empty state is a plain centered block. Replace it with a proper multi-step onboarding.

- [ ] **Welcome screen** (`/app` — no orgs yet): Illustrated empty state, headline _"Create your first Organization"_, and a prominent CTA.
- [ ] **Create Organization** — **Full-page centered form, not a modal**:
  - Organization name field with live slug preview (e.g. `acme-inc`).
  - Optional short description.
  - Submit navigates to the new org's project list (`/app/orgs/:orgId`).
- [ ] Visiting `/app` when orgs exist should redirect to the last-visited org (persisted in `localStorage`), or to the first org.
- [ ] **Org switcher** in the sidebar: dropdown listing all orgs + _"+ New Organization"_ at the bottom. Remove the "+ Org" button from the top header entirely.

### 0-D · Project List Page (`/app/orgs/:orgId`) — GitHub-style

> Model on GitHub's repository list. Projects are first-class; organizations own them.

- [ ] **Persistent sidebar** (visible across all `/app/**` routes):
  - Org name + avatar initial at the top.
  - Nav links: _Projects_ (active), _Settings_ (future).
  - Org switcher dropdown at the bottom.
- [ ] **Projects grid/list** — each project card shows:
  - Project name (prominent).
  - Auto-created environment badges: `dev` · `staging` · `prod` (+ custom envs, truncated).
  - Total flag count.
  - Last updated timestamp.
  - Clicking the card navigates to `/app/orgs/:orgId/projects/:projectId`.
- [ ] **"+ New Project" flow** — **Full-page form, not a modal**:
  - Project name input.
  - Read-only preview of the three default environments that will be auto-created.
  - On submit, redirect into the new project's flags page.
- [ ] Empty state when no projects exist — illustrated, with _"Create your first project"_ CTA.

### 0-E · Project Detail Page (`/app/orgs/:orgId/projects/:projectId`)

> The current `App.tsx` mixes flags, environments, and workspace state into one 814-line component. Separate them.

- [ ] **Project header** — Breadcrumb (`OrgName / ProjectName`), environment tab strip (replaces the global header env buttons: `DEV` · `STAGING` · `PROD` · custom).
- [ ] **Tab navigation** inside a project:

  | Tab | URL suffix | Content |
  |-----|-----------|---------|
  | Feature Flags | (default, no suffix) | Flag list + create flow |
  | Environments | `/environments` | Env list + custom env creation |
  | API Keys | `/keys` | Phase 2 |
  | Audit Log | `/audit` | Phase 3+ |
  | Settings | `/settings` | Phase 3+ |

- [ ] **Feature Flags sub-page**:
  - Flag cards with kill switch toggle, rollout slider, and evaluation playground — same as today.
  - _"+ Create Flag"_ opens a **slide-over panel** or dedicated sub-page (not a fullscreen modal overlay).
  - Active environment comes from the project header tab strip, not from the global header.
- [ ] **Environments sub-page** (moved out of the current `view === 'environments'` block):
  - Lists all environments; `dev/staging/prod` have an _"auto-created"_ badge, custom ones have a _"custom"_ badge.
  - Shows bootstrap cache version (`v{n}`) per environment.
  - Inline _"+ New Environment"_ form at the top (lowercase identifier validation, e.g. `qa`).
  - _"View flags →"_ button switches to the flags tab with that environment active.
- [ ] **Remove all workspace dropdowns from `<header>`**. The global header should contain only: brand logo + health indicator. All navigation lives in the sidebar and project header.

### 0-F · State Management & Component Refactor

> Required before new pages can be built cleanly.

- [ ] Introduce **`WorkspaceContext`** (`React.createContext`) — owns orgs list, selected org, projects.
- [ ] Introduce **`useProject(projectId)`** custom hook — owns flags, environments, flag actions.
- [ ] Extract pages into `frontend/src/pages/`:
  - `LandingPage.tsx`
  - `OrgDashboard.tsx` (project list)
  - `ProjectDetail.tsx` (tabs + flag list)
  - `EnvironmentsPage.tsx`
- [ ] Extract reusable UI components into `frontend/src/components/`:
  - `Sidebar.tsx`
  - `FlagCard.tsx`
  - `KillSwitchButton.tsx`
  - `RolloutSlider.tsx`
  - `EvalPlayground.tsx`
  - `EnvBadge.tsx`
- [ ] Ensure `npm run lint` and `npm run build` stay green after every step.

---

## Phase 0.5: Authentication (Register / Login)

> **Goal:** Gate the entire dashboard behind user accounts. Users must register or log in before
> they can create organizations, manage projects, or touch any flags. Auth is a prerequisite for
> meaningful audit logs, org ownership, and the API key system in Phase 2.
>
> **Status: 🔲 Not started.**

### 0.5-A · Backend: User Model & Auth Endpoints

- [ ] **`User` model** (new SQLAlchemy model in `backend/app/models/`):
  - `id` (UUID), `email` (unique, indexed), `hashed_password`, `full_name`, `created_at`
- [ ] **Password hashing** — use `passlib[bcrypt]` (add to `pyproject.toml`).
- [ ] **JWT tokens** — use `python-jose[cryptography]`; short-lived access token (15 min) + long-lived refresh token (7 days).
- [ ] **Auth endpoints** under `/api/v1/auth/`:
  | Method & Path | Description |
  |---------------|-------------|
  | `POST /api/v1/auth/register` | Create account (`email`, `password`, `full_name`) |
  | `POST /api/v1/auth/login` | Return `access_token` + `refresh_token` (JSON body, not form) |
  | `POST /api/v1/auth/refresh` | Exchange valid refresh token for a new access token |
  | `GET /api/v1/auth/me` | Return the current authenticated user's profile |
- [ ] **Auth middleware / dependency** — FastAPI `Depends(get_current_user)` injected into every protected route; unauthenticated requests get `401`.
- [ ] **Exempt routes** — `/healthz`, `/api/v1/auth/register`, `/api/v1/auth/login`, `/api/v1/auth/refresh` remain public.
- [ ] **Org ownership** — add `owner_id` FK on `Organization` pointing to `User.id`; users can only read/write their own orgs and their downstream projects/flags.
- [ ] **Audit log enrichment** — add `user_id` (nullable FK → `User`) and `user_email` (denormalized string) to `AuditLog` so every change is attributable.
- [ ] Add auth-related tests to the pytest suite (register, login, protected route rejection, token refresh).

### 0.5-B · Frontend: Auth Pages & Token Management

- [ ] **`/login` page** — Email + password form, _"Don't have an account? Register"_ link, submit → stores tokens → redirects to `/app`.
- [ ] **`/register` page** — Full name + email + password + confirm password, submit → auto-login → redirects to `/app`.
- [ ] **Token storage** — store `access_token` in memory (React context) and `refresh_token` in an `httpOnly`-style approach or `localStorage` (document the tradeoff); auto-refresh on 401 responses.
- [ ] **`AuthContext`** (`React.createContext`) — exposes `user`, `login()`, `logout()`, `register()`; wraps the entire app.
- [ ] **Protected route wrapper** — `<ProtectedRoute>` component that redirects unauthenticated users to `/login`; wraps all `/app/**` routes.
- [ ] **Auth-aware API client** (`frontend/src/api.ts`) — attach `Authorization: Bearer <token>` header to every request; intercept `401` to trigger silent token refresh before retrying once.
- [ ] **User menu in header** — small avatar/initials + dropdown with _"Signed in as {email}"_ and _"Log out"_ action (replaces the future "user/org avatar" placeholder).
- [ ] **`/login` and `/register` use the landing page's Black & Gold design** — they should feel like premium auth screens, not plain browser forms.

### 0.5-C · Security Hardening (Minimum Bar)

- [ ] Rate-limit `/api/v1/auth/login` and `/api/v1/auth/register` (e.g. `slowapi` — 5 req/min per IP).
- [ ] `JWT_SECRET` and token expiry durations read from env vars (`.env.example` updated).
- [ ] Passwords must be ≥ 8 characters (validated in Pydantic schema).
- [ ] Never return `hashed_password` in any response schema.

---

## Phase 1: Multi-Tenant Hierarchy (Organizations, Projects & Environments)

> **Goal:** Transition from default auto-provisioned entities to explicit management of Organizations, Projects, and scoped Environments.
>
> **Status: ✅ Complete.** All items below are implemented. Auto-provisioning of the default
> organization/project was removed; every flag/evaluate/bootstrap/audit call now requires an
> explicit `project_id` (422 when missing, 404 when unknown) and validates that the environment
> belongs to that project. The bootstrap ETag bug was fixed: `Environment.version` is now bumped
> by every snapshot-affecting mutation (flag creation, state/rollout/kill-switch updates), so
> ETags invalidate correctly and stay isolated per project. Covered by 12 passing backend tests;
> frontend `npm run lint` / `npm run build` pass.

- [x] **Backend: Organization Management**
  - `POST /api/v1/organizations` — Create organization
  - `GET /api/v1/organizations` — List organizations
  - `GET /api/v1/organizations/{id}` — Get organization details
- [x] **Backend: Projects & Environments**
  - `POST /api/v1/organizations/{org_id}/projects` — Create project
  - Auto-provision standard environments (`dev`, `staging`, `prod`) on project creation
  - `POST /api/v1/projects/{project_id}/environments` — Create custom environment
  - `GET /api/v1/projects/{project_id}/environments` — List project environments
  - Scope all flag queries and mutations strictly by `project_id`
- [x] **Frontend: Workspace Navigation** _(partially superseded by Phase 0)_
  - Organization & Project dropdown switcher in header navigation
  - "New Project" creation modal with auto-created environment badges
  - Project-level environment management view

---

## Phase 2: API Key Management & SDK Authentication

> **Goal:** Secure the `/bootstrap` and `/evaluate` endpoints with environment-scoped SDK tokens and provide a dashboard for managing keys.

- [ ] **Backend: API Key Service & Endpoints**
  - Generate cryptographically secure keys with prefix format: `cp_<env>_<random32>`
  - Store SHA-256 hash in `api_keys` table; return raw secret key only once upon creation
  - `POST /api/v1/projects/{project_id}/keys` — Generate new API key
  - `GET /api/v1/projects/{project_id}/keys` — List active keys (prefix, env, created_at, status)
  - `DELETE /api/v1/projects/{project_id}/keys/{key_id}` — Revoke key
  - Add `X-SDK-Key` authentication middleware to `/api/v1/bootstrap` and `/api/v1/evaluate`
- [ ] **Frontend: API Keys Dashboard**
  - New "API Keys" tab inside the Project Detail page (Phase 0-E)
  - Create Key modal with environment selector (`dev`, `staging`, `prod`) and descriptive name
  - "Copy to Clipboard" banner with one-time reveal of full secret key
  - Revocation confirmation dialog and status badges (`Active` / `Revoked`)

---

## Phase 3: Rule-Based Targeting & Visual Rule Builder

> **Goal:** Enable targeted beta rollouts based on user attributes (e.g., email domain, user role, country, app version) with an intuitive dashboard builder.

- [ ] **Backend: Rule CRUD Endpoints**
  - `POST /api/v1/flags/{key}/environments/{env}/rules` — Create targeting rule
  - `PUT /api/v1/flags/{key}/environments/{env}/rules/{rule_id}` — Update conditions/priority
  - `DELETE /api/v1/flags/{key}/environments/{env}/rules/{rule_id}` — Delete rule
  - Re-order rule priorities (0 = highest priority)
  - Invalidate environment version on rule mutation to bust SDK cache
- [ ] **Frontend: Visual Rule Builder UI**
  - Expandable "Targeting Rules" section on each Flag Card
  - Condition builder row:
    - Attribute input (e.g. `email`, `role`, `country`, `version`)
    - Operator dropdown (`equals`, `not_equals`, `in`, `contains`, `starts_with`, `ends_with`, `>`, `<`, `>=`, `<=`)
    - Value input (string, comma-separated array, number)
  - Target serve value toggle (`True` / `False`)
  - Integration with the live evaluation playground (pass custom attributes to verify rule match)

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
- [x] Frontend React + Vite + TypeScript dashboard with live health status, environment switcher, kill switches, and evaluation playground
- [x] Automated test suite (12 passing unit & integration tests)