New Tasks

- [x] Just like how the targeting rules is minimized, the live evaluation section also must stay minimized, when clicked should open that section
- [x] beside the flag key there must be a button with copy icon to copy the flag when clicked on it
- [x] api keys must be deletable, also remove the line in the bottom of the api key card
- [x] whenever the client is used to check the status of the flag, we mention the attributes everytime like the user_id, email_id etc etc. This is very tedious process. What i should be able to do is after the client is declared be able to attach the user_id and the relevant attributes or mention the attributes and user_id when declaring the client with the CatalystClient

## What shipped

- Live evaluation is a disclosure (`EvalPlayground`), collapsed by default, with `aria-expanded`. The closed header still shows the last decision, or "Not evaluated yet".
- The flag key badge has an icon-only copy button beside it, backed by `frontend/src/lib/clipboard.ts` (`copyText`), which the project id and API key copies now share. It returns a boolean so a denied clipboard is not reported as a copy.
- `DELETE /api/v1/projects/{project_id}/keys/{key_id}` deletes the row and writes an `api_key.deleted` audit entry instead of setting `revoked`. The dashboard shows a Delete action naming the key in the confirmation, and the card's bottom divider is gone. See `docs/adr/002`.
- The SDK accepts `user_id=`/`attributes=` on the constructor and gained `client.for_user(user_id, attributes)`, which returns a `UserScopedClient` sharing the parent's snapshot and transport. Per-call `attributes` merge onto the bound ones. See `docs/adr/001`. Released as `sdk-catalyst 0.4.0`.