# ADR-002: API keys are deleted, not soft-revoked

## Status
Accepted

## Context
- `DELETE /projects/{project_id}/keys/{key_id}` set `revoked = true` and left the row. The dashboard therefore grew a permanent "Revoked" card per retired key with no way to remove it, which is the reason keys were described as undeletable.
- A tombstone keeps the key's name and env in the database after the operator has decided the key is finished with.
- The SDK authenticates by hashing the presented key and comparing hashes, so a key that no longer has a row stops authenticating. Removal does not weaken that.

## Decision
- The `DELETE` endpoint removes the row instead of flagging it, and writes an `api_key.deleted` audit entry carrying the key's name and env.
- `api_keys.revoked` stays as a column and keeps being returned, so old rows and existing clients are unaffected. Nothing sets it any more.
- The dashboard drops the revoked card branch and shows a Delete action with a confirmation.

## Alternatives Considered
- Keeping revoke and adding a separate purge endpoint was rejected: two endpoints for one operator intent, and the purge path would be the only way to clear the list.
- Renaming the response field or dropping the column in the same change was rejected: that is a separate migration, and the flag key security fix is not the place to bundle one.

## Consequences
- The audit trail, not the key table, becomes the record that a key existed. An operator who wants the name and env of a deleted key has to read the audit log.
- A deleted key returns `404 API key not found` where a revoked one returned `401`, so a stale key's error message changes. The key is equally dead either way.
- `list_api_keys(active_only=False)` and the `revoked` check in `deps.py` are now no-ops. They are left in place as defence in depth rather than removed alongside a change that has nothing to gain from deleting them.
