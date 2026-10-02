-- Catalyst Phase 2 schema transition: evaluation rework
--
-- Apply this file once, in the same deploy window as the code that reads the
-- new columns.  Startup create_all() only ever creates missing tables, so it
-- will not add or drop a column on an existing one.
--
--   psql "$DATABASE_URL" -f backend/migrations/003_enable_all.sql
--
-- Back up the database before applying it.  Every statement is idempotent.
--
-- Ordering constraint: the backfill below reads flags.default_value, so the
-- column drop has to happen after it in the same transaction. Do not split
-- this file.

BEGIN;

-- ---------------------------------------------------------------------------
-- 2-A · "Enable to all users"
-- ---------------------------------------------------------------------------
ALTER TABLE flag_env_states ADD COLUMN IF NOT EXISTS enable_all BOOLEAN;
-- False, not True: no existing flag may change behaviour on deploy.
UPDATE flag_env_states SET enable_all = FALSE WHERE enable_all IS NULL;
ALTER TABLE flag_env_states ALTER COLUMN enable_all SET NOT NULL;
ALTER TABLE flag_env_states ALTER COLUMN enable_all SET DEFAULT FALSE;

-- ---------------------------------------------------------------------------
-- 2-B · percentage becomes a real share, so 0 serves nobody
-- ---------------------------------------------------------------------------
-- Under the OLD evaluator the percentage was only reached when no rule
-- matched, and the fallthrough was default_value rather than false. So:
--
--   default_value = true  -> the flag was serving TRUE to everyone, and a
--                            real share of anything less than 100 would start
--                            turning users off. Set 100 to keep it on.
--   the flag has rules    -> the old evaluator short-circuited on the first
--                            match and the percentage was never reached for
--                            a matched user. Set 100 so a matched user still
--                            receives the rule's value.
--   otherwise             -> the percentage was already the real share and
--                            0 already served nobody. Leave it alone.
--
-- The remaining behaviour change is intentional and unavoidable: a flag with
-- rules whose default_value was true used to serve true to everyone who
-- matched no rule, and under the new filtering model they now get false. That
-- is the point of 2-D, not a migration artefact.
UPDATE flag_env_states s
SET percentage = 100
WHERE s.percentage <> 100
  AND (
    EXISTS (SELECT 1 FROM flags f WHERE f.id = s.flag_id AND f.default_value)
    OR EXISTS (SELECT 1 FROM targeting_rules r WHERE r.flag_id = s.flag_id)
  );

ALTER TABLE flag_env_states ALTER COLUMN percentage SET DEFAULT 100;

-- ---------------------------------------------------------------------------
-- 2-C · default_value has no meaning left under the new model
-- ---------------------------------------------------------------------------
ALTER TABLE flags DROP COLUMN IF EXISTS default_value;

-- ---------------------------------------------------------------------------
-- 2-H · an operator-facing label on each rule
-- ---------------------------------------------------------------------------
-- Empty, not generated: the builder falls back to "Rule #3" for an unnamed
-- rule, and inventing a name in a migration would put text nobody chose into
-- the audit log.
ALTER TABLE targeting_rules ADD COLUMN IF NOT EXISTS name VARCHAR(128);
UPDATE targeting_rules SET name = '' WHERE name IS NULL;
ALTER TABLE targeting_rules ALTER COLUMN name SET NOT NULL;
ALTER TABLE targeting_rules ALTER COLUMN name SET DEFAULT '';

COMMIT;
