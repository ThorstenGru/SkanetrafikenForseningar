-- Skånetrafiken förseningar — Postgres (Supabase) schema.
-- Run once against a fresh project. Safe to re-run (IF NOT EXISTS everywhere).
--
-- This file alone is NOT the current schema -- it's the original baseline,
-- frozen on purpose (see docs/RUNBOOK.md#applying-migrations). Every
-- change since then lives in src/migrations/, numbered in order, and must
-- ALL be applied for the application code to actually work (e.g.
-- housekeeping.py references housekeeping_runs.line_anomalies_deleted,
-- which only exists after 008_split_housekeeping_counter.sql). A database
-- provisioned from just this file will fail on the first script that
-- touches a column a later migration added.

CREATE TABLE IF NOT EXISTS delays (
    trip_id                    TEXT NOT NULL,
    trip_start_date            DATE NOT NULL,
    route_id                   TEXT,
    route_short_name           TEXT,
    vehicle_type                TEXT,
    trip_number                 TEXT,
    distance_km                  REAL,
    sommarticket_valid           BOOLEAN,
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
CREATE INDEX IF NOT EXISTS idx_delays_vehicle_type ON delays (vehicle_type);

CREATE TABLE IF NOT EXISTS trip_cancellations (
    trip_id             TEXT NOT NULL,
    trip_start_date     DATE NOT NULL,
    route_id            TEXT,
    route_short_name    TEXT,
    vehicle_type         TEXT,
    trip_number          TEXT,
    distance_km           REAL,
    sommarticket_valid    BOOLEAN,
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

-- Populated once daily by coverage_check.py for a fully-completed day: for
-- every line, what fraction of its scheduled trips actually appeared (with
-- ANY status) in the realtime feed that day. Only ~5% of all scheduled
-- trips ever appear in TripUpdates at all (empirically verified — most
-- vehicles aren't live-tracked), so a per-line rate — not "scheduled minus
-- seen" — is the only way to get a meaningful signal. See ARCHITECTURE.md.
CREATE TABLE IF NOT EXISTS line_daily_visibility (
    trip_start_date     DATE NOT NULL,
    route_short_name    TEXT NOT NULL,
    scheduled_count     INTEGER NOT NULL,
    seen_count          INTEGER NOT NULL,
    visibility_rate     REAL NOT NULL,
    computed_at         TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (trip_start_date, route_short_name)
);
CREATE INDEX IF NOT EXISTS idx_line_visibility_route ON line_daily_visibility (route_short_name);

-- A line-day is flagged here only when its visibility rate drops well below
-- THAT LINE'S OWN rolling baseline (not below 100% of schedule) — see
-- coverage_check.py. Requires enough baseline history to exist first, so
-- this stays empty until the project has run for a couple of weeks.
CREATE TABLE IF NOT EXISTS line_visibility_anomalies (
    trip_start_date     DATE NOT NULL,
    route_short_name    TEXT NOT NULL,
    scheduled_count     INTEGER,
    seen_count          INTEGER,
    actual_rate         REAL,
    baseline_rate       REAL,
    baseline_days       INTEGER,
    detected_at         TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (trip_start_date, route_short_name)
);

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
    line_visibility_deleted INTEGER,
    alerts_deleted      INTEGER,
    scan_runs_deleted   INTEGER,
    error               TEXT
);
