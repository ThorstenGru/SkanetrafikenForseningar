-- Adds the "Print Claim" stage the user asked for 2026-07-07, ahead of
-- "Mark sent in": claims.html now fills the official Skånetrafiken paper
-- form client-side (route/date/times/delay-length/compensation-type/
-- payout-method only -- never personnummer, bank details, mobile, e-post,
-- or signature) and stores the rendered PDF for later proof.
--
-- This supersedes 002_claim_choices.sql's note that nothing beyond enums
-- would ever be stored: the filled PDF necessarily contains name + home
-- address (typed once into this browser's localStorage only -- never
-- part of the built static page's JSON payload, never in this table).
-- See docs/COMPENSATION_RULES.md §16 for the full reasoning.
--
-- Lifecycle is now: cart -> checked out (claimed=true) -> printed
-- (printed_at set, filled_pdf_path recorded) -> archived (mailed=true).
-- Claim number is only meaningful once Skånetrafiken has actually
-- responded, i.e. after mailing -- claims.html gates the input on
-- mailed=true even though the column itself predates this migration.

ALTER TABLE claim_tracking
    ADD COLUMN IF NOT EXISTS printed_at       TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS filled_pdf_path  TEXT;

-- Private bucket -- this site has no login (the anon key and even the
-- write passphrase are both readable in the deployed page's own JS), so
-- "private" here means "not in the public bucket list", gated by the same
-- shared passphrase already accepted for claim_tracking writes. That is a
-- deliberately weaker bar than the personnummer/bank exclusion, which is
-- why those fields never make it into the PDF this bucket holds.
INSERT INTO storage.buckets (id, name, public)
VALUES ('claim_forms', 'claim_forms', false)
ON CONFLICT (id) DO NOTHING;

DROP POLICY IF EXISTS claim_forms_select ON storage.objects;
CREATE POLICY claim_forms_select ON storage.objects
    FOR SELECT USING (
        bucket_id = 'claim_forms'
        AND current_setting('request.headers', true)::json->>'x-claim-passphrase' = '${CLAIM_TRACKING_PASSPHRASE}'
    );

DROP POLICY IF EXISTS claim_forms_insert ON storage.objects;
CREATE POLICY claim_forms_insert ON storage.objects
    FOR INSERT
    WITH CHECK (
        bucket_id = 'claim_forms'
        AND current_setting('request.headers', true)::json->>'x-claim-passphrase' = '${CLAIM_TRACKING_PASSPHRASE}'
    );

-- Allows re-printing (re-upload) to overwrite a previous filled PDF for
-- the same trip rather than accumulating duplicates.
DROP POLICY IF EXISTS claim_forms_update ON storage.objects;
CREATE POLICY claim_forms_update ON storage.objects
    FOR UPDATE
    USING (
        bucket_id = 'claim_forms'
        AND current_setting('request.headers', true)::json->>'x-claim-passphrase' = '${CLAIM_TRACKING_PASSPHRASE}'
    )
    WITH CHECK (
        bucket_id = 'claim_forms'
        AND current_setting('request.headers', true)::json->>'x-claim-passphrase' = '${CLAIM_TRACKING_PASSPHRASE}'
    );
