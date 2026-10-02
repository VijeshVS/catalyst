-- Catalyst Phase 1 schema transition: drop Flag.archived
--
-- Apply this file once, in the same deploy window as the code that stops
-- reading and writing the column.  Startup create_all() only ever creates
-- missing tables, so it will not drop a column from an existing one.
--
--   psql "$DATABASE_URL" -f backend/migrations/004_drop_flag_archived.sql
--
-- Back up the database before applying it.  Every statement is idempotent.
--
-- Numbering note: this is 004 because Phase 2 owns 003_enable_all.sql. The two
-- are independent, so this one may be applied before or after that one.

BEGIN;

DROP INDEX IF EXISTS ix_flag_project_archived;
ALTER TABLE flags DROP COLUMN IF EXISTS archived;

COMMIT;