-- Adds the two extra choices the claim-initiation wizard on claims.html
-- collects once "Claim started" is ticked: which compensation type and
-- which payout method the rider wants. Both are plain enums with no
-- personal content — safe to add to the existing openly-readable
-- claim_tracking table (see 001_claim_tracking.sql's own note on why
-- SELECT is open to everyone with the anon key).
--
-- Deliberately NOT stored anywhere, ever: name, address, personnummer, or
-- any other personal-details/payout-account field from the actual claim
-- form. Those stay local to the user's own machine only (the filled PDF
-- itself, never uploaded) — see docs/COMPENSATION_RULES.md §14 for the
-- full reasoning. This table exists to answer "did I already claim this
-- trip and how", not to hold the claim itself.

ALTER TABLE claim_tracking
    ADD COLUMN IF NOT EXISTS compensation_type TEXT,   -- 'prisavdrag' | 'taxi' | 'mileage'
    ADD COLUMN IF NOT EXISTS payout_method TEXT;        -- 'voucher_sms' | 'voucher_email' | 'cash'
