-- One-off data wipe, requested explicitly by the user 2026-07-06 for a
-- clean start ("wipe the database for a clean start", confirmed after
-- being told this was irreversible and that the purchase-date cutoff
-- already achieves the same practical filtering non-destructively — see
-- docs/COMPENSATION_RULES.md §15/§16).
--
-- Scope: every table the live scanner writes to. Deliberately excludes
-- claim_tracking — that holds the user's own claim cart/checkout/archive
-- progress, not scanned delay history, and wiping it was never asked for.
--
-- TRUNCATE (not DELETE) because these are full-table wipes with no WHERE
-- clause — faster, and RESTART IDENTITY resets the BIGSERIAL id columns
-- (alert_entities, scan_runs, housekeeping_runs) back to 1 for a genuinely
-- clean start. alerts + alert_entities must be truncated together in one
-- statement since alert_entities has a FOREIGN KEY into alerts.
TRUNCATE TABLE
    delays,
    trip_cancellations,
    seen_trips,
    line_daily_visibility,
    line_visibility_anomalies,
    alerts,
    alert_entities,
    scan_runs,
    housekeeping_runs
RESTART IDENTITY;
