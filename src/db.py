"""SQLite schema and upsert helpers for the delay/alert history database."""

import os
import sqlite3

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS delays (
    trip_id TEXT NOT NULL,
    trip_start_date TEXT NOT NULL,
    route_id TEXT,
    route_short_name TEXT,
    direction_id INTEGER,
    destination_stop_name TEXT,
    stop_id TEXT NOT NULL,
    stop_name TEXT,
    stop_sequence INTEGER,
    is_final_stop INTEGER DEFAULT 0,
    stop_schedule_relationship TEXT,
    trip_schedule_relationship TEXT,
    arrival_delay_sec INTEGER,
    departure_delay_sec INTEGER,
    arrival_time_epoch INTEGER,
    departure_time_epoch INTEGER,
    scheduled_arrival_epoch INTEGER,
    scheduled_departure_epoch INTEGER,
    max_abs_delay_sec INTEGER,
    weekday INTEGER,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    poll_count INTEGER DEFAULT 1,
    PRIMARY KEY (trip_id, trip_start_date, stop_id)
);

CREATE TABLE IF NOT EXISTS trip_cancellations (
    trip_id TEXT NOT NULL,
    trip_start_date TEXT NOT NULL,
    route_id TEXT,
    route_short_name TEXT,
    destination_stop_name TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    poll_count INTEGER DEFAULT 1,
    PRIMARY KEY (trip_id, trip_start_date)
);

CREATE TABLE IF NOT EXISTS alerts (
    alert_uid TEXT PRIMARY KEY,
    cause_code INTEGER,
    cause_label TEXT,
    effect_code INTEGER,
    effect_label TEXT,
    header_text TEXT,
    description_text TEXT,
    active_period_start_epoch INTEGER,
    active_period_end_epoch INTEGER,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alert_entities (
    alert_uid TEXT NOT NULL,
    route_id TEXT,
    trip_id TEXT,
    stop_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_alert_entities_route ON alert_entities(route_id);
CREATE INDEX IF NOT EXISTS idx_alert_entities_stop ON alert_entities(stop_id);
CREATE INDEX IF NOT EXISTS idx_alert_entities_trip ON alert_entities(trip_id);

CREATE TABLE IF NOT EXISTS scan_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at TEXT NOT NULL,
    delays_seen INTEGER,
    delays_new INTEGER,
    cancellations_seen INTEGER,
    alerts_seen INTEGER,
    alerts_new INTEGER,
    static_refreshed INTEGER DEFAULT 0,
    error TEXT
);
"""


def connect():
    os.makedirs(config.DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.executescript(SCHEMA)
    return conn


def upsert_delay(conn, row, now_iso):
    """row: dict matching the delays columns except first/last_seen_at/poll_count."""
    existing = conn.execute(
        "SELECT max_abs_delay_sec, poll_count FROM delays WHERE trip_id=? AND trip_start_date=? AND stop_id=?",
        (row["trip_id"], row["trip_start_date"], row["stop_id"]),
    ).fetchone()

    abs_delay = max(abs(row.get("arrival_delay_sec") or 0), abs(row.get("departure_delay_sec") or 0))

    if existing is None:
        conn.execute(
            """INSERT INTO delays (
                trip_id, trip_start_date, route_id, route_short_name, direction_id,
                destination_stop_name, stop_id, stop_name, stop_sequence, is_final_stop,
                stop_schedule_relationship, trip_schedule_relationship,
                arrival_delay_sec, departure_delay_sec, arrival_time_epoch, departure_time_epoch,
                scheduled_arrival_epoch, scheduled_departure_epoch, max_abs_delay_sec, weekday,
                first_seen_at, last_seen_at, poll_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
            (
                row["trip_id"], row["trip_start_date"], row["route_id"], row["route_short_name"],
                row["direction_id"], row["destination_stop_name"], row["stop_id"], row["stop_name"],
                row["stop_sequence"], row["is_final_stop"], row["stop_schedule_relationship"],
                row["trip_schedule_relationship"], row["arrival_delay_sec"], row["departure_delay_sec"],
                row["arrival_time_epoch"], row["departure_time_epoch"], row["scheduled_arrival_epoch"],
                row["scheduled_departure_epoch"], abs_delay, row["weekday"], now_iso, now_iso,
            ),
        )
        return True
    else:
        new_max = max(existing[0] or 0, abs_delay)
        conn.execute(
            """UPDATE delays SET
                arrival_delay_sec=?, departure_delay_sec=?, arrival_time_epoch=?, departure_time_epoch=?,
                stop_schedule_relationship=?, trip_schedule_relationship=?,
                max_abs_delay_sec=?, last_seen_at=?, poll_count=poll_count+1
               WHERE trip_id=? AND trip_start_date=? AND stop_id=?""",
            (
                row["arrival_delay_sec"], row["departure_delay_sec"], row["arrival_time_epoch"],
                row["departure_time_epoch"], row["stop_schedule_relationship"], row["trip_schedule_relationship"],
                new_max, now_iso, row["trip_id"], row["trip_start_date"], row["stop_id"],
            ),
        )
        return False


def upsert_cancellation(conn, row, now_iso):
    existing = conn.execute(
        "SELECT 1 FROM trip_cancellations WHERE trip_id=? AND trip_start_date=?",
        (row["trip_id"], row["trip_start_date"]),
    ).fetchone()
    if existing is None:
        conn.execute(
            """INSERT INTO trip_cancellations
               (trip_id, trip_start_date, route_id, route_short_name, destination_stop_name,
                first_seen_at, last_seen_at, poll_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
            (row["trip_id"], row["trip_start_date"], row["route_id"], row["route_short_name"],
             row["destination_stop_name"], now_iso, now_iso),
        )
        return True
    else:
        conn.execute(
            "UPDATE trip_cancellations SET last_seen_at=?, poll_count=poll_count+1 WHERE trip_id=? AND trip_start_date=?",
            (now_iso, row["trip_id"], row["trip_start_date"]),
        )
        return False


def upsert_alert(conn, alert_uid, fields, entities, now_iso):
    existing = conn.execute("SELECT 1 FROM alerts WHERE alert_uid=?", (alert_uid,)).fetchone()
    if existing is None:
        conn.execute(
            """INSERT INTO alerts (
                alert_uid, cause_code, cause_label, effect_code, effect_label,
                header_text, description_text, active_period_start_epoch, active_period_end_epoch,
                first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                alert_uid, fields["cause_code"], fields["cause_label"], fields["effect_code"],
                fields["effect_label"], fields["header_text"], fields["description_text"],
                fields["active_period_start_epoch"], fields["active_period_end_epoch"], now_iso, now_iso,
            ),
        )
        conn.executemany(
            "INSERT INTO alert_entities (alert_uid, route_id, trip_id, stop_id) VALUES (?, ?, ?, ?)",
            [(alert_uid, e.get("route_id"), e.get("trip_id"), e.get("stop_id")) for e in entities],
        )
        return True
    else:
        conn.execute("UPDATE alerts SET last_seen_at=? WHERE alert_uid=?", (now_iso, alert_uid))
        return False


def record_scan_run(conn, stats):
    conn.execute(
        """INSERT INTO scan_runs (run_at, delays_seen, delays_new, cancellations_seen, alerts_seen, alerts_new, static_refreshed, error)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            stats["run_at"], stats["delays_seen"], stats["delays_new"], stats["cancellations_seen"],
            stats["alerts_seen"], stats["alerts_new"], int(stats["static_refreshed"]), stats.get("error"),
        ),
    )
