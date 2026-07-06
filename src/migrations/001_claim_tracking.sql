-- Personal claim-tracking (a "Claim started" flag + Skånetrafiken's own
-- claim number once filed), written directly by claims.html's client-side
-- JS via Supabase's PostgREST API using the public anon key. Moved off
-- browser localStorage (2026-07-06) so the record survives across
-- browsers/devices — see docs/COMPENSATION_RULES.md §12 for the full
-- design decision, including why this needs a passphrase gate at all.
--
-- Apply with: see docs/RUNBOOK.md#applying-migrations. ${CLAIM_TRACKING_PASSPHRASE}
-- is substituted by src/apply_migration.py from the environment — never
-- commit an actual passphrase value into this file.

CREATE TABLE IF NOT EXISTS claim_tracking (
    trip_id           TEXT NOT NULL,
    trip_start_date   DATE NOT NULL,
    claimed           BOOLEAN NOT NULL DEFAULT FALSE,
    claim_number      TEXT,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (trip_id, trip_start_date)
);

ALTER TABLE claim_tracking ENABLE ROW LEVEL SECURITY;

-- Reads are always open — this table has no sensitive content beyond a
-- self-chosen claim number, and the dashboard/compensation/claims pages
-- are already fully public network-wide data.
DROP POLICY IF EXISTS claim_tracking_select ON claim_tracking;
CREATE POLICY claim_tracking_select ON claim_tracking
    FOR SELECT USING (true);

-- Writes require a shared passphrase sent as a custom header
-- (x-claim-passphrase), checked via PostgREST's request.headers GUC. This
-- is NOT real security — the passphrase ships inside claims.html's own
-- JavaScript, so anyone who opens dev tools on the live page can read it
-- just as easily as the anon key itself. Its only purpose is to stop a
-- casual visitor or bot from trivially POSTing to the table without first
-- inspecting the page source — a deliberate, accepted trade-off given this
-- table's low sensitivity (see COMPENSATION_RULES.md §12 for the
-- alternatives considered and why full Supabase Auth was judged overkill
-- for a single-user personal tool).
DROP POLICY IF EXISTS claim_tracking_insert ON claim_tracking;
CREATE POLICY claim_tracking_insert ON claim_tracking
    FOR INSERT
    WITH CHECK (current_setting('request.headers', true)::json->>'x-claim-passphrase' = '${CLAIM_TRACKING_PASSPHRASE}');

DROP POLICY IF EXISTS claim_tracking_update ON claim_tracking;
CREATE POLICY claim_tracking_update ON claim_tracking
    FOR UPDATE
    USING (current_setting('request.headers', true)::json->>'x-claim-passphrase' = '${CLAIM_TRACKING_PASSPHRASE}')
    WITH CHECK (current_setting('request.headers', true)::json->>'x-claim-passphrase' = '${CLAIM_TRACKING_PASSPHRASE}');

-- Deliberately no DELETE policy and no DELETE grant — the anon role
-- cannot delete tracking rows under any circumstance, passphrase or not.
GRANT SELECT, INSERT, UPDATE ON claim_tracking TO anon;
