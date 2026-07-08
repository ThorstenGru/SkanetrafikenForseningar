-- Adds a second, parallel path to the claim lifecycle: filing directly
-- with Skånetrafiken through their own digital channel, as an alternative
-- to printing the paper form and mailing it. Requested by the user
-- 2026-07-08.
--
-- Deliberately a separate flag from mailed/mailed_at rather than
-- overloading "mailed" to mean "filed, however" -- mailed should keep
-- meaning literally that. claims.html's archived section now checks
-- (mailed OR claimed_digitally) to decide what's actually filed.
ALTER TABLE claim_tracking
    ADD COLUMN IF NOT EXISTS claimed_digitally    BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS claimed_digitally_at TIMESTAMPTZ;
