# ADR-001: Carry user context on the SDK client

## Status
Accepted

## Context
- Every check repeated the identity: `client.is_enabled("new-checkout", user_id="user_123", attributes={"email": ...})`. In a request handler that repetition lands on every call site, and a handler checking five flags repeats it five times.
- The identity is usually known once per request, or once per process for a background job. Repetition at the call site is not a missing feature so much as the wrong place to put the data.
- Identity can also vary within one process: a web app serves many users from one long-lived client, so a single hard-bound client cannot be the whole answer.

## Decision
- `CatalystClient` takes optional `user_id` and `attributes`, used as defaults whenever a call omits them.
- `CatalystClient.for_user(user_id, attributes=None)` returns a `UserScopedClient`: a cheap view sharing the parent's transport and snapshot, whose `evaluate`/`is_enabled`/`get_all` take no identity at all.
- A per-call `user_id`/`attributes` overrides or merges onto the bound context rather than replacing it, and `for_user` merges the client's defaults. `for_user` exists only on `CatalystClient`, so a scoped view cannot re-bind and inherit the previous user's attributes.

## Alternatives Considered
- Context managers (`with client.for_user(...)`) were rejected: they make a flag check in a helper function unreachable without threading the context through, and that is exactly where flags get read.
- Requiring `for_user` and leaving the constructor alone was rejected: a single-user script or job should not have to call it at all.
- Constructing a fresh `CatalystClient` per request was rejected as the only mechanism. Construction is free, but every client holds its own snapshot, so per-request clients give up the shared snapshot and the single-flight read that collapses concurrent checks into one request.

## Consequences
- Two supported shapes: bound clients for jobs and scripts, `for_user` for multi-user processes. Existing call sites keep working unchanged, so this is additive rather than a breaking change.
- `for_user` is O(1) and allocates only the view; the snapshot, transport, ETag, and refresh loop stay shared, so a request-scoped view costs no extra round trip.
- A mis-bound client is a new failure mode: an omitted `user_id` on a bound client silently uses the wrong user instead of raising. The SDK still fails closed on evaluation, not on identity, so this shows up as a wrong rollout decision rather than an error.
- The FastAPI demo example now shows `for_user`, since that is the case that motivated it.
