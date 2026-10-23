CREATE TABLE IF NOT EXISTS "Users" (
    user_id        SERIAL PRIMARY KEY,
    username       VARCHAR(64)  NOT NULL UNIQUE,
    email          VARCHAR(254) NOT NULL UNIQUE,
    password_hash  TEXT         NOT NULL,
    role           VARCHAR(20)  NOT NULL
                   CHECK (role IN ('admin', 'manager', 'staff')),
    is_active      BOOLEAN      NOT NULL DEFAULT TRUE,
    last_login_at  TIMESTAMPTZ,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

ALTER TABLE "Users"
    ADD COLUMN IF NOT EXISTS mfa_secret TEXT,
    ADD COLUMN IF NOT EXISTS mfa_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS mfa_recovery_hashes JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS mfa_failed_attempts INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS mfa_locked_until TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS mfa_pending_expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS mfa_challenge_hash TEXT;

ALTER TABLE "Users" DROP CONSTRAINT IF EXISTS users_role_check;
UPDATE "Users" SET role = 'staff' WHERE role = 'store_manager';
ALTER TABLE "Users" ADD CONSTRAINT users_role_check
    CHECK (role IN ('admin', 'manager', 'staff'));

CREATE TABLE IF NOT EXISTS "Projects" (
    project_id   SERIAL PRIMARY KEY,
    name         VARCHAR(200) NOT NULL,
    description  TEXT,
    status       VARCHAR(24) NOT NULL DEFAULT 'draft'
                 CHECK (status IN (
                     'planned', 'draft', 'pending_approval', 'approved', 'active',
                     'on_hold', 'completed', 'cancelled', 'rejected'
                 )),
    manager_id   INTEGER REFERENCES "Users"(user_id),
    created_by   INTEGER NOT NULL REFERENCES "Users"(user_id),
    start_date   DATE,
    due_date     DATE,
    end_date     DATE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (end_date IS NULL OR start_date IS NULL OR end_date >= start_date)
);

CREATE TABLE IF NOT EXISTS "Project_Staff_Assignments" (
    project_id   INTEGER NOT NULL REFERENCES "Projects"(project_id) ON DELETE CASCADE,
    user_id      INTEGER NOT NULL REFERENCES "Users"(user_id) ON DELETE CASCADE,
    assigned_by  INTEGER REFERENCES "Users"(user_id) ON DELETE SET NULL,
    assigned_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (project_id, user_id)
);

CREATE OR REPLACE FUNCTION projects_sync_compat() RETURNS trigger AS $$
BEGIN
    IF NEW.created_by IS NULL THEN NEW.created_by := NEW.manager_id; END IF;

    IF TG_OP = 'INSERT' THEN
        IF NEW.end_date IS NULL THEN NEW.end_date := NEW.due_date; END IF;
        IF NEW.due_date IS NULL THEN NEW.due_date := NEW.end_date; END IF;
    ELSE
        IF NEW.end_date IS DISTINCT FROM OLD.end_date THEN
            NEW.due_date := NEW.end_date;
        ELSIF NEW.due_date IS DISTINCT FROM OLD.due_date THEN
            NEW.end_date := NEW.due_date;
        END IF;
    END IF;

    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS projects_sync_compat_trg ON "Projects";
CREATE TRIGGER projects_sync_compat_trg
    BEFORE INSERT OR UPDATE ON "Projects"
    FOR EACH ROW EXECUTE FUNCTION projects_sync_compat();

UPDATE "Projects" SET manager_id = NULL
WHERE status IN ('draft', 'pending_approval', 'rejected') AND manager_id IS NOT NULL;
CREATE TABLE IF NOT EXISTS "Tasks" (
    task_id      SERIAL PRIMARY KEY,
    project_id   INTEGER NOT NULL REFERENCES "Projects"(project_id) ON DELETE CASCADE,
    assignee_id  INTEGER REFERENCES "Users"(user_id),
    title        VARCHAR(200) NOT NULL,
    status       VARCHAR(20)  NOT NULL DEFAULT 'todo'
                 CHECK (status IN ('todo', 'in_progress', 'done')),
    due_date     DATE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS "Assets" (
    asset_id    SERIAL PRIMARY KEY,
    asset_type  VARCHAR(10)  NOT NULL CHECK (asset_type IN ('tool', 'device', 'vehicle')),
    name        VARCHAR(150) NOT NULL,
    category    VARCHAR(100),
    brand       VARCHAR(100),
    serial_no   VARCHAR(100) UNIQUE,
    condition   VARCHAR(50)  NOT NULL DEFAULT 'good',
    status      VARCHAR(20)  NOT NULL DEFAULT 'available'
                CHECK (status IN ('available', 'assigned', 'maintenance', 'retired')),
    image_path  VARCHAR(255),
    added_by    INTEGER REFERENCES "Users"(user_id),
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS "Vehicle_Details" (
    asset_id  INTEGER PRIMARY KEY REFERENCES "Assets"(asset_id) ON DELETE CASCADE,
    plate_no  VARCHAR(20) NOT NULL UNIQUE,
    make      VARCHAR(100),
    model     VARCHAR(100),
    mileage   INTEGER NOT NULL DEFAULT 0 CHECK (mileage >= 0)
);

CREATE TABLE IF NOT EXISTS "Requests" (
    request_id    SERIAL PRIMARY KEY,
    requester_id  INTEGER NOT NULL REFERENCES "Users"(user_id),
    asset_id      INTEGER REFERENCES "Assets"(asset_id),
    project_id    INTEGER REFERENCES "Projects"(project_id),
    item_name     VARCHAR(200),
    reason        TEXT,
    status        VARCHAR(20) NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'approved', 'rejected', 'fulfilled', 'cancelled')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (asset_id IS NOT NULL OR item_name IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS "Asset_Assignments" (
    assignment_id    SERIAL PRIMARY KEY,
    asset_id         INTEGER NOT NULL REFERENCES "Assets"(asset_id),
    user_id          INTEGER NOT NULL REFERENCES "Users"(user_id),
    project_id       INTEGER REFERENCES "Projects"(project_id),
    request_id       INTEGER REFERENCES "Requests"(request_id),
    assigned_by      INTEGER REFERENCES "Users"(user_id),
    assigned_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    due_back         DATE,
    returned_at      TIMESTAMPTZ,
    return_condition VARCHAR(50)
);

CREATE UNIQUE INDEX IF NOT EXISTS one_open_assignment_per_asset
    ON "Asset_Assignments"(asset_id) WHERE returned_at IS NULL;
CREATE INDEX IF NOT EXISTS assets_status_idx ON "Assets"(status);
CREATE INDEX IF NOT EXISTS assets_type_idx   ON "Assets"(asset_type);

CREATE TABLE IF NOT EXISTS "Procurements" (
    procurement_id  SERIAL PRIMARY KEY,
    request_id      INTEGER UNIQUE REFERENCES "Requests"(request_id) ON DELETE SET NULL,
    requested_by    INTEGER NOT NULL REFERENCES "Users"(user_id),
    item_name       VARCHAR(200) NOT NULL,
    quantity        INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
    estimated_cost  NUMERIC(12, 2) NOT NULL CHECK (estimated_cost >= 0),
    supplier        VARCHAR(200),
    status          VARCHAR(20) NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'level_1', 'level_2', 'approved', 'rejected')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS "Approvals" (
    approval_id     SERIAL PRIMARY KEY,
    procurement_id  INTEGER NOT NULL REFERENCES "Procurements"(procurement_id) ON DELETE CASCADE,
    level           SMALLINT NOT NULL CHECK (level IN (1, 2)),
    approver_id     INTEGER REFERENCES "Users"(user_id),
    decision        VARCHAR(10) NOT NULL DEFAULT 'pending'
                    CHECK (decision IN ('pending', 'approved', 'rejected')),
    comment         TEXT,
    decided_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (procurement_id, level)
);

CREATE TABLE IF NOT EXISTS "Disbursements" (
    disbursement_id    SERIAL PRIMARY KEY,
    procurement_id     INTEGER UNIQUE REFERENCES "Procurements"(procurement_id),
    reference          VARCHAR(100) UNIQUE,
    payee              VARCHAR(200),
    recipient_phone    VARCHAR(16),
    amount             NUMERIC(12, 2) NOT NULL CHECK (amount >= 0),
    currency           VARCHAR(3) NOT NULL DEFAULT 'KES',
    description        TEXT NOT NULL DEFAULT '',
    status             VARCHAR(12) NOT NULL DEFAULT 'pending'
                       CHECK (status IN ('pending', 'processing', 'success', 'paid', 'failed')),
    provider           VARCHAR(30) NOT NULL DEFAULT 'legacy_simulator',
    daraja_conversation_id            VARCHAR(100),
    daraja_originator_conversation_id VARCHAR(100),
    daraja_transaction_id             VARCHAR(100),
    provider_status_message TEXT,
    payment_reference  VARCHAR(100),
    failure_reason     TEXT,
    submitted_by       INTEGER REFERENCES "Users"(user_id),
    paid_by            INTEGER REFERENCES "Users"(user_id),
    paid_at            TIMESTAMPTZ,
    receipt_ref        VARCHAR(100),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (procurement_id IS NOT NULL OR (reference IS NOT NULL AND payee IS NOT NULL)),
    CHECK (reference IS NULL OR amount > 0)
);

ALTER TABLE "Disbursements"
    ADD COLUMN IF NOT EXISTS recipient_phone VARCHAR(16),
    ADD COLUMN IF NOT EXISTS provider VARCHAR(30) NOT NULL DEFAULT 'legacy_simulator',
    ADD COLUMN IF NOT EXISTS daraja_conversation_id VARCHAR(100),
    ADD COLUMN IF NOT EXISTS daraja_originator_conversation_id VARCHAR(100),
    ADD COLUMN IF NOT EXISTS daraja_transaction_id VARCHAR(100),
    ADD COLUMN IF NOT EXISTS provider_status_message TEXT,
    ADD COLUMN IF NOT EXISTS submitted_by INTEGER REFERENCES "Users"(user_id);

CREATE UNIQUE INDEX IF NOT EXISTS disbursements_daraja_conversation_idx
    ON "Disbursements"(daraja_conversation_id)
    WHERE daraja_conversation_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS disbursements_daraja_originator_idx
    ON "Disbursements"(daraja_originator_conversation_id)
    WHERE daraja_originator_conversation_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS disbursements_daraja_transaction_idx
    ON "Disbursements"(daraja_transaction_id)
    WHERE daraja_transaction_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS "Payment_History" (
    history_id         SERIAL PRIMARY KEY,
    disbursement_id    INTEGER NOT NULL REFERENCES "Disbursements"(disbursement_id) ON DELETE CASCADE,
    reference          VARCHAR(100),
    payment_reference  VARCHAR(100),
    amount             NUMERIC(12, 2) NOT NULL,
    currency           VARCHAR(3) NOT NULL,
    status             VARCHAR(12) NOT NULL,
    message            TEXT NOT NULL DEFAULT '',
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS "Disbursement_Audit_Logs" (
    log_id           SERIAL PRIMARY KEY,
    disbursement_id  INTEGER REFERENCES "Disbursements"(disbursement_id) ON DELETE SET NULL,
    action           VARCHAR(100) NOT NULL,
    details          TEXT NOT NULL DEFAULT '',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS disbursements_status_idx ON "Disbursements"(status);
CREATE INDEX IF NOT EXISTS payment_history_disbursement_idx ON "Payment_History"(disbursement_id);
CREATE INDEX IF NOT EXISTS disbursement_audit_logs_idx ON "Disbursement_Audit_Logs"(disbursement_id);

CREATE TABLE IF NOT EXISTS "Notifications" (
    notification_id  SERIAL PRIMARY KEY,
    user_id          INTEGER NOT NULL REFERENCES "Users"(user_id) ON DELETE CASCADE,
    message          VARCHAR(500) NOT NULL,
    notif_type       VARCHAR(30)  NOT NULL DEFAULT 'info',
    is_read          BOOLEAN NOT NULL DEFAULT FALSE,
    email_sent       BOOLEAN NOT NULL DEFAULT FALSE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS notifications_user_unread_idx
    ON "Notifications"(user_id, is_read);

CREATE TABLE IF NOT EXISTS "Audit_Log" (
    audit_id     SERIAL PRIMARY KEY,
    user_id      INTEGER REFERENCES "Users"(user_id) ON DELETE SET NULL,
    action       VARCHAR(100) NOT NULL,
    entity_type  VARCHAR(50),
    entity_id    INTEGER,
    details      JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS audit_log_created_idx ON "Audit_Log"(created_at);
-- Project tracking and sequential approval workflow.
-- The Users table is provisioned by the account setup component.

CREATE TABLE IF NOT EXISTS "Approval_Requests" (
	approval_id    SERIAL PRIMARY KEY,
	project_id     INTEGER NOT NULL REFERENCES "Projects"(project_id) ON DELETE CASCADE,
	round_number   INTEGER NOT NULL CHECK (round_number > 0),
	step_order     INTEGER NOT NULL CHECK (step_order > 0),
	approver_id    INTEGER NOT NULL REFERENCES "Users"(user_id),
	status         VARCHAR(12) NOT NULL DEFAULT 'waiting'
				   CHECK (status IN ('waiting', 'pending', 'approved', 'rejected', 'skipped')),
	comments       TEXT,
	created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
	decided_at     TIMESTAMPTZ,
	UNIQUE (project_id, round_number, step_order),
	UNIQUE (project_id, round_number, approver_id)
);

CREATE TABLE IF NOT EXISTS "Project_Status_History" (
	history_id   SERIAL PRIMARY KEY,
	project_id   INTEGER NOT NULL REFERENCES "Projects"(project_id) ON DELETE CASCADE,
	from_status  VARCHAR(24),
	to_status    VARCHAR(24) NOT NULL CHECK (to_status IN (
					 'draft', 'pending_approval', 'approved', 'active',
					 'on_hold', 'completed', 'cancelled', 'rejected'
				 )),
	changed_by   INTEGER NOT NULL REFERENCES "Users"(user_id),
	reason       TEXT,
	changed_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
	CHECK (from_status IS NULL OR from_status IN (
        'planned', 'draft', 'pending_approval', 'approved', 'active',
        'on_hold', 'completed', 'cancelled', 'rejected'
	))
);

CREATE INDEX IF NOT EXISTS projects_status_idx ON "Projects"(status);
CREATE INDEX IF NOT EXISTS projects_created_by_idx ON "Projects"(created_by);
CREATE INDEX IF NOT EXISTS approvals_inbox_idx
	ON "Approval_Requests"(approver_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS approvals_project_round_idx
	ON "Approval_Requests"(project_id, round_number, step_order);
CREATE INDEX IF NOT EXISTS project_status_history_idx
	ON "Project_Status_History"(project_id, changed_at DESC);

CREATE TABLE IF NOT EXISTS "Project_Milestones" (
    milestone_id  SERIAL PRIMARY KEY,
    project_id    INTEGER NOT NULL REFERENCES "Projects"(project_id) ON DELETE CASCADE,
    title         VARCHAR(200) NOT NULL,
    description   TEXT,
    due_date      DATE,
    status        VARCHAR(20) NOT NULL DEFAULT 'planned'
                  CHECK (status IN ('planned', 'in_progress', 'completed')),
    created_by    INTEGER NOT NULL REFERENCES "Users"(user_id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at  TIMESTAMPTZ
);

-- Approval inbox (approvals module). Give this to the database owner to merge into schema.sql.
-- The names "Approvals" and "Approval_Requests" are already used by the procurement and
-- project approval chains, so this module uses "Approval_Items".
-- Needs the existing "Users" table (user_id) and "Audit_Log" table.
-- request_type is validated in code (REQUEST_TYPES in services/approvals.py).

CREATE TABLE IF NOT EXISTS "Approval_Items" (
    approval_id      SERIAL PRIMARY KEY,
    request_type     VARCHAR(30)  NOT NULL,
    reference_id     INTEGER,
    summary          VARCHAR(500) NOT NULL,
    requested_by     INTEGER NOT NULL REFERENCES "Users"(user_id),
    status           VARCHAR(10)  NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending', 'approved', 'rejected')),
    decided_by       INTEGER REFERENCES "Users"(user_id),
    decision_reason  TEXT,
    decided_at       TIMESTAMPTZ,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CHECK (status = 'pending' OR (decided_by IS NOT NULL AND decided_at IS NOT NULL)),
    CHECK (status <> 'rejected'
           OR (decision_reason IS NOT NULL AND length(btrim(decision_reason)) > 0))
);

CREATE INDEX IF NOT EXISTS approval_items_pending_idx
    ON "Approval_Items"(request_type, created_at) WHERE status = 'pending';

-- Remembers that a user has opened the pending list (task T8).
CREATE TABLE IF NOT EXISTS "Approval_Views" (
    user_id    INTEGER PRIMARY KEY REFERENCES "Users"(user_id) ON DELETE CASCADE,
    viewed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS project_milestones_order_idx
    ON "Project_Milestones"(project_id, due_date, milestone_id);



-- ---------------------------------------------------------------------------
-- Requests and Procurements: extra columns, wider status lists, history.
-- Owner: Member 4 (requests and procurement). Additive only: no column is
-- removed or renamed, so existing rows and other modules keep working.
-- Safe to run on every start: every statement can be repeated.
-- ---------------------------------------------------------------------------
ALTER TABLE "Requests"
    ADD COLUMN IF NOT EXISTS request_type VARCHAR(20) NOT NULL DEFAULT 'asset',
    ADD COLUMN IF NOT EXISTS category     VARCHAR(100),
    ADD COLUMN IF NOT EXISTS quantity     INTEGER NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS amount       NUMERIC(12, 2),
    ADD COLUMN IF NOT EXISTS needed_by    DATE,
    ADD COLUMN IF NOT EXISTS asset_type   VARCHAR(10),
    ADD COLUMN IF NOT EXISTS escalated_to INTEGER REFERENCES "Users"(user_id),
    ADD COLUMN IF NOT EXISTS fulfilled_by INTEGER REFERENCES "Users"(user_id),
    ADD COLUMN IF NOT EXISTS updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW();

-- Replace the two original checks (they only allowed asset requests and five
-- statuses) with named, wider ones. Existing rows already satisfy them.
ALTER TABLE "Requests" DROP CONSTRAINT IF EXISTS "Requests_check";
ALTER TABLE "Requests" DROP CONSTRAINT IF EXISTS "Requests_status_check";

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'requests_status_values'
                   AND conrelid = '"Requests"'::regclass) THEN
        BEGIN
            ALTER TABLE "Requests" ADD CONSTRAINT requests_status_values CHECK (status IN
                ('pending', 'escalated', 'approved', 'rejected', 'fulfilled', 'converted', 'cancelled'));
        EXCEPTION WHEN duplicate_object THEN NULL;  -- another process got there first
        END;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'requests_type_values'
                   AND conrelid = '"Requests"'::regclass) THEN
        BEGIN
            ALTER TABLE "Requests" ADD CONSTRAINT requests_type_values CHECK (request_type IN
                ('asset', 'disbursement', 'project'));
        EXCEPTION WHEN duplicate_object THEN NULL;  -- another process got there first
        END;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'requests_asset_needs_item'
                   AND conrelid = '"Requests"'::regclass) THEN
        BEGIN
            ALTER TABLE "Requests" ADD CONSTRAINT requests_asset_needs_item CHECK
                (request_type <> 'asset' OR asset_id IS NOT NULL OR item_name IS NOT NULL);
        EXCEPTION WHEN duplicate_object THEN NULL;  -- another process got there first
        END;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'requests_disbursement_needs_amount'
                   AND conrelid = '"Requests"'::regclass) THEN
        BEGIN
            ALTER TABLE "Requests" ADD CONSTRAINT requests_disbursement_needs_amount CHECK
                (request_type <> 'disbursement' OR amount IS NOT NULL);
        EXCEPTION WHEN duplicate_object THEN NULL;  -- another process got there first
        END;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'requests_amount_positive'
                   AND conrelid = '"Requests"'::regclass) THEN
        BEGIN
            ALTER TABLE "Requests" ADD CONSTRAINT requests_amount_positive CHECK (amount IS NULL OR amount > 0);
        EXCEPTION WHEN duplicate_object THEN NULL;  -- another process got there first
        END;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'requests_quantity_positive'
                   AND conrelid = '"Requests"'::regclass) THEN
        BEGIN
            ALTER TABLE "Requests" ADD CONSTRAINT requests_quantity_positive CHECK (quantity > 0);
        EXCEPTION WHEN duplicate_object THEN NULL;  -- another process got there first
        END;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'requests_asset_type_values'
                   AND conrelid = '"Requests"'::regclass) THEN
        BEGIN
            ALTER TABLE "Requests" ADD CONSTRAINT requests_asset_type_values CHECK
                (asset_type IS NULL OR asset_type IN ('tool', 'device', 'vehicle'));
        EXCEPTION WHEN duplicate_object THEN NULL;  -- another process got there first
        END;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS requests_status_idx       ON "Requests"(status);
CREATE INDEX IF NOT EXISTS requests_requester_idx    ON "Requests"(requester_id);
CREATE INDEX IF NOT EXISTS requests_escalated_to_idx ON "Requests"(escalated_to);

ALTER TABLE "Procurements"
    ADD COLUMN IF NOT EXISTS category   VARCHAR(100),
    ADD COLUMN IF NOT EXISTS asset_type VARCHAR(10),
    ADD COLUMN IF NOT EXISTS reason     TEXT,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

-- A draft has no cost yet, so the cost may be empty until it is submitted.
ALTER TABLE "Procurements" ALTER COLUMN estimated_cost DROP NOT NULL;

-- Keep the approval-chain statuses and add the draft/purchase life cycle.
ALTER TABLE "Procurements" DROP CONSTRAINT IF EXISTS "Procurements_status_check";

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'procurements_status_values'
                   AND conrelid = '"Procurements"'::regclass) THEN
        BEGIN
            ALTER TABLE "Procurements" ADD CONSTRAINT procurements_status_values CHECK (status IN
                ('draft', 'pending', 'pending_approval', 'level_1', 'level_2',
                 'approved', 'rejected', 'purchased', 'cancelled'));
        EXCEPTION WHEN duplicate_object THEN NULL;  -- another process got there first
        END;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'procurements_asset_type_values'
                   AND conrelid = '"Procurements"'::regclass) THEN
        BEGIN
            ALTER TABLE "Procurements" ADD CONSTRAINT procurements_asset_type_values CHECK
                (asset_type IS NULL OR asset_type IN ('tool', 'device', 'vehicle'));
        EXCEPTION WHEN duplicate_object THEN NULL;  -- another process got there first
        END;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS procurements_status_idx ON "Procurements"(status);

-- One row per status change of a request or procurement. Powers the timeline
-- in the app and doubles as an audit trail. changed_by is NULL for the system.
CREATE TABLE IF NOT EXISTS "Request_History" (
    history_id   SERIAL PRIMARY KEY,
    entity_type  VARCHAR(12) NOT NULL CHECK (entity_type IN ('request', 'procurement')),
    entity_id    INTEGER     NOT NULL,
    status       VARCHAR(24) NOT NULL,
    note         TEXT,
    changed_by   INTEGER REFERENCES "Users"(user_id),
    changed_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS request_history_entity_idx
    ON "Request_History"(entity_type, entity_id, changed_at);
