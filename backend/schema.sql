-- Accounts
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

-- Projects and their approval workflow 
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

-- Inventory
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

-- Requests and procurement
CREATE TABLE IF NOT EXISTS "Requests" (
    request_id    SERIAL PRIMARY KEY,
    request_type  VARCHAR(20)  NOT NULL
                  CHECK (request_type IN ('asset', 'disbursement', 'project')),
    requested_by  INTEGER      NOT NULL REFERENCES "Users"(user_id),
    project_id    INTEGER REFERENCES "Projects"(project_id),
    asset_id      INTEGER REFERENCES "Assets"(asset_id),
    item_name     VARCHAR(150),
    category      VARCHAR(100),
    asset_type    VARCHAR(10) CHECK (asset_type IN ('tool', 'device', 'vehicle')),
    quantity      INTEGER      NOT NULL DEFAULT 1 CHECK (quantity > 0),
    amount        NUMERIC(12,2) CHECK (amount > 0),
    needed_by     DATE,
    reason        TEXT         NOT NULL,
    status        VARCHAR(20)  NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'escalated', 'approved', 'rejected',
                                    'fulfilled', 'converted', 'cancelled')),
    escalated_to  INTEGER REFERENCES "Users"(user_id),
    fulfilled_by  INTEGER REFERENCES "Users"(user_id),
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT asset_request_has_item
        CHECK (request_type <> 'asset' OR asset_id IS NOT NULL OR item_name IS NOT NULL),
    CONSTRAINT disbursement_request_has_amount
        CHECK (request_type <> 'disbursement' OR amount IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS requests_status_idx       ON "Requests"(status);
CREATE INDEX IF NOT EXISTS requests_requested_by_idx ON "Requests"(requested_by);
CREATE INDEX IF NOT EXISTS requests_escalated_to_idx ON "Requests"(escalated_to);

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

-- One asset can have only one open assignment
CREATE UNIQUE INDEX IF NOT EXISTS one_open_assignment_per_asset
    ON "Asset_Assignments"(asset_id) WHERE returned_at IS NULL;
CREATE INDEX IF NOT EXISTS assets_status_idx ON "Assets"(status);
CREATE INDEX IF NOT EXISTS assets_type_idx   ON "Assets"(asset_type);

CREATE TABLE IF NOT EXISTS "Procurement" (
    procurement_id  SERIAL PRIMARY KEY,
    -- NULL when a store manager raises a procurement directly, without a request.
    request_id      INTEGER REFERENCES "Requests"(request_id),
    raised_by       INTEGER      NOT NULL REFERENCES "Users"(user_id),
    item_name       VARCHAR(150) NOT NULL,
    category        VARCHAR(100),
    asset_type      VARCHAR(10) CHECK (asset_type IN ('tool', 'device', 'vehicle')),
    quantity        INTEGER      NOT NULL DEFAULT 1 CHECK (quantity > 0),
    estimated_cost  NUMERIC(12,2) CHECK (estimated_cost >= 0),
    supplier        VARCHAR(150),
    reason          TEXT,
    status          VARCHAR(20)  NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'pending_approval', 'approved',
                                      'rejected', 'purchased', 'cancelled')),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- One request can be converted into one procurement
CREATE UNIQUE INDEX IF NOT EXISTS one_procurement_per_request
    ON "Procurement"(request_id) WHERE request_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS procurement_status_idx ON "Procurement"(status);

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

-- Approvals
CREATE TABLE IF NOT EXISTS "Approvals" (
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

CREATE INDEX IF NOT EXISTS approvals_pending_idx
    ON "Approvals"(request_type, created_at) WHERE status = 'pending';

-- Remembers that a user has opened the pending list (task T8).
CREATE TABLE IF NOT EXISTS "Approval_Views" (
    user_id    INTEGER PRIMARY KEY REFERENCES "Users"(user_id) ON DELETE CASCADE,
    viewed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Disbursements
CREATE TABLE IF NOT EXISTS "Disbursements" (
    disbursement_id    SERIAL PRIMARY KEY,
    procurement_id     INTEGER UNIQUE REFERENCES "Procurement"(procurement_id),
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

-- Shared tables
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