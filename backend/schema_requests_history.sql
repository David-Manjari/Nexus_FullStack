-- Extra columns and the history table for Member 4.
-- Run after schema_requests.sql. Give both to Member 1 to merge into schema.sql.
-- ASSUMPTION: "Users".user_id is an integer primary key.

ALTER TABLE "Requests"
    ADD COLUMN IF NOT EXISTS needed_by  DATE,
    ADD COLUMN IF NOT EXISTS asset_type VARCHAR(10)
        CHECK (asset_type IN ('tool', 'device', 'vehicle'));

ALTER TABLE "Procurement"
    ADD COLUMN IF NOT EXISTS asset_type VARCHAR(10)
        CHECK (asset_type IN ('tool', 'device', 'vehicle'));

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
