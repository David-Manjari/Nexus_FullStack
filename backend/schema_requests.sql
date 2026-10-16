-- Request and procurement tables for Member 4. Give this to Member 1 to merge into schema.sql.
-- ASSUMPTIONS: "Users".user_id and "Assets".asset_id are integer primary keys.
-- Create "Users" and "Assets" before running this file.
-- project_id has no foreign key yet: add it once the Projects table exists.

CREATE TABLE IF NOT EXISTS "Requests" (
    request_id    SERIAL PRIMARY KEY,
    request_type  VARCHAR(20)  NOT NULL
                  CHECK (request_type IN ('asset', 'disbursement', 'project')),
    requested_by  INTEGER      NOT NULL REFERENCES "Users"(user_id),
    project_id    INTEGER,
    asset_id      INTEGER REFERENCES "Assets"(asset_id),
    item_name     VARCHAR(150),
    category      VARCHAR(100),
    quantity      INTEGER      NOT NULL DEFAULT 1 CHECK (quantity > 0),
    amount        NUMERIC(12,2) CHECK (amount > 0),
    reason        TEXT         NOT NULL,
    status        VARCHAR(20)  NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'escalated', 'approved', 'rejected',
                                    'fulfilled', 'converted', 'cancelled')),
    escalated_to  INTEGER REFERENCES "Users"(user_id),
    fulfilled_by  INTEGER REFERENCES "Users"(user_id),
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    -- An asset request must say what is wanted; a disbursement must say how much.
    CONSTRAINT asset_request_has_item
        CHECK (request_type <> 'asset' OR asset_id IS NOT NULL OR item_name IS NOT NULL),
    CONSTRAINT disbursement_request_has_amount
        CHECK (request_type <> 'disbursement' OR amount IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS "Procurement" (
    procurement_id  SERIAL PRIMARY KEY,
    -- NULL when a store manager raises a procurement directly, without a request.
    request_id      INTEGER REFERENCES "Requests"(request_id),
    raised_by       INTEGER      NOT NULL REFERENCES "Users"(user_id),
    item_name       VARCHAR(150) NOT NULL,
    category        VARCHAR(100),
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

-- A request can be converted into at most one procurement.
CREATE UNIQUE INDEX IF NOT EXISTS one_procurement_per_request
    ON "Procurement"(request_id) WHERE request_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS requests_status_idx       ON "Requests"(status);
CREATE INDEX IF NOT EXISTS requests_requested_by_idx ON "Requests"(requested_by);
CREATE INDEX IF NOT EXISTS requests_escalated_to_idx ON "Requests"(escalated_to);
CREATE INDEX IF NOT EXISTS procurement_status_idx    ON "Procurement"(status);

-- Once "Requests" exists, Member 3's assignments table can link to it:
-- ALTER TABLE "Asset_Assignments"
--     ADD CONSTRAINT asset_assignments_request_fk
--     FOREIGN KEY (request_id) REFERENCES "Requests"(request_id);
