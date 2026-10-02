-- Catalyst Phase 1 schema transition: mutation timestamps
--
-- Apply this file once to a database created before this deploy.  Startup
-- create_all() only ever creates missing tables, so it will not add a column
-- to an existing one; without this script a live database has no
-- flag_env_states.updated_at and the API fails on first read.
--
--   psql "$DATABASE_URL" -f backend/migrations/002_updated_at.sql
--
-- Back up the database before applying it.  Every statement is idempotent, so
-- running the file twice is safe.
--
-- flag_env_states is the one that matters: it is what records when a rollout
-- percentage or kill switch last moved.

BEGIN;

-- ---------------------------------------------------------------------------
-- flag_env_states.updated_at
-- ---------------------------------------------------------------------------
ALTER TABLE flag_env_states ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;
-- A state row cannot predate its flag, so the flag's creation time is the
-- most accurate history available for a pre-existing row.
UPDATE flag_env_states
SET updated_at = (
    SELECT flags.created_at FROM flags WHERE flags.id = flag_env_states.flag_id
)
WHERE updated_at IS NULL;
UPDATE flag_env_states SET updated_at = now() WHERE updated_at IS NULL;
ALTER TABLE flag_env_states ALTER COLUMN updated_at SET NOT NULL;
ALTER TABLE flag_env_states ALTER COLUMN updated_at SET DEFAULT now();

-- ---------------------------------------------------------------------------
-- flags.updated_at
-- ---------------------------------------------------------------------------
ALTER TABLE flags ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;
UPDATE flags SET updated_at = created_at WHERE updated_at IS NULL;
ALTER TABLE flags ALTER COLUMN updated_at SET NOT NULL;
ALTER TABLE flags ALTER COLUMN updated_at SET DEFAULT now();

-- ---------------------------------------------------------------------------
-- environments.created_at
-- ---------------------------------------------------------------------------
ALTER TABLE environments ADD COLUMN IF NOT EXISTS created_at TIMESTAMP;
-- Environments are provisioned with their project, so the project's creation
-- time is the closest true answer.
UPDATE environments
SET created_at = (
    SELECT projects.created_at FROM projects WHERE projects.id = environments.project_id
)
WHERE created_at IS NULL;
UPDATE environments SET created_at = now() WHERE created_at IS NULL;
ALTER TABLE environments ALTER COLUMN created_at SET NOT NULL;
ALTER TABLE environments ALTER COLUMN created_at SET DEFAULT now();

-- ---------------------------------------------------------------------------
-- targeting_rules.created_at / .updated_at
-- ---------------------------------------------------------------------------
ALTER TABLE targeting_rules ADD COLUMN IF NOT EXISTS created_at TIMESTAMP;
ALTER TABLE targeting_rules ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;
UPDATE targeting_rules
SET created_at = (
    SELECT flags.created_at FROM flags WHERE flags.id = targeting_rules.flag_id
)
WHERE created_at IS NULL;
UPDATE targeting_rules SET created_at = now() WHERE created_at IS NULL;
UPDATE targeting_rules SET updated_at = created_at WHERE updated_at IS NULL;
ALTER TABLE targeting_rules ALTER COLUMN created_at SET NOT NULL;
ALTER TABLE targeting_rules ALTER COLUMN created_at SET DEFAULT now();
ALTER TABLE targeting_rules ALTER COLUMN updated_at SET NOT NULL;
ALTER TABLE targeting_rules ALTER COLUMN updated_at SET DEFAULT now();

COMMIT;