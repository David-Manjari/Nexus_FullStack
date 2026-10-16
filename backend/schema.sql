CREATE TABLE IF NOT EXISTS "Users" (
    user_id        SERIAL PRIMARY KEY,
    username       VARCHAR(64)  NOT NULL UNIQUE,
    email          VARCHAR(254) NOT NULL UNIQUE,
    password_hash  TEXT         NOT NULL,
    role           VARCHAR(20)  NOT NULL
                   CHECK (role IN ('admin', 'manager', 'store_manager', 'staff')),
    is_active      BOOLEAN      NOT NULL DEFAULT TRUE,
    last_login_at  TIMESTAMPTZ,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

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
CREATE OR REPLACE FUNCTION projects_sync_compat() RETURNS trigger AS $$
BEGIN
    IF NEW.created_by IS NULL THEN NEW.created_by := NEW.manager_id; END IF;
    IF NEW.manager_id IS NULL THEN NEW.manager_id := NEW.created_by; END IF;

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
    amount             NUMERIC(12, 2) NOT NULL CHECK (amount >= 0),
    currency           VARCHAR(3) NOT NULL DEFAULT 'KES',
    description        TEXT NOT NULL DEFAULT '',
    status             VARCHAR(12) NOT NULL DEFAULT 'pending'
                       CHECK (status IN ('pending', 'processing', 'success', 'paid', 'failed')),
    payment_reference  VARCHAR(100),
    failure_reason     TEXT,
    paid_by            INTEGER REFERENCES "Users"(user_id),
    paid_at            TIMESTAMPTZ,
    receipt_ref        VARCHAR(100),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (procurement_id IS NOT NULL OR (reference IS NOT NULL AND payee IS NOT NULL)),
    CHECK (reference IS NULL OR amount > 0)
);

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


