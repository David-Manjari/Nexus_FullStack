-- Approvals (Member: approvals). Give this to the database owner to merge into schema.sql.
-- ASSUMPTION: "Users".user_id is an integer primary key.
-- request_type is validated in code (REQUEST_TYPES in services/approvals.py).

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

-- Skip this table if the shared schema already defines Audit_Log.
CREATE TABLE IF NOT EXISTS "Audit_Log" (
    audit_id     SERIAL PRIMARY KEY,
    user_id      INTEGER REFERENCES "Users"(user_id) ON DELETE SET NULL,
    action       VARCHAR(100) NOT NULL,
    entity_type  VARCHAR(50),
    entity_id    INTEGER,
    details      JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);