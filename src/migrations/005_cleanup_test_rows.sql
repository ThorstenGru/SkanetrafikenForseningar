-- Removes two leftover rows from Claude's own debugging session on
-- 2026-07-06 (a synthetic connectivity-test row, and one real trip that
-- was toggled during a live-page bug investigation before fetch
-- interception was in place for all subsequent tests). Neither reflects
-- anything the user actually claimed. Targeted by trip_id, not a blanket
-- wipe of claim_tracking — that table holds real user claim progress and
-- was deliberately excluded from 004_wipe_delay_history.sql.
DELETE FROM claim_tracking WHERE trip_id IN ('__CONNECTIVITY_TEST__', '121120000383773696');
