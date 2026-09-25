-- Catalyst Phase 0.5 schema transition
--
-- Apply this file once to a database created by the Phase 1 application,
-- before deploying the authentication-enabled API.  Fresh development and
-- test databases are created from the current SQLAlchemy metadata by the
-- existing startup create_all/bootstrap path and do not need this script.
--
-- The original users.org_id column is intentionally retained as a nullable
-- legacy column: it is no longer used for authorization.  New users do not
-- need an organization because Phase 1 organization onboarding is explicit.

BEGIN;

ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name VARCHAR(255);
UPDATE users
SET full_name = COALESCE(NULLIF(full_name, ''), split_part(email, '@', 1), 'Catalyst user')
WHERE full_name IS NULL OR full_name = '';
ALTER TABLE users ALTER COLUMN full_name SET NOT NULL;
ALTER TABLE users ALTER COLUMN org_id DROP NOT NULL;

ALTER TABLE organizations ADD COLUMN IF NOT EXISTS description VARCHAR(500);
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS owner_id VARCHAR(36);

-- Backfill ownership only when the legacy one-user-per-organization shape
-- provides an unambiguous candidate. Ownerless legacy organizations remain
-- inaccessible rather than being claimed by an arbitrary account.
UPDATE organizations
SET owner_id = (
    SELECT users.id
    FROM users
    WHERE users.org_id = organizations.id
    ORDER BY users.created_at ASC, users.id ASC
    LIMIT 1
)
WHERE owner_id IS NULL;

CREATE INDEX IF NOT EXISTS ix_organizations_owner_id ON organizations (owner_id);

ALTER TABLE organizations
    ADD CONSTRAINT fk_organizations_owner_id_users
    FOREIGN KEY (owner_id) REFERENCES users (id) ON DELETE SET NULL;

ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS user_id VARCHAR(36);
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS user_email VARCHAR(255);
CREATE INDEX IF NOT EXISTS ix_audit_logs_user_id ON audit_logs (user_id);

ALTER TABLE audit_logs
    ADD CONSTRAINT fk_audit_logs_user_id_users
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL;

COMMIT;
