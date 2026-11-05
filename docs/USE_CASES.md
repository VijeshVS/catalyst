# Use Cases & Stakeholder Playbook — Catalyst Feature Management Platform

**Document Status:** Production Specification  
**System:** Catalyst Control Plane, Evaluation Service & Client SDK  

---

## 1. Stakeholders & Roles

| Stakeholder | Primary Objectives | Typical Catalyst Tasks |
|---|---|---|
| **Release Manager / Site Reliability Engineer (SRE)** | Production safety, zero-downtime releases | Toggles emergency kill switches; monitors audit logs; oversees progressive canary stages. |
| **Product Manager (PM)** | Adoption, customer segmentation, beta access | Configures targeting rules (by email, company, tier); moves percentage rollout sliders (1% → 25% → 100%). |
| **Software Engineer (Developer)** | Application integration, latency, reliability | Integrates `catalyst_sdk`; configures in-memory auto-refresh; tests flags in the Evaluation Playground. |
| **Security & Compliance Officer** | Access boundaries, credential lifecycle, auditability | Issues and revokes SDK API keys; verifies tenant isolation; reviews immutable audit records. |

---

## 2. Core Use Cases

### UC-1: Workspace & Environment Provisioning
* **Actor:** Organization Owner / Lead Engineer
* **Objective:** Establish an isolated tenant workspace, provision environments, and issue SDK keys in under 2 minutes.

#### Workflow:
1. **User Registration:** Navigate to `/register` and create an account with email, full name, and password.
2. **Organization Creation:** Create an organization (e.g., `Acme Corp`).
3. **Project Setup:** Create a project (e.g., `storefront-service`). Catalyst automatically provisions three isolated environments:
   * `dev`
   * `staging`
   * `prod`
4. **Custom Environment (Optional):** Add custom lowercase environments (e.g., `qa`, `perf-test`) as needed.
5. **Issue SDK Credentials:** Navigate to the **API Keys** tab and generate an SDK key for `prod`.
   * The raw key (`cp_prod_a1b2c3d4e5f6g7h8i9j0k1...`) is displayed once. Copy and store it in your application's secrets manager.
   * Catalyst stores only the SHA-256 hash in PostgreSQL.

---

### UC-2: Emergency Kill Switch (Incident Blast-Radius Mitigation)
* **Actor:** Release Manager / On-Call SRE
* **Objective:** Instantly shut down a failing feature in production without redeploying code or restarting application servers.

#### Workflow:
1. **Incident Trigger:** Sentry alerts show an error spike originating from the newly deployed `ai-recommendations` feature.
2. **Toggle Kill Switch:**
   * Open the Catalyst Dashboard → Navigate to Project `storefront-service` → Flag `ai-recommendations` → Select tab `prod`.
   * Click the **Emergency Kill Switch** button to set `enabled = false`.
3. **Backend Processing:**
   * The API executes `PATCH /api/v1/flags/ai-recommendations/environments/prod`.
   * Increments `Environment.version` and `FlagEnvState.version`.
   * Drops the Redis snapshot cache key `catalyst:snapshot:<project_id>:prod`.
   * Writes an immutable `AuditLog` entry: `action = "flag.state_updated"`, capturing before and after states.
4. **SDK Propagation:**
   * On the next poll cycle or conditional check, the SDK receives the updated snapshot.
   * `client.is_enabled("ai-recommendations")` immediately returns **`False`** with reason code **`KILL_SWITCH_ACTIVE`**.
   * Production traffic instantly falls back to the safe baseline logic.

---

### UC-3: Progressive Canary Rollout (Sticky Percentage Ramp-Up)
* **Actor:** Product Manager / Release Manager
* **Objective:** Incrementally expose a new feature (e.g., `new-checkout`) from 5% to 50% to 100% of users while guaranteeing that users enrolled at 5% remain enrolled at higher percentages.

#### Workflow:
1. **Initial Deployment (Dark Launch):**
   * Create flag `new-checkout`. Initial rollout is pinned to `0%` (`enabled = true`, `percentage = 0`).
   * Code is safely deployed to production; no customers see the new checkout.
2. **Canary Phase (5%):**
   * Set rollout percentage to `5%` on the dashboard.
   * The frontend debounces slider input and commits the update to the API.
   * For non-targeted users, the SDK computes:
     $$\text{bucket} = (\text{MurmurHash3}(\text{"new-checkout:"} + \text{user\_id}) \ \& \ \text{0xFFFFFFFF}) \pmod{100}$$
   * Users with `bucket < 5` receive `True` (`reason: PERCENTAGE_ROLLOUT`). Users with `bucket >= 5` receive `False` (`reason: PERCENTAGE_OUTSIDE_ROLLOUT`).
3. **Ramp-Up (25% → 50% → 100%):**
   * Metrics indicate stable performance. The PM moves the slider to `25%`, then `50%`, then `100%`.
   * **Monotonicity Guarantee:** Because a user's MurmurHash3 bucket is deterministic and immutable, every user in the initial 5% bucket (`0..4`) stays in the bucket at 25% (`0..24`) and 50% (`0..49`). Users never experience UI flickering or session disruption across requests.

---

### UC-4: Attribute-Based Targeted Release (Beta Testing & Segmentation)
* **Actor:** Product Manager / QA Lead
* **Objective:** Enable a feature exclusively for internal employees and VIP beta testers before public release.

#### Workflow:
1. **Define Rules in Dashboard:**
   * Open flag `beta-search` → Environment `prod` → Rule Builder.
   * **Rule #0 (Priority 0 - Internal Employees):**
     * Condition: `email ends_with @company.com`
     * Action: Serve `True`
   * **Rule #1 (Priority 1 - Enterprise Tier Beta):**
     * Conditions: `tier in enterprise,vip` **AND** `country equals US`
     * Action: Serve `True`
2. **Evaluation Precedence:**
   * Catalyst evaluates rules in strict ascending priority order (Rule #0 before Rule #1).
   * **First Match Wins:** An internal user matching Rule #0 immediately receives `True` (`reason: RULE_AND_ROLLOUT`).
   * **Exclusion Contract:** External users who do not match any rule are immediately filtered out and served `False` (`reason: DEFAULT_VALUE`), without wasting computation on rollout percentages.

---

### UC-5: High-Performance Python SDK Integration
* **Actor:** Application Software Engineer
* **Objective:** Integrate Catalyst into a high-throughput backend (e.g., FastAPI, Django, Flask) with sub-millisecond evaluation latency and zero network overhead per check.

#### Workflow:
1. **Install SDK:**
   ```bash
   pip install sdk-catalyst
   ```
2. **Initialize In-Memory Client:**
   Configure the client once at application startup with `refresh_on_evaluate=False` and launch a background auto-refresh daemon:
   ```python
   from catalyst_sdk import CatalystClient

   client = CatalystClient(
       sdk_key="cp_prod_a1b2c3d4e5f6g7h8i9j0k1",
       project_id="7c9e6679-7425-40de-944b-e07fc1f90ae7",
       env="prod",
       refresh_on_evaluate=False,  # Evaluate purely from memory
   )

   # Poll for updates every 30 seconds in background
   client.start_auto_refresh(interval=30.0)
   ```
3. **Evaluate Flags on Hot Request Paths:**
   ```python
   # Evaluates locally in RAM (< 0.05 ms, 0 network requests)
   if client.is_enabled("new-payment-flow", user_id=user.id, attributes={"email": user.email, "tier": user.tier}):
       return process_new_payment()
   else:
       return process_legacy_payment()
   ```
4. **User-Scoped Client for Web Requests:**
   Bind user context per request without reallocating transport connections:
   ```python
   scoped_client = client.for_user(user.id, {"email": user.email, "country": "US"})
   if scoped_client.is_enabled("feature-a"): ...
   if scoped_client.is_enabled("feature-b"): ...
   ```

---

### UC-6: Pre-Release Verification in Evaluation Playground
* **Actor:** Software Engineer / QA Tester
* **Objective:** Test and verify complex rule logic and rollout behavior without creating mock user accounts or deploying test scripts.

#### Workflow:
1. Open the flag detail page on the Catalyst Dashboard.
2. Expand the **Evaluation Playground** disclosure.
3. Input test context parameters:
   * `User ID`: `test_user_88`
   * `Attributes`:
     ```json
     {
       "email": "alice@company.com",
       "tier": "enterprise",
       "country": "US"
     }
     ```
4. Click **Evaluate**.
5. The dashboard calls `POST /api/v1/evaluate` and displays:
   * **Result:** `True` (Green indicator)
   * **Reason:** `RULE_AND_ROLLOUT`
   * **Matched Rule:** `Rule #0 (Internal Employees)`
   * **Bucket Assignment:** `Bucket 34`

---

### UC-7: Secure API Key Rotation & Revocation
* **Actor:** DevOps Engineer / Security Administrator
* **Objective:** Safely rotate an SDK API key without interrupting production traffic.

#### Workflow:
1. **Generate New Key:**
   * Navigate to the project's **API Keys** tab.
   * Click **Create API Key** for the target environment (e.g., `prod`).
   * Copy the newly generated raw key (`cp_prod_newkey...`).
2. **Update Application Deployment:**
   * Update the application's environment configuration (`CATALYST_SDK_KEY`).
   * Deploy the updated configuration to production servers.
3. **Delete Old Key:**
   * Return to the **API Keys** tab in Catalyst.
   * Click **Delete** next to the old key prefix.
   * The API deletes the key record from PostgreSQL and logs `action: "api_key.deleted"`.
   * Any subsequent request using the old key is rejected with `404 Not Found`.

---

### UC-8: Audit & Compliance Inspection
* **Actor:** Compliance Officer / Engineering Manager
* **Objective:** Trace who modified a production flag, when the mutation occurred, and the exact before/after configuration state.

#### Workflow:
1. Navigate to the project's **Audit Log** page (`/app/orgs/:orgId/projects/:projectId/audit`).
2. Filter or review historical events. Each entry displays:
   * **Timestamp:** Exact UTC execution time.
   * **Actor:** Full name and email of the user who performed the edit.
   * **Action:** Semantic action descriptor (`flag.created`, `flag.state_updated`, `rule.created`, `rule.reordered`, `api_key.created`, `api_key.deleted`).
   * **Environment:** Targeted environment (`prod`, `staging`, `dev`).
   * **State Diff:** Collapsible JSON viewer showing exact `before` and `after` snapshots.
