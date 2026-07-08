"""Postgres (Supabase) connection and batch upsert helpers.

Schema lives in schema.sql — apply it once against a fresh project. This
module only contains runtime read/write helpers, no DDL.

Everything is batched via execute_values (one round-trip per table per scan,
not one per row) — a single scan can touch 5,000-15,000 delay rows, and doing
that as individual statements against a cloud DB is slow enough to blow past
Supabase's statement timeout. See docs/ARCHITECTURE.md.
"""

import psycopg2
import psycopg2.extras

import config

DELAY_COLUMNS = [
    "trip_id", "trip_start_date", "route_id", "route_short_name", "vehicle_type",
    "trip_number", "distance_km", "sommarticket_valid", "direction_id",
    "destination_stop_name", "stop_id", "stop_name", "stop_sequence", "is_final_stop",
    "is_origin_stop", "stop_schedule_relationship", "trip_schedule_relationship",
    "arrival_delay_sec", "departure_delay_sec", "arrival_time", "departure_time",
    "scheduled_arrival", "scheduled_departure",
]


def connect():
    return psycopg2.connect(config.database_url(), connect_timeout=30)


def upsert_delays_batch(cur, rows, now):
    """rows: list of dicts with DELAY_COLUMNS keys. Returns count of newly-inserted rows."""
    if not rows:
        return 0
    values = [
        tuple(row[c] for c in DELAY_COLUMNS) + (max(abs(row.get("arrival_delay_sec") or 0), abs(row.get("departure_delay_sec") or 0)), now, now)
        for row in rows
    ]
    results = psycopg2.extras.execute_values(
        cur,
        """INSERT INTO delays (%s, max_abs_delay_sec, first_seen_at, last_seen_at)
           VALUES %%s
           ON CONFLICT (trip_id, trip_start_date, stop_sequence) DO UPDATE SET
               -- Only let an incoming row overwrite the observed values when
               -- it's at least as new as what's already stored. Without this,
               -- a backfill run replaying an older KoDa snapshot's own
               -- timestamp as `now` could silently clobber a more-current
               -- live-scanned delay/time with a stale one, even though
               -- last_seen_at (GREATEST'd below) keeps correctly advancing.
               arrival_delay_sec = CASE WHEN EXCLUDED.last_seen_at >= delays.last_seen_at THEN EXCLUDED.arrival_delay_sec ELSE delays.arrival_delay_sec END,
               departure_delay_sec = CASE WHEN EXCLUDED.last_seen_at >= delays.last_seen_at THEN EXCLUDED.departure_delay_sec ELSE delays.departure_delay_sec END,
               arrival_time = CASE WHEN EXCLUDED.last_seen_at >= delays.last_seen_at THEN EXCLUDED.arrival_time ELSE delays.arrival_time END,
               departure_time = CASE WHEN EXCLUDED.last_seen_at >= delays.last_seen_at THEN EXCLUDED.departure_time ELSE delays.departure_time END,
               stop_schedule_relationship = CASE WHEN EXCLUDED.last_seen_at >= delays.last_seen_at THEN EXCLUDED.stop_schedule_relationship ELSE delays.stop_schedule_relationship END,
               trip_schedule_relationship = CASE WHEN EXCLUDED.last_seen_at >= delays.last_seen_at THEN EXCLUDED.trip_schedule_relationship ELSE delays.trip_schedule_relationship END,
               max_abs_delay_sec = GREATEST(delays.max_abs_delay_sec, EXCLUDED.max_abs_delay_sec),
               last_seen_at = GREATEST(delays.last_seen_at, EXCLUDED.last_seen_at),
               poll_count = delays.poll_count + 1
           RETURNING (xmax = 0) AS inserted""" % ", ".join(DELAY_COLUMNS),
        values,
        page_size=1000,
        fetch=True,
    )
    return sum(1 for r in results if r[0])


def upsert_cancellations_batch(cur, rows, now):
    if not rows:
        return 0
    values = [
        (r["trip_id"], r["trip_start_date"], r["route_id"], r["route_short_name"], r["vehicle_type"],
         r["trip_number"], r["distance_km"], r["sommarticket_valid"], r["destination_stop_name"], now, now)
        for r in rows
    ]
    results = psycopg2.extras.execute_values(
        cur,
        """INSERT INTO trip_cancellations
           (trip_id, trip_start_date, route_id, route_short_name, vehicle_type, trip_number,
            distance_km, sommarticket_valid, destination_stop_name, first_seen_at, last_seen_at)
           VALUES %s
           ON CONFLICT (trip_id, trip_start_date) DO UPDATE SET
               last_seen_at = GREATEST(trip_cancellations.last_seen_at, EXCLUDED.last_seen_at),
               poll_count = trip_cancellations.poll_count + 1
           RETURNING (xmax = 0) AS inserted""",
        values,
        fetch=True,
    )
    return sum(1 for r in results if r[0])


def upsert_seen_trips_batch(cur, rows, now):
    """rows: list of (trip_id, trip_start_date, route_short_name)."""
    if not rows:
        return
    values = [(trip_id, trip_start_date, route_short_name, now, now) for trip_id, trip_start_date, route_short_name in rows]
    psycopg2.extras.execute_values(
        cur,
        """INSERT INTO seen_trips (trip_id, trip_start_date, route_short_name, first_seen_at, last_seen_at)
           VALUES %s
           ON CONFLICT (trip_id, trip_start_date) DO UPDATE SET
               last_seen_at = GREATEST(seen_trips.last_seen_at, EXCLUDED.last_seen_at),
               poll_count = seen_trips.poll_count + 1""",
        values,
    )


def upsert_alerts_batch(cur, alerts, now):
    """alerts: list of (alert_uid, fields_dict, entities_list). Returns count newly-inserted."""
    if not alerts:
        return 0
    values = [
        (uid, f["cause_code"], f["cause_label"], f["effect_code"], f["effect_label"],
         f["header_text"], f["description_text"], f["active_period_start"], f["active_period_end"], now, now)
        for uid, f, _ in alerts
    ]
    results = psycopg2.extras.execute_values(
        cur,
        """INSERT INTO alerts (
               alert_uid, cause_code, cause_label, effect_code, effect_label,
               header_text, description_text, active_period_start, active_period_end,
               first_seen_at, last_seen_at
           ) VALUES %s
           ON CONFLICT (alert_uid) DO UPDATE SET last_seen_at = GREATEST(alerts.last_seen_at, EXCLUDED.last_seen_at)
           RETURNING alert_uid, (xmax = 0) AS inserted""",
        values,
        fetch=True,
    )
    inserted_uids = {uid for uid, was_inserted in results if was_inserted}

    entity_rows = [
        (uid, e.get("route_id"), e.get("trip_id"), e.get("stop_id"))
        for uid, _, entities in alerts if uid in inserted_uids
        for e in entities
    ]
    if entity_rows:
        psycopg2.extras.execute_values(
            cur,
            "INSERT INTO alert_entities (alert_uid, route_id, trip_id, stop_id) VALUES %s",
            entity_rows,
        )
    return len(inserted_uids)


TRAIN_ANNOUNCEMENT_COLUMNS = [
    "advertised_train_number", "traffic_date", "location_signature", "activity_type",
    "advertised_time_at_location", "estimated_time_at_location", "time_at_location",
    "canceled", "track_at_location", "deviation_text", "operator", "modified_time",
]


def upsert_train_announcements_batch(cur, rows, now):
    """rows: list of dicts with TRAIN_ANNOUNCEMENT_COLUMNS keys, from
    scan_trafikverket.py. Returns count of newly-inserted rows. Mirrors
    upsert_delays_batch's "don't let a stale re-poll clobber a newer value"
    guard, keyed on Trafikverket's own modified_time instead of last_seen_at
    since that's the field their API uses to signal "this changed"."""
    if not rows:
        return 0
    values = [tuple(row[c] for c in TRAIN_ANNOUNCEMENT_COLUMNS) + (now, now) for row in rows]
    results = psycopg2.extras.execute_values(
        cur,
        """INSERT INTO train_announcements (%s, first_seen_at, last_seen_at)
           VALUES %%s
           ON CONFLICT (advertised_train_number, traffic_date, location_signature, activity_type) DO UPDATE SET
               estimated_time_at_location = CASE WHEN EXCLUDED.modified_time >= train_announcements.modified_time THEN EXCLUDED.estimated_time_at_location ELSE train_announcements.estimated_time_at_location END,
               time_at_location = CASE WHEN EXCLUDED.modified_time >= train_announcements.modified_time THEN EXCLUDED.time_at_location ELSE train_announcements.time_at_location END,
               canceled = CASE WHEN EXCLUDED.modified_time >= train_announcements.modified_time THEN EXCLUDED.canceled ELSE train_announcements.canceled END,
               track_at_location = CASE WHEN EXCLUDED.modified_time >= train_announcements.modified_time THEN EXCLUDED.track_at_location ELSE train_announcements.track_at_location END,
               deviation_text = CASE WHEN EXCLUDED.modified_time >= train_announcements.modified_time THEN EXCLUDED.deviation_text ELSE train_announcements.deviation_text END,
               modified_time = GREATEST(train_announcements.modified_time, EXCLUDED.modified_time),
               last_seen_at = GREATEST(train_announcements.last_seen_at, EXCLUDED.last_seen_at),
               poll_count = train_announcements.poll_count + 1
           RETURNING (xmax = 0) AS inserted""" % ", ".join(TRAIN_ANNOUNCEMENT_COLUMNS),
        values,
        page_size=1000,
        fetch=True,
    )
    return sum(1 for r in results if r[0])


def get_trafikverket_changeid(cur):
    """None on first-ever run — scan_trafikverket.py must then send a
    changeid-free query to establish a starting point, per Trafikverket's
    own documented polling pattern (see docs/TRAFIKVERKET_INTEGRATION.md)."""
    cur.execute("SELECT changeid FROM trafikverket_poll_state WHERE id")
    row = cur.fetchone()
    return row[0] if row else None


def set_trafikverket_changeid(cur, changeid, now):
    cur.execute(
        """INSERT INTO trafikverket_poll_state (id, changeid, updated_at) VALUES (TRUE, %s, %s)
           ON CONFLICT (id) DO UPDATE SET changeid = EXCLUDED.changeid, updated_at = EXCLUDED.updated_at""",
        (changeid, now),
    )


def record_scan_run(cur, stats):
    cur.execute(
        """INSERT INTO scan_runs (run_at, delays_seen, delays_new, cancellations_seen, alerts_seen, alerts_new, static_refreshed, error)
           VALUES (%(run_at)s, %(delays_seen)s, %(delays_new)s, %(cancellations_seen)s, %(alerts_seen)s, %(alerts_new)s, %(static_refreshed)s, %(error)s)""",
        stats,
    )
