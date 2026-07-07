-- One-off full reset, requested explicitly by the user 2026-07-07, after
-- being told plainly what it costs: trip 827's already-mailed real claim
-- (Claim #12) disappears from view since claim_tracking gets wiped along
-- with the raw scan data it's enriched against, and the entire 13-day
-- 2026-06-26..07-06 backfill recovered earlier the same day (after that
-- day's storage-quota incident) is thrown away. Confirmed with full
-- knowledge of both, choosing a genuinely clean slate over preserving
-- either.
--
-- Scope: every table the live scanner/claims flow writes to -- the same
-- set as 004_wipe_delay_history.sql + 006_wipe_claim_tracking.sql
-- combined into one statement. Does NOT touch Supabase's own auth/storage
-- system tables (users, sessions, buckets, objects, etc.) or the
-- claim_forms storage bucket's objects -- those are infrastructure, not
-- application data, and weren't part of what was asked to be wiped.
TRUNCATE TABLE
    delays,
    trip_cancellations,
    seen_trips,
    line_daily_visibility,
    line_visibility_anomalies,
    alerts,
    alert_entities,
    scan_runs,
    housekeeping_runs,
    claim_tracking
RESTART IDENTITY;
