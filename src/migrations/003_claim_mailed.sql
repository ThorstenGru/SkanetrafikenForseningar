-- Adds the third and final stage to the claim lifecycle the user asked for
-- 2026-07-06: cart (selected, not yet claimed) -> checked out (claimed=true,
-- forms being prepared) -> archived (mailed=true, physically sent). Only
-- the last transition needs a new column; "checked out" already exists as
-- claimed=true from 001/002.
--
-- Still no personal content — mailed/mailed_at say nothing about who the
-- claimant is, consistent with every other column in this table (see
-- COMPENSATION_RULES.md §12/§14 for why that boundary matters here).

ALTER TABLE claim_tracking
    ADD COLUMN IF NOT EXISTS mailed    BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS mailed_at TIMESTAMPTZ;
