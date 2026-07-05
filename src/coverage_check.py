"""Coverage check: for a fully-completed service day, find trip_ids that were
scheduled per the static timetable but never showed up in seen_trips at all —
i.e. Skånetrafiken's own realtime feed never mentioned them, not even as
SCHEDULED. That's a real, otherwise-invisible gap: a trip that silently never
appeared is indistinguishable from "on time" under the normal delay-only
logging, unless we cross-check against the full schedule.

Runs once daily (see housekeeping.yml), checking "yesterday" (Europe/Stockholm
local date) by default — by the time this runs, that whole service day is over.

Usage:
    python src/coverage_check.py                # yesterday, local time
    python src/coverage_check.py --date 20260704
"""

import argparse
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import psycopg2.extras

import config
import db

WEEKDAY_COLS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _yyyymmdd(d):
    return d.strftime("%Y%m%d")


def active_service_ids(static_conn, target_date):
    weekday_col = WEEKDAY_COLS[target_date.weekday()]
    ymd = _yyyymmdd(target_date)

    base_active = {
        row[0] for row in static_conn.execute(
            "SELECT service_id FROM calendar WHERE %s = 1 AND start_date <= ? AND end_date >= ?" % weekday_col,
            (ymd, ymd),
        )
    }
    additions = {
        row[0] for row in static_conn.execute(
            "SELECT service_id FROM calendar_dates WHERE date = ? AND exception_type = 1", (ymd,)
        )
    }
    removals = {
        row[0] for row in static_conn.execute(
            "SELECT service_id FROM calendar_dates WHERE date = ? AND exception_type = 2", (ymd,)
        )
    }
    return (base_active | additions) - removals


def scheduled_trips_for(static_conn, target_date):
    services = active_service_ids(static_conn, target_date)
    if not services:
        return []
    placeholders = ",".join("?" * len(services))
    rows = static_conn.execute(
        "SELECT trip_id, route_id, destination_stop_name FROM trip_meta WHERE service_id IN (%s)" % placeholders,
        tuple(services),
    ).fetchall()
    routes = dict(static_conn.execute("SELECT route_id, short_name FROM routes").fetchall())
    return [(trip_id, route_id, routes.get(route_id, route_id), dest) for trip_id, route_id, dest in rows]


def seen_trip_ids_for(cur, target_date):
    cur.execute("SELECT trip_id FROM seen_trips WHERE trip_start_date = %s", (target_date,))
    return {row[0] for row in cur.fetchall()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="YYYYMMDD (local Europe/Stockholm date). Default: yesterday.")
    args = parser.parse_args()

    if args.date:
        target_date = date(int(args.date[0:4]), int(args.date[4:6]), int(args.date[6:8]))
    else:
        target_date = (datetime.now(ZoneInfo("Europe/Stockholm")) - timedelta(days=1)).date()

    static_conn = sqlite3.connect(config.STATIC_INDEX_PATH)
    scheduled = scheduled_trips_for(static_conn, target_date)
    static_conn.close()

    if not scheduled:
        print("Inga schemalagda turer hittades for %s (kontrollera att static-indexet tacker detta datum)." % target_date)
        return

    conn = db.connect()
    cur = conn.cursor()
    try:
        seen = seen_trip_ids_for(cur, target_date)
        missing = [row for row in scheduled if row[0] not in seen]

        now = datetime.now(timezone.utc)
        if missing:
            psycopg2.extras.execute_values(
                cur,
                """INSERT INTO missing_trips (trip_id, trip_start_date, route_id, route_short_name, destination_stop_name, scheduled_departure, detected_at)
                   VALUES %s ON CONFLICT (trip_id, trip_start_date) DO NOTHING""",
                [(trip_id, target_date, route_id, route_short_name, dest, None, now) for trip_id, route_id, route_short_name, dest in missing],
            )
        conn.commit()
        print("Tackningskontroll for %s: %d schemalagda turer, %d sedda, %d saknade (aldrig sedda i realtidsfeeden)." % (
            target_date, len(scheduled), len(seen), len(missing)))
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
