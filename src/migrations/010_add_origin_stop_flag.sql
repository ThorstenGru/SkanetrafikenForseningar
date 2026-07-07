-- Fixes a gap found by today's (2026-07-07) code review, confirmed
-- independently by four review passes: scan.py always records a trip's
-- origin stop regardless of delay (to avoid unconfirmed "?" departure
-- times), but `delays` only ever persisted is_final_stop -- there was no
-- way to tell an origin-stop row apart from an ordinary mid-trip row once
-- written. cleanup_delay_noise.py's noise-deletion could (and, on its
-- first run, likely did) delete origin-stop rows it had no way to
-- recognize as protected, silently reintroducing the unconfirmed-
-- departure bug the origin-always-record logic was written to fix.
ALTER TABLE delays
    ADD COLUMN IF NOT EXISTS is_origin_stop BOOLEAN NOT NULL DEFAULT FALSE;
