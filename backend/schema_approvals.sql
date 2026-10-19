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