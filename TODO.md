# Catalyst — Implementation Roadmap (TODO)

This roadmap outlines upcoming features organized in the recommended implementation sequence. Each phase builds upon the existing core models and evaluation engine established during initialization.

---

## Phase 1: Multi-Tenant Hierarchy (Organizations, Projects & Environments)
> **Goal:** Transition from default auto-provisioned entities to explicit management of Organizations, Projects, and scoped Environments.

- [ ] **Backend: Organization Management**
  - `POST /api/v1/organizations` — Create organization
  - `GET /api/v1/organizations` — List organizations
  - `GET /api/v1/organizations/{id}` — Get organization details
- [ ] **Backend: Projects & Environments**
  - `POST /api/v1/organizations/{org_id}/projects` — Create project
  - Auto-provision standard environments (`dev`, `staging`, `prod`) on project creation
  - `POST /api/v1/projects/{project_id}/environments` — Create custom environment
  - `GET /api/v1/projects/{project_id}/environments` — List project environments
  - Scope all flag queries and mutations strictly by `project_id`
- [ ] **Frontend: Workspace Navigation**
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
  - New "API Keys" tab or settings page
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
- [x] Automated test suite (5 passing unit & integration tests)