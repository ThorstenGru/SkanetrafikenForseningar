-- Skånetrafiken förseningar — Postgres (Supabase) schema.
-- Run once against a fresh project. Safe to re-run (IF NOT EXISTS everywhere).

CREATE TABLE IF NOT EXISTS delays (
    trip_id                    TEXT NOT NULL,
    trip_start_date            DATE NOT NULL,
    route_id                   TEXT,
    route_short_name           TEXT,
    direction_id                SMALLINT,
    destination_stop_name      TEXT,
    stop_id                     TEXT NOT NULL,
    stop_name                   TEXT,
    stop_sequence                INTEGER,
    is_final_stop               BOOLEAN NOT NULL DEFAULT FALSE,
    stop_schedule_relationship  TEXT,
    trip_schedule_relationship  TEXT,
    arrival_delay_sec           INTEGER,
    departure_delay_sec         INTEGER,
    arrival_time                TIMESTAMPTZ,
    departure_time               TIMESTAMPTZ,
    scheduled_arrival            TIMESTAMPTZ,
    scheduled_departure          TIMESTAMPTZ,
    max_abs_delay_sec           INTEGER,
    first_seen_at                TIMESTAMPTZ NOT NULL,
    last_seen_at                 TIMESTAMPTZ NOT NULL,
    poll_count                   INTEGER NOT NULL DEFAULT 1,
    -- Keyed on stop_sequence, NOT stop_id: a circular/loop route can revisit
    -- the same physical stop_id twice in one trip, which would otherwise
    -- collide. stop_sequence is guaranteed unique per trip by the GTFS spec.
    PRIMARY KEY (trip_id, trip_start_date, stop_sequence)
);
CREATE INDEX IF NOT EXISTS idx_delays_date ON delays (trip_start_date);
CREATE INDEX IF NOT EXISTS idx_delays_route ON delays (route_short_name);

CREATE TABLE IF NOT EXISTS trip_cancellations (
    trip_id             TEXT NOT NULL,
    trip_start_date     DATE NOT NULL,
    route_id            TEXT,
    route_short_name    TEXT,
    destination_stop_name TEXT,
    first_seen_at        TIMESTAMPTZ NOT NULL,
    last_seen_at         TIMESTAMPTZ NOT NULL,
    poll_count           INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (trip_id, trip_start_date)
);
CREATE INDEX IF NOT EXISTS idx_cancellations_date ON trip_cancellations (trip_start_date);

-- Every trip_id seen in a TripUpdates poll, regardless of delay — the
-- presence log that makes the coverage check possible (a trip missing from
-- this table for a day it was scheduled never showed up in the feed at all).
CREATE TABLE IF NOT EXISTS seen_trips (
    trip_id           TEXT NOT NULL,
    trip_start_date   DATE NOT NULL,
    route_short_name  TEXT,
    first_seen_at      TIMESTAMPTZ NOT NULL,
    last_seen_at       TIMESTAMPTZ NOT NULL,
    poll_count         INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (trip_id, trip_start_date)
);
CREATE INDEX IF NOT EXISTS idx_seen_trips_date ON seen_trips (trip_start_date);

-- Populated once daily by coverage_check.py for a fully-completed day:
-- trips that were scheduled per the static timetable but never appeared in
-- seen_trips at all — a real, otherwise-invisible gap in Skånetrafiken's own
-- realtime feed.
CREATE TABLE IF NOT EXISTS missing_trips (
    trip_id                TEXT NOT NULL,
    trip_start_date        DATE NOT NULL,
    route_id               TEXT,
    route_short_name       TEXT,
    destination_stop_name  TEXT,
    scheduled_departure    TIMESTAMPTZ,
    detected_at             TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (trip_id, trip_start_date)
);
CREATE INDEX IF NOT EXISTS idx_missing_trips_date ON missing_trips (trip_start_date);

CREATE TABLE IF NOT EXISTS alerts (
    alert_uid               TEXT PRIMARY KEY,
    cause_code              INTEGER,
    cause_label             TEXT,
    effect_code             INTEGER,
    effect_label            TEXT,
    header_text             TEXT,
    description_text        TEXT,
    active_period_start     TIMESTAMPTZ,
    active_period_end       TIMESTAMPTZ,
    first_seen_at            TIMESTAMPTZ NOT NULL,
    last_seen_at             TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alerts_last_seen ON alerts (last_seen_at);

CREATE TABLE IF NOT EXISTS alert_entities (
    id          BIGSERIAL PRIMARY KEY,
    alert_uid   TEXT NOT NULL REFERENCES alerts (alert_uid) ON DELETE CASCADE,
    route_id    TEXT,
    trip_id     TEXT,
    stop_id     TEXT
);
CREATE INDEX IF NOT EXISTS idx_alert_entities_route ON alert_entities (route_id);
CREATE INDEX IF NOT EXISTS idx_alert_entities_trip ON alert_entities (trip_id);
CREATE INDEX IF NOT EXISTS idx_alert_entities_stop ON alert_entities (stop_id);

CREATE TABLE IF NOT EXISTS scan_runs (
    id                      BIGSERIAL PRIMARY KEY,
    run_at                  TIMESTAMPTZ NOT NULL,
    delays_seen             INTEGER,
    delays_new              INTEGER,
    cancellations_seen      INTEGER,
    alerts_seen             INTEGER,
    alerts_new              INTEGER,
    static_refreshed        BOOLEAN NOT NULL DEFAULT FALSE,
    error                   TEXT
);

CREATE TABLE IF NOT EXISTS housekeeping_runs (
    id                  BIGSERIAL PRIMARY KEY,
    run_at              TIMESTAMPTZ NOT NULL,
    cutoff_date         DATE NOT NULL,
    delays_deleted      INTEGER,
    cancellations_deleted INTEGER,
    seen_trips_deleted  INTEGER,
    missing_trips_deleted INTEGER,
    alerts_deleted      INTEGER,
    scan_runs_deleted   INTEGER,
    error               TEXT
);
