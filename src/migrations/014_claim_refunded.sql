-- Adds a "Refunded" checkbox to the archived/already-filed section --
-- requested by the user 2026-07-08: knowing a claim was mailed/filed
-- doesn't say whether Skånetrafiken actually paid out. Deliberately a
-- plain toggle (not a one-way gate like mailed/claimed_digitally), since a
-- rider can reasonably tick it, realize the voucher/cash hasn't actually
-- arrived yet, and untick it -- refunded_at is cleared (not left stale) if
-- that happens, see saveTrackingRow's own note in claims_template.html.
ALTER TABLE claim_tracking
    ADD COLUMN IF NOT EXISTS refunded    BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS refunded_at TIMESTAMPTZ;
