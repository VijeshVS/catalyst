# Database schema transitions

The project historically used SQLAlchemy `Base.metadata.create_all()` during
application startup and did not have a migration runner. That remains the
bootstrap behavior for fresh development and self-contained SQLite tests.

`001_auth_ownership.sql` is the explicit one-time transition for an existing
Phase 1 PostgreSQL database. It is intentionally a documented SQL step rather
than a new migration framework being introduced in this phase:

```bash
psql "$DATABASE_URL" -f backend/migrations/001_auth_ownership.sql
```

Back up the database before applying it. The script preserves the legacy
`users.password_hash` and nullable `users.org_id` columns for compatibility,
backfills unambiguous organization ownership, and leaves ownerless legacy
organizations inaccessible until an administrator resolves ownership.

`002_updated_at.sql` and `004_drop_flag_archived.sql` are the Phase 1
transitions. `002` adds the mutation timestamps that startup `create_all()`
cannot add to an existing table; without it a live database has no
`flag_env_states.updated_at` and the API fails on first read. `004` drops
`flags.archived` and must land in the same deploy window as the code that stops
reading it, so no window exists where a query filters on a dropped column or a
live column has no reader. It is numbered 004 because Phase 2 owns
`003_enable_all.sql`; the two are independent and either order applies.

Every statement in all three files is idempotent, so a script that was already
run is safe to run again.
