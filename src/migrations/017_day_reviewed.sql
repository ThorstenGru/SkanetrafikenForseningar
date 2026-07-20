-- Per-day "already looked into" flag for claims.html's "Suggested reasonable
-- chains" section (src/claims_template.html) -- requested by the user
-- 2026-07-20: most days have nothing worth claiming, and re-reading the same
-- already-checked day every time the page loads is wasted effort. Ticking a
-- day's own checkbox marks it reviewed and hides it from the default view
-- (a toggle brings reviewed days back if needed).
--
-- Same design as claim_tracking (docs/COMPENSATION_RULES.md §12): written
-- directly from the browser via Supabase's REST API using the public anon
-- key, gated by the same shared passphrase header so a casual visitor can't
-- trivially write to it either. Global (not per-browser/device) for the same
-- reason claim_tracking is -- this is a single-user personal tool, and the
-- point is to remember review state across devices.
--
-- Apply with: see docs/RUNBOOK.md#applying-migrations. ${CLAIM_TRACKING_PASSPHRASE}
-- is substituted by src/apply_migration.py from the environment -- never
-- commit an actual passphrase value into this file.

CREATE TABLE IF NOT EXISTS day_reviewed (
    review_date  DATE NOT NULL PRIMARY KEY,
    reviewed     BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE day_reviewed ENABLE ROW LEVEL SECURITY;

-- Reads open to anyone, same reasoning as claim_tracking_select -- this
-- table has no sensitive content at all (just a date and a boolean), and
-- the page it drives is already fully public network-wide data.
DROP POLICY IF EXISTS day_reviewed_select ON day_reviewed;
CREATE POLICY day_reviewed_select ON day_reviewed
    FOR SELECT USING (true);

-- Writes gated by the same shared passphrase as claim_tracking (see that
-- migration's own note on why this is a deterrent, not real security).
DROP POLICY IF EXISTS day_reviewed_insert ON day_reviewed;
CREATE POLICY day_reviewed_insert ON day_reviewed
    FOR INSERT
    WITH CHECK (current_setting('request.headers', true)::json->>'x-claim-passphrase' = '${CLAIM_TRACKING_PASSPHRASE}');

DROP POLICY IF EXISTS day_reviewed_update ON day_reviewed;
CREATE POLICY day_reviewed_update ON day_reviewed
    FOR UPDATE
    USING (current_setting('request.headers', true)::json->>'x-claim-passphrase' = '${CLAIM_TRACKING_PASSPHRASE}')
    WITH CHECK (current_setting('request.headers', true)::json->>'x-claim-passphrase' = '${CLAIM_TRACKING_PASSPHRASE}');

-- Deliberately no DELETE policy/grant, same as claim_tracking -- unreviewing
-- a day is just another UPDATE (reviewed=false), never a row deletion.
GRANT SELECT, INSERT, UPDATE ON day_reviewed TO anon;
