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
