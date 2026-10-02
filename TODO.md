# Catalyst — Roadmap 2.0

**Status:** Phase 0 done. Phases 1 and 2 are not implemented yet.

The original roadmap is finished. This one has three parts: fix an API key
security problem, add timestamps, and **rework how flags are evaluated** so the
behaviour matches what the product is supposed to do.

The evaluation rework is the big one. It changes what real users receive, so it
has to be right before anything is built on top of it.

### Status

| Phase | What it is | Status |
|---|---|---|
| [0](#phase-0--api-key-security-fix) | API key security fix | **Done** |
| [1](#phase-1--updated_at-timestamps) | `updated_at` timestamps | **Active** |
| [2](#phase-2--rework-how-flags-are-evaluated) | Rework evaluation | **Active** |

---

# Phase 0 — API key security fix

**Status: Done.**

## The problem, in plain words

An API key looks like `cp_prod_a1b2c3d4e5f6g7h8i9j0k1`. You see the whole thing
once, when you create it. After that Catalyst keeps only a **hash** — a one-way
fingerprint, so the real key cannot be recovered from the database.

Alongside the hash, Catalyst stored a **12-character nickname** (`cp_prod_a1b2c`) to
help you tell keys apart in the list. That nickname is shown on the Keys tab.

**The bug:** when an SDK presented a key, the code checked the hash first, and if
that failed it **also accepted the nickname as if it were the real key**. The
nickname was meant to be a harmless label, but it worked as a password.

So today, anyone who can open the API Keys tab can use a key's nickname to read
your project's flags.

## What to change

### 0-A · Only the full key may authenticate

- [x] Delete the fallback lookup in `backend/app/services/api_keys.py:87-89` that
      matches against the stored `prefix` column. Authentication must work **only**
      by hashing the presented key and comparing it to the stored hash.
- [x] Delete `get_api_key_by_prefix` (`api_keys.py:93-96`); call
      `get_api_key_by_raw_key` directly from `backend/app/api/v1/deps.py:126`.
- [x] Fix the two comments describing the abandoned design: `deps.py:107` and
      `backend/app/schemas/schemas.py:343`.
- [x] **The stored hash stays.** The full key is already in the database as a
      one-way hash. Keeping it hashed means a stolen backup or a SQL injection
      cannot reveal anyone's key. Do not change this to plain text.

### 0-B · Stop returning any part of the key

- [x] Remove `prefix` from `ApiKeyResponse` (`schemas.py:336-345`).
- [x] Keys stay distinguishable in the list by **name**, **environment**,
      **status**, and **created date** — all already in the response.
- [x] The one-time full-key reveal at **creation** is unchanged. That should stay
      the only moment the real key is ever shown.
- [x] **Frontend: `frontend/src/pages/ApiKeysPage.tsx` renders the prefix.** Remove
      it. The create flow's one-time reveal and copy button stay as they are.
- [x] The `ApiKey.prefix` column can stay in the database — it is now just a
      non-secret label. Dropping the column is a schema change and can ride along
      with a later migration.

### 0-C · Reissue existing keys

Every existing key's nickname has been visible on the Keys tab to everyone with
project access, so treat those keys as compromised:

1. Revoke the old key.
2. Create a new key.
3. Put the new key in your app's config wherever the old one was.
4. Redeploy the app.

Skipping this leaves a small risk that someone copied a nickname before the fix
landed.

### 0-D · Default the environment to `dev` everywhere

`/api/v1/bootstrap` defaults to `prod` (`api/v1/bootstrap.py:25`) while
`/api/v1/evaluate` defaults to `dev` (`schemas.py:83`). Two endpoints in one system
defaulting to different environments is a trap in a product built around
environment isolation.

- [x] Change `/bootstrap` to default to `dev`.
- [x] Change the Python SDK's default from `env="prod"` to `env="dev"`
      (`packages/catalyst-python-sdk/src/catalyst_sdk/client.py:114`).
- [x] Document the default in one place, and check the SDK README and
      `frontend/src/pages/DocsPage.tsx` for any place that still says `prod`.

### 0-E · Clean up dead code

- [x] `get_sdk_key_from_header` (`deps.py:111-113`) — defined, never used.
- [x] `verify_api_key` (`api_keys.py:34-40`), `revoke_api_key` (`:127-142`),
      `get_api_key_or_404` (`:145-156`) — defined, never called; the endpoint
      re-implements the logic inline.
- [x] `random_bytes` at `api_keys.py:20` is assigned and never used.
- [x] `revoke_api_key_endpoint` commits twice (`projects.py:201` then `:216`),
      writing the revoke and its audit row as two transactions. Combine.
- [x] `create_api_key` accepts `user_id` and `user_email` (`api_keys.py:48-49`)
      and discards them, because `ApiKey` has no such columns. Either store them
      or stop accepting them.

### Done when

- [x] A 12-character nickname in `X-SDK-Key` is rejected with `404`.
- [x] The full key still authenticates.
- [x] The keys list response and the keys page show no part of any key.
- [x] `/evaluate`, `/bootstrap`, and the SDK all default to `dev`.
- [x] Every change has a test.

---

# Phase 1 — `updated_at` timestamps

**Status: Active.** Small, but needed for the canary later.

## The problem, in plain words

Most tables have no timestamps. You cannot ask when a rollout started or when
someone last moved a slider — that information does not exist.

The visible symptom: every project tile shows a "last updated" time, but it is
**fake**. It is calculated as the newest flag *creation* date
(`api/v1/organizations.py:34-37`), so moving a rollout slider never changes it.

## What to change

### 1-A · Add `updated_at` to `FlagEnvState` 🗄️

`FlagEnvState` holds the kill switch and rollout percentage per flag per
environment. It has **no timestamps at all**.

- [ ] Add an `updated_at` column, defaulting to now.
- [ ] Set it on **every** state mutation — kill switch and rollout percentage
      alike, so moving the slider is recorded.
- [ ] Write `backend/migrations/002_updated_at.sql` and apply it to Neon by hand.
      **Startup `create_all()` only creates missing tables — it never adds a column
      to an existing one**, so the model change alone does nothing to a live
      database. See `backend/migrations/README.md`.

### 1-B · Add timestamps to the other mutable tables 🗄️

- [ ] `Flag.updated_at` — bumped on create and on any later edit.
- [ ] `TargetingRule.created_at` and `.updated_at`.
- [ ] `Environment.created_at`.
- [ ] Can follow 1-A; 1-A is the one that matters.

### 1-C · Make the project "last updated" honest

- [ ] Once 1-B lands, change `ProjectResponse.updated_at` (`schemas.py:150`) to
      use the real newest `Flag.updated_at` instead of `max(flag.created_at)`.
- [ ] Test: change a rollout, confirm the project's `updated_at` moved.

### 1-D · Remove the `archived` column 🗄️

**Decision: delete the column. Archiving is not a requirement and will not be
built later.** It is not being deferred — there is no archive or delete concept
in the product, no plan for one, and no button anywhere in the UI. Keeping the
column would ship a half-feature that reads like working functionality and
cannot be reached.

`Flag.archived` is a write-never field. `FlagUpdate` (`schemas.py:282`) is the
only schema that accepts it, it is used by no endpoint, and `FlagCreate` has no
such field. Two read paths filter on it anyway:

- [ ] Drop `Flag.archived` (`models.py:148`) and the `ix_flag_project_archived`
      index that pairs it with `project_id` (`models.py:165`).
- [ ] Drop the `archived` query parameter and the `Flag.archived == archived`
      filter from `list_flags` (`api/v1/flags.py:84`, `:91`). The endpoint
      already behaves as if nothing is ever archived, so the list keeps
      returning everything it returns today.
- [ ] Remove `archived` from `FlagResponse` (`schemas.py:294`). Delete
      `FlagUpdate` (`schemas.py:282`) and its export in
      `backend/app/schemas/__init__.py` outright rather than stripping one field
      out of a schema nothing references.
- [ ] `services/snapshots.py:122` loses its `Flag.archived == False` clause.
- [ ] `api/v1/organizations.py:46` — `flag_count` becomes a plain count, with
      no `if not flag.archived` test.
- [ ] `frontend/src/api.ts:92` — remove `archived` from the `Flag` type.
- [ ] Migration `004_drop_flag_archived.sql` (numbered after Phase 2's
      `003_enable_all.sql`; the two are independent, so it can run first if the
      numbering matters). Startup `create_all()` only ever
      creates missing tables, so it will not drop the column from Neon; apply
      the migration by hand, same as 1-A.
- [ ] Code changes and the migration ship in **one** deploy window. A deploy
      that drops the column while a query still filters on it (or the reverse)
      breaks the flag list and the bootstrap snapshot in between.
- [ ] Fix the three docs that promise archiving, since they describe behaviour
      that will not exist: `docs/PRD.md:89`, `docs/TECH_SPEC.md:103`, `:153`,
      `:185`, `:270`, and `docs/USE_CASES.md:165`.
- [ ] `frontend/src/test/ruleBuilder.test.tsx:30` sets `archived: false` on its
      fixture flag; drop the field.

---

# Phase 2 — Rework how flags are evaluated

**Status: Active. The most important phase in this document.** It changes what
real users receive from the product, and the SDK has a copy of the same logic that
must be changed in lockstep.

## What we want

Two switches, in priority order:

1. **Emergency kill switch — highest priority.** If it is on, **everyone gets
   false.** Nothing else is even looked at.
2. **Enable to all users.** If the kill switch is off and this is on, **everyone
   gets true** — no rules, no percentage, nothing.
3. Otherwise, **rules and percentage** decide.

And the percentage becomes a real share: **0% means nobody gets it, 100% means
everybody does.**

## The full decision table

| Kill switch | Enable all | Rules | Percentage | Who gets the feature |
|---|---|---|---|---|
| **ON** | anything | anything | anything | **nobody** — everyone gets false |
| off | **ON** | anything | anything | **everybody** — no targeting at all |
| off | off | none | 100% | everybody |
| off | off | none | 0% | nobody |
| off | off | none | 50% | 50% of everyone |
| off | off | someone matches | 50% | 50% of the matched users |
| off | off | someone matches | 100% | the matched users, getting the rule's value |
| off | off | **no rule matches** | anything | **nobody** — rules filtered them out |

The last row is the "filtering" behaviour: if rules are defined and you match
none of them, you are not in the population and you do not get the feature.

## What the code does today

`backend/app/services/evaluator.py:140-161`:

```python
if not enabled:
    return default_value, "KILL_SWITCH_ACTIVE", None            # :141

for rule in sorted(rules, key=lambda item: item.get("priority", 0)):
    if match_rule(rule.get("conditions", []), attributes):
        return rule.get("serve", True), "RULE_MATCH", rule.get("id")   # :152

if percentage > 0:                                              # :155
    if get_user_bucket(flag_key, user_id) < percentage:
        return True, "PERCENTAGE_ROLLOUT", None                 # :157

return default_value, "DEFAULT_VALUE", None                     # :161
```

Four things are wrong with this against the table above:

1. **A matching rule short-circuits everything.** The `return` at line 152 means
   the percentage at line 155 is **never reached**. Rules and percentage are two
   separate overrides, not a filter followed by a split.
2. **0% and 100% behave identically.** Both skip line 155 and fall through to
   `default_value`. The slider's ends mean the same thing.
3. **`default_value` is a third source of truth.** The fallthrough value is
   whatever the user picked when creating the flag, not something the rules or the
   slider control.
4. **The SDK has an identical copy** at
   `packages/catalyst-python-sdk/src/catalyst_sdk/evaluator.py:220-254`, held in
   agreement by a differential test suite
   (`backend/tests/test_sdk_parity.py`) that fuzzes both against each other.

## What to change

### 2-A · Add the "enable to all users" switch 🗄️

- [ ] Add `enable_all: Boolean` to `FlagEnvState` (`models.py:169-196`).
- [ ] **Default it to `false`** so no existing flag changes behaviour the moment
      this deploys.
- [ ] Add it to the bootstrap snapshot payload so the SDK can evaluate it locally
      without a server round trip.
- [ ] Migration `003_enable_all.sql`.

### 2-B · Change the percentage to a real share 🗄️

- [ ] `FlagEnvState.percentage` becomes the share of eligible users who receive
      the feature. **0% serves nobody.** Remove the `if percentage > 0` guard.
- [ ] Change the column default from `0` to `100`.
- [ ] The migration must **explicitly set the percentage on every existing row**
      rather than relying on the default, so that no flag changes behaviour:
      - rows where `default_value=False` → set `percentage=0` (preserves today's
        behaviour: off)
      - rows where `default_value=True` → set `percentage=100` (preserves today's
        behaviour: on)
      - rows with a non-zero percentage → leave alone
- [ ] Write the migration so it is idempotent and can be run twice safely.

### 2-C · Remove `default_value` 🗄️

Under the new model nothing needs it: the kill switch means false, and the
percentage means true. Keeping a field with one vestigial meaning is how the
current confusion happened.

- [ ] Drop `Flag.default_value` (`models.py:147`).
- [ ] Remove it from `FlagCreate` (`schemas.py:277`), `FlagUpdate` (`:281`), and
      `FlagResponse` (`:290`).
- [ ] Remove the on/off choice from the create-flag form
      (`frontend/src/components/FlagCreatePanel.tsx`) and from `api.ts`.
- [ ] Remove `defaultValue` from the bootstrap payload and from
      `packages/catalyst-python-sdk/src/catalyst_sdk/snapshot.py:22`.
- [ ] Update the SDK evaluator, `DocsPage.tsx`, and the SDK README.
- [ ] Migration to drop the column, after 2-B has read it.

### 2-D · Rewrite `evaluate_flag` 🔴

New order, matching the table above:

```python
def evaluate_flag(flag, rules, user_id, attributes, percentage, enable_all):
    if not enabled:                                   # 1. kill switch, highest priority
        return False, "KILL_SWITCH_ACTIVE", None

    if enable_all:                                    # 2. everyone, no targeting
        return True, "ENABLE_ALL_USERS", None

    matched = first matching rule by ascending priority # 3. who is in the population

    if matched is None and rules_exist:
        return False, "DEFAULT_VALUE", None           #    filtered out

    bucket = get_user_bucket(flag_key, user_id)       # 4. split the population

    if bucket < percentage:
        return (matched.serve if matched else True), \
               "RULE_AND_ROLLOUT" if matched else "PERCENTAGE_ROLLOUT", \
               matched.id if matched else None

    return (not (matched.serve if matched else True)), \
           "RULE_OUTSIDE_ROLLOUT" if matched else "PERCENTAGE_OUTSIDE_ROLLOUT", \
           matched.id if matched else None
```

- [ ] The percentage applies to the **filtered** population, exactly as specified.
- [ ] A matching rule **and** a percentage combine rather than override: the
      percentage splits the matched group, and those outside it get the **opposite**
      of the rule's value.
- [ ] The same `bucket` is used everywhere. It is
      `murmur3(f"{flag_key}:{user_id}") % 100` (`evaluator.py:52-58`) — a fixed
      number per user, independent of the percentage. So **raising the percentage
      only ever adds users; it can never remove one.** That is what makes a gradual
      rollout safe. It is not obvious from reading the code, so it needs an
      explicit test.
- [ ] Reason codes change. Remove `RULE_MATCH`; add `ENABLE_ALL_USERS`,
      `RULE_AND_ROLLOUT`, `RULE_OUTSIDE_ROLLOUT`, `PERCENTAGE_OUTSIDE_ROLLOUT`.
      An operator debugging a rollout needs to tell "your rule did not match" and
      "your rule matched and you fell outside the percentage" apart — two very
      different problems.
- [ ] `DEFAULT_VALUE` is kept, but it now only ever means `false`.

### 2-E · The SDK must fail closed 🔴

If the SDK cannot reach Catalyst, it serves `false`. Always.

- [ ] Remove the last-good-snapshot fallback in
      `packages/catalyst-python-sdk/src/catalyst_sdk/client.py` — a failed read
      inside `evaluate()` must resolve to `false`, not to the in-memory snapshot.
- [ ] Remove the disk-cache fallback (`client.py:518-535`) and
      `~/.cache/catalyst` entirely, along with `clear_cache()`, `cache_path`, and
      `CATALYST_CACHE_DIR`.
- [ ] Keep the conditional read. A `304 Not Modified` is a **successful** read —
      the snapshot in memory stays valid and keeps serving. Only genuine failures
  flip to false.
- [ ] Keep the single-flight and failure-backoff behaviour. Unchanged.
- [ ] `default_value` as a client constructor argument
      (`client.py:129`, default `False`) also disappears with 2-C.
- [ ] Update `AGENTS.md`, which currently documents the disk cache as a feature.
- [ ] Update the SDK tests that assert the cached fallback, and the README section
      describing it.

### 2-F · Mirror everything in the SDK 🔴

- [ ] Same rewrite in
      `packages/catalyst-python-sdk/src/catalyst_sdk/evaluator.py`.
- [ ] Export the new reason constants from
      `packages/catalyst-python-sdk/src/catalyst_sdk/__init__.py`.
- [ ] Parse the new snapshot fields in
      `packages/catalyst-python-sdk/src/catalyst_sdk/snapshot.py`.
- [ ] Extend `backend/tests/test_sdk_parity.py` so the differential fuzz covers
      **both switches and rules and a percentage on the same flag**, not each in
      isolation. This suite is the only thing guaranteeing the two
      implementations never drift apart.

### 2-G · Tests that assert the old behaviour must be rewritten 🔴

These currently pass and will start failing. That is expected, not a surprise:

- [ ] `backend/tests/test_evaluator.py:32` — rule targeting
- [ ] `backend/tests/test_evaluator.py:72` — percentage distribution
- [ ] `backend/tests/test_evaluator.py:138` —
      `test_rules_beat_the_percentage_rollout` asserts the **old** short-circuit
- [ ] `packages/catalyst-python-sdk/tests/test_evaluator.py:138` — same test name
- [ ] Any SDK test asserting the disk-cache fallback (2-E)
- [ ] The new tests: both switches at once, 0% and 100% endpoints, the flip
      behaviour, monotonicity, and the filtered-out case

### 2-H · Frontend 🔴

Everything here encodes the old behaviour and will be wrong after 2-D:

- [ ] `frontend/src/components/FlagCard.tsx` — add the "Enable to all users"
      control. Both switches must be visible and their priority obvious, since one
      silently overrides the other.
- [ ] `frontend/src/components/RolloutSlider.tsx` — the disabled state currently
      keys off the kill switch only (`:37-40` in `FlagCard`). Both switches now
      bypass the slider.
- [ ] `frontend/src/components/EvalPlayground.tsx` — `REASON_LABELS` (`:12-18`),
      which turns a reason code into the sentence a user reads.
- [ ] `frontend/src/lib/attributeCatalog.ts` — `previewRuleMatch` (`:364`), the
      client-side copy of the evaluator behind the rule builder's match preview.
- [ ] `frontend/src/components/RuleBuilder.tsx` — the preview's closing line
      ("Nothing matches, so the percentage rollout and then the flag default
      decide") is now wrong; it must explain the real outcome.
- [ ] `frontend/src/components/FlagCreatePanel.tsx` — drop the `default_value`
      toggle (2-C).
- [ ] `frontend/src/api.ts` — remove `default_value`; add `enable_all` and the
      new reason codes.
- [ ] `frontend/src/test/ruleBuilder.test.tsx` (450 lines) and
      `rolloutSlider.test.tsx` will need updating.

**On the match preview and hashing:** showing "you are inside/outside the rollout"
for the specific user in the playground would require porting MurmurHash3 to
TypeScript and keeping it byte-identical to the server's. **Skip it.** The preview
explains the rules and percentage in general terms, and the playground — which
calls the real `/evaluate` endpoint — gives the definitive answer for the specific
user. Revisit only if users need it directly.

- [ ] Enforce the 25-condition limit in the builder UI. The server caps at 25
      (`schemas.py:227`) but the "Add condition" button
      (`RuleBuilder.tsx:517-519`) is unlimited, so you can build something that
      looks valid and then fail on save.
- [ ] Use the `priority` field the API already accepts (`schemas.py:231`, `:241`)
      and the builder never sends — ordering is up/down buttons only.
- [ ] Add rule labels. `TargetingRule` has no name (`models.py:199-220`), so the
      builder shows "Rule #3".

### 2-I · Documentation 🔴

- [ ] `backend/app/schemas/schemas.py` — the `reason` documentation on
      `EvaluateResponse` (`:86-91`).
- [ ] `frontend/src/pages/DocsPage.tsx` — the precedence section.
- [ ] `packages/catalyst-python-sdk/README.md` — same, hand-synced.
- [ ] `AGENTS.md` — the evaluation and SDK sections describe the old model and the
      disk cache.

### Done when

- [ ] The decision table above is reproduced exactly by tests, row by row.
- [ ] The server, the SDK, the parity suite, the frontend preview, and all three
      sets of docs describe the same behaviour.
- [ ] A flag with both switches off, a rule matching, and 40% serves the rule's
      value to 40% of matched users and the opposite value to the rest.
- [ ] Raising a percentage never removes a user.
- [ ] An unreachable Catalyst serves `false` from the SDK, with no cached fallback
      anywhere in the code.
- [ ] No production flag changed behaviour as a side effect of the migration.
