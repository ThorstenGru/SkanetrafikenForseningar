"""Coverage check: for a fully-completed service day, record what fraction
of each line's scheduled trips actually appeared (with any status) in the
realtime feed, and flag lines whose visibility today dropped well below
their OWN historical baseline.

Why not simply diff "scheduled" vs. "seen"? Empirically (verified
2026-07-05 against real data): only about 5% of ALL scheduled trips ever
appear in the TripUpdates feed on a given day, even on a day we scanned
continuously. Skånetrafiken's feed apparently only reports live predictions
for a subset of vehicles (likely GPS/AVL-tracked ones), not every scheduled
trip. A naive "scheduled minus seen" comparison would flag ~95% of
completely normal, on-time service as "missing" — false. So instead we
track each line's own typical visibility rate over a rolling window, and
only flag a day where a line's rate falls well below its own baseline.
That requires enough prior days of history to exist first — until then,
this correctly reports nothing rather than a misleading number.

Runs once daily (see housekeeping.yml), checking "yesterday" (Europe/Stockholm
local date) by default — by the time this runs, that whole service day is over.

Usage:
    python src/coverage_check.py                # yesterday, local time
    python src/coverage_check.py --date 20260704
"""

import argparse
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
import psycopg2.extras

import config
import db

WEEKDAY_COLS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

# A line needs at least this many prior days of data, and a baseline
# visibility rate of at least this much, before we'll try to detect an
# anomaly for it at all — below that, there's no meaningful signal.
MIN_BASELINE_DAYS = 7
MIN_BASELINE_RATE = 0.10
BASELINE_WINDOW_DAYS = 30
# Flag only a large, clear drop relative to the line's own normal rate.
ANOMALY_RATIO = 0.5


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
    """Returns [(trip_id, route_short_name), ...] for every trip scheduled that day."""
    services = active_service_ids(static_conn, target_date)
    if not services:
        return []
    placeholders = ",".join("?" * len(services))
    rows = static_conn.execute(
        "SELECT trip_id, route_id FROM trip_meta WHERE service_id IN (%s)" % placeholders,
        tuple(services),
    ).fetchall()
    routes = dict(static_conn.execute("SELECT route_id, short_name FROM routes").fetchall())
    return [(trip_id, routes.get(route_id, route_id)) for trip_id, route_id in rows]


def seen_trip_ids_for(cur, target_date):
    cur.execute("SELECT trip_id FROM seen_trips WHERE trip_start_date = %s", (target_date,))
    return {row[0] for row in cur.fetchall()}


def compute_line_visibility(scheduled, seen_ids):
    """scheduled: [(trip_id, route_short_name)]. Returns {route_short_name: (scheduled_count, seen_count)}."""
    counts = defaultdict(lambda: [0, 0])
    for trip_id, route_short_name in scheduled:
        counts[route_short_name][0] += 1
        if trip_id in seen_ids:
            counts[route_short_name][1] += 1
    return counts


def detect_anomalies(cur, target_date, line_counts):
    """Compare each line's rate today against its own rolling baseline (excluding today)."""
    window_start = target_date - timedelta(days=BASELINE_WINDOW_DAYS)
    cur.execute(
        """SELECT route_short_name, visibility_rate FROM line_daily_visibility
           WHERE trip_start_date >= %s AND trip_start_date < %s""",
        (window_start, target_date),
    )
    history = defaultdict(list)
    for route_short_name, rate in cur.fetchall():
        history[route_short_name].append(rate)

    anomalies = []
    for route_short_name, (scheduled_count, seen_count) in line_counts.items():
        rates = history.get(route_short_name, [])
        if len(rates) < MIN_BASELINE_DAYS:
            continue
        baseline_rate = sum(rates) / len(rates)
        if baseline_rate < MIN_BASELINE_RATE:
            continue
        actual_rate = seen_count / scheduled_count if scheduled_count else 0.0
        if actual_rate < baseline_rate * ANOMALY_RATIO:
            anomalies.append({
                "route_short_name": route_short_name,
                "scheduled_count": scheduled_count,
                "seen_count": seen_count,
                "actual_rate": actual_rate,
                "baseline_rate": baseline_rate,
                "baseline_days": len(rates),
            })
    return anomalies


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="YYYYMMDD (local Europe/Stockholm date). Default: yesterday.")
    args = parser.parse_args()

    if args.date:
        target_date = date(int(args.date[0:4]), int(args.date[4:6]), int(args.date[6:8]))
    else:
        target_date = (datetime.now(config.LOCAL_TZ) - timedelta(days=1)).date()

    static_conn = sqlite3.connect(config.STATIC_INDEX_PATH)
    scheduled = scheduled_trips_for(static_conn, target_date)
    static_conn.close()

    if not scheduled:
        print("No scheduled trips found for %s (check that the static index covers this date)." % target_date)
        return

    conn = db.connect()
    cur = conn.cursor()

    # Guard against measuring "visibility" for dates before the scanner
    # itself existed — that would just show 0%, not a real drop.
    cur.execute("SELECT MIN(run_at) FROM scan_runs")
    first_scan = cur.fetchone()[0]
    if first_scan is None or target_date < first_scan.astimezone(config.LOCAL_TZ).date():
        print("Skipping %s: before the scanner's first run (%s), not a real coverage signal." % (
            target_date, first_scan.date() if first_scan else "unknown"))
        cur.close()
        conn.close()
        return

    try:
        seen = seen_trip_ids_for(cur, target_date)
        line_counts = compute_line_visibility(scheduled, seen)
        now = datetime.now(timezone.utc)

        psycopg2.extras.execute_values(
            cur,
            """INSERT INTO line_daily_visibility
               (trip_start_date, route_short_name, scheduled_count, seen_count, visibility_rate, computed_at)
               VALUES %s
               ON CONFLICT (trip_start_date, route_short_name) DO UPDATE SET
                   scheduled_count = EXCLUDED.scheduled_count,
                   seen_count = EXCLUDED.seen_count,
                   visibility_rate = EXCLUDED.visibility_rate,
                   computed_at = EXCLUDED.computed_at""",
            [
                (target_date, route, sched, seen_n, (seen_n / sched if sched else 0.0), now)
                for route, (sched, seen_n) in line_counts.items()
            ],
        )

        anomalies = detect_anomalies(cur, target_date, line_counts)
        if anomalies:
            psycopg2.extras.execute_values(
                cur,
                """INSERT INTO line_visibility_anomalies
                   (trip_start_date, route_short_name, scheduled_count, seen_count, actual_rate, baseline_rate, baseline_days, detected_at)
                   VALUES %s
                   ON CONFLICT (trip_start_date, route_short_name) DO UPDATE SET
                       actual_rate = EXCLUDED.actual_rate,
                       baseline_rate = EXCLUDED.baseline_rate,
                       baseline_days = EXCLUDED.baseline_days,
                       detected_at = EXCLUDED.detected_at""",
                [
                    (target_date, a["route_short_name"], a["scheduled_count"], a["seen_count"],
                     a["actual_rate"], a["baseline_rate"], a["baseline_days"], now)
                    for a in anomalies
                ],
            )

        conn.commit()
        overall_seen = sum(s for _, s in line_counts.values())
        overall_scheduled = sum(c for c, _ in line_counts.values())
        print("Coverage check for %s: %d lines, %d/%d trips seen overall (%.1f%%), %d lines below their own baseline." % (
            target_date, len(line_counts), overall_seen, overall_scheduled,
            100 * overall_seen / overall_scheduled if overall_scheduled else 0, len(anomalies)))
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
