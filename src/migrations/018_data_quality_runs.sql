-- Requested by the user 2026-07-20: "with every scanner run... review the
-- predictions if they have come true or cured themselves... make sure we
-- have every time a full, consistent and correct data set." Investigated
-- first, before building anything: does GTFS-RT re-polling alone ever
-- "cure" a stale/unconfirmed final-stop prediction? Checked directly --
-- most unconfirmed final-stop rows have already been polled many times
-- (poll_count 15-20+ in plenty of cases) and are STILL unconfirmed, because
-- GTFS-RT's own "arrival_time" field is a rolling prediction that keeps
-- moving forward as the delay grows, right up until the vehicle actually
-- arrives -- our own polling, no matter how frequent, can only ever catch
-- this if a poll happens to land exactly after the real arrival and before
-- the trip drops out of the feed. Confirming a stale prediction therefore
-- genuinely needs a second source (Trafikverket's post-event
-- TimeAtLocation, already built as confirm_stale_finals() in
-- trafikverket_merge.py) -- this table exists to make that mechanism's
-- results a persisted, queryable trail instead of a print() line that
-- only ever existed in one Action run's own log, plus a set of basic
-- structural consistency checks (src/data_quality_check.py).
CREATE TABLE IF NOT EXISTS data_quality_runs (
    id                              BIGSERIAL PRIMARY KEY,
    run_at                          TIMESTAMPTZ NOT NULL,
    final_stop_rows_total           INTEGER,
    final_stop_rows_unconfirmed     INTEGER,
    confirmed_via_trafikverket_now  INTEGER,
    max_delay_fallback_trips        INTEGER,
    orphaned_final_stop_trips       INTEGER,
    arrival_after_departure_rows    INTEGER,
    implausible_delay_rows          INTEGER,
    cancelled_and_delayed_trips     INTEGER,
    error                           TEXT
);
