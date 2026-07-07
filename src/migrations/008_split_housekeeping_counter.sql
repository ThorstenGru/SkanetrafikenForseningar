-- housekeeping.py was summing line_daily_visibility and
-- line_visibility_anomalies deletion counts into the single
-- line_visibility_deleted column, making it impossible to tell which of
-- the two tables actually had rows deleted on a given run. Splits them:
-- line_visibility_deleted now means line_daily_visibility only, and this
-- new column carries line_visibility_anomalies.

ALTER TABLE housekeeping_runs
    ADD COLUMN IF NOT EXISTS line_anomalies_deleted INTEGER;
