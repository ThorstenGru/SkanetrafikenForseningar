"""Generate a self-contained HTML dashboard from Postgres. No local SQLite
file involved for delay data — only the small static_index.sqlite (routes/
stops cache) is read locally, and even that isn't needed here since delays
rows already carry denormalized route/stop names written at scan time.

Two different windows, for two different jobs:
  - The "Historik per dag" table is a cheap SQL aggregate (COUNT/AVG/MAX
    GROUP BY day) over the FULL retention window (up to 45 days) — trend
    view, stays small regardless of history length.
  - The detailed row-level log defaults to the last few days only (--days),
    or a single day (--date), to keep the exported HTML from growing
    unbounded as 45 days of raw rows would make for a multi-hundred-MB file.

Usage:
    python src/build_dashboard.py                  # history trend (45d) + last 3 days of detail
    python src/build_dashboard.py --days 7          # last 7 days of detail
    python src/build_dashboard.py --date 20260705   # exactly one day of detail
    python src/build_dashboard.py --out dashboard.html
"""

import argparse
import json
import os
from datetime import date, datetime, timedelta, timezone

import psycopg2
import psycopg2.extras

import config
import db

TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard_template.html")

DEFAULT_DETAIL_DAYS = 3


def fmt_time(dt):
    if dt is None:
        return None
    return dt.astimezone().strftime("%H:%M")


def build_alert_lookups(cur):
    cur.execute(
        """SELECT e.trip_id, e.route_id, e.stop_id, a.description_text
           FROM alert_entities e JOIN alerts a ON a.alert_uid = e.alert_uid"""
    )
    by_trip, by_route, by_stop = {}, {}, {}
    for trip_id, route_id, stop_id, desc in cur.fetchall():
        if trip_id:
            by_trip.setdefault(trip_id, desc)
        if route_id:
            by_route.setdefault(route_id, desc)
        if stop_id:
            by_stop.setdefault(stop_id, desc)
    return by_trip, by_route, by_stop


def best_reason(lookups, trip_id, route_id, stop_id):
    by_trip, by_route, by_stop = lookups
    for d, key in ((by_trip, trip_id), (by_stop, stop_id), (by_route, route_id)):
        if key in d:
            return d[key].strip()
    return None


def classify(delay_sec, stop_schedule_relationship, is_final_stop):
    if stop_schedule_relationship == "SKIPPED":
        return "Hoppar over hallplats" if not is_final_stop else "Installd (nar inte slutstation)"
    if delay_sec and delay_sec > 60:
        return "Forsenad"
    if delay_sec and delay_sec < -60:
        return "Fore tiden"
    return "OK/marginell"


def fetch_history_trend(cur):
    """Cheap daily aggregate over the full retention window."""
    cur.execute(
        """SELECT
               trip_start_date,
               COUNT(*) FILTER (WHERE stop_schedule_relationship != 'SKIPPED') AS delay_rows,
               COUNT(*) FILTER (WHERE stop_schedule_relationship = 'SKIPPED') AS skipped_rows,
               AVG(GREATEST(COALESCE(departure_delay_sec, arrival_delay_sec, 0), 0)) FILTER (WHERE COALESCE(departure_delay_sec, arrival_delay_sec, 0) > 60) AS avg_delay_sec,
               MAX(GREATEST(COALESCE(departure_delay_sec, arrival_delay_sec, 0), 0)) AS worst_delay_sec
           FROM delays
           GROUP BY trip_start_date"""
    )
    delay_agg = {row[0]: row[1:] for row in cur.fetchall()}

    cur.execute("SELECT trip_start_date, COUNT(*) FROM trip_cancellations GROUP BY trip_start_date")
    cancel_agg = dict(cur.fetchall())

    all_dates = set(delay_agg) | set(cancel_agg)
    out = []
    for d in all_dates:
        delay_rows, skipped_rows, avg_delay_sec, worst_delay_sec = delay_agg.get(d, (0, 0, 0, 0))
        out.append({
            "date": d.strftime("%Y%m%d"),
            "count": (delay_rows or 0) + (skipped_rows or 0),
            "cancelled": (skipped_rows or 0) + cancel_agg.get(d, 0),
            "avgDelay": round(float(avg_delay_sec or 0) / 60, 1),
            "worst": round(float(worst_delay_sec or 0) / 60, 1),
        })
    return out


def fetch_missing_trips_by_day(cur):
    cur.execute("SELECT trip_start_date, COUNT(*) FROM missing_trips GROUP BY trip_start_date")
    return {d.strftime("%Y%m%d"): c for d, c in cur.fetchall()}


def fetch_detail_rows(cur, start_date, end_date, single_date):
    lookups = build_alert_lookups(cur)
    out = []

    if single_date:
        where, params = "WHERE trip_start_date = %s", (single_date,)
    else:
        where, params = "WHERE trip_start_date BETWEEN %s AND %s", (start_date, end_date)

    cur.execute(
        """SELECT trip_id, trip_start_date, route_id, route_short_name, destination_stop_name,
                  stop_id, stop_name, stop_sequence, is_final_stop, stop_schedule_relationship,
                  arrival_delay_sec, departure_delay_sec, arrival_time, departure_time,
                  scheduled_arrival, scheduled_departure, first_seen_at, last_seen_at, poll_count
           FROM delays %s""" % where,
        params,
    )
    for (trip_id, d, route_id, route_short_name, dest, stop_id, stop_name, seq, is_final,
         stop_rel, arr_delay, dep_delay, arr_time, dep_time, sched_arr, sched_dep,
         first_seen, last_seen, polls) in cur.fetchall():
        delay_sec = dep_delay if dep_delay not in (None, 0) else arr_delay
        out.append({
            "trip": trip_id, "date": d.strftime("%Y%m%d"), "line": route_short_name, "dest": dest,
            "stop": stop_name, "seq": seq, "final": bool(is_final),
            "status": classify(delay_sec, stop_rel, is_final),
            "relationship": stop_rel,
            "delayMin": round(delay_sec / 60, 1) if delay_sec is not None else None,
            "schedDep": fmt_time(sched_dep), "actDep": fmt_time(dep_time),
            "schedArr": fmt_time(sched_arr), "actArr": fmt_time(arr_time),
            "reason": best_reason(lookups, trip_id, route_id, stop_id),
            "firstSeen": first_seen.isoformat(), "lastSeen": last_seen.isoformat(), "polls": polls,
        })

    cur.execute(
        """SELECT trip_id, trip_start_date, route_id, route_short_name, destination_stop_name,
                  first_seen_at, last_seen_at, poll_count
           FROM trip_cancellations %s""" % where,
        params,
    )
    for trip_id, d, route_id, route_short_name, dest, first_seen, last_seen, polls in cur.fetchall():
        out.append({
            "trip": trip_id, "date": d.strftime("%Y%m%d"), "line": route_short_name, "dest": dest,
            "stop": "(HELA TUREN)", "seq": None, "final": None, "status": "Installd tur",
            "relationship": "CANCELED", "delayMin": None, "schedDep": None, "actDep": None,
            "schedArr": None, "actArr": None,
            "reason": best_reason(lookups, trip_id, route_id, None),
            "firstSeen": first_seen.isoformat(), "lastSeen": last_seen.isoformat(), "polls": polls,
        })

    cur.execute(
        """SELECT trip_id, trip_start_date, route_id, route_short_name, destination_stop_name, detected_at
           FROM missing_trips %s""" % where,
        params,
    )
    for trip_id, d, route_id, route_short_name, dest, detected_at in cur.fetchall():
        out.append({
            "trip": trip_id, "date": d.strftime("%Y%m%d"), "line": route_short_name, "dest": dest or "",
            "stop": "(ALDRIG SEDD I FEEDEN)", "seq": None, "final": None, "status": "Aldrig sedd",
            "relationship": "MISSING", "delayMin": None, "schedDep": None, "actDep": None,
            "schedArr": None, "actArr": None,
            "reason": "Turen fanns i tidtabellen men syntes aldrig i TripUpdates-feeden den dagen.",
            "firstSeen": detected_at.isoformat(), "lastSeen": detected_at.isoformat(), "polls": 0,
        })

    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="YYYYMMDD — exactly one day of raw detail.")
    parser.add_argument("--days", type=int, default=DEFAULT_DETAIL_DAYS, help="How many recent days of raw detail to include (ignored if --date is set).")
    parser.add_argument("--out", default=os.path.join(config.REPO_ROOT, "dashboard.html"))
    args = parser.parse_args()

    single_date = None
    if args.date:
        single_date = date(int(args.date[0:4]), int(args.date[4:6]), int(args.date[6:8]))
        start_date = end_date = single_date
    else:
        end_date = date.today()
        start_date = end_date - timedelta(days=args.days - 1)

    conn = db.connect()
    cur = conn.cursor()
    try:
        trend = fetch_history_trend(cur)
        missing_by_day = fetch_missing_trips_by_day(cur)
        for row in trend:
            row["missingTrips"] = missing_by_day.get(row["date"], 0)
        detail_rows = fetch_detail_rows(cur, start_date, end_date, single_date)
    finally:
        cur.close()
        conn.close()

    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template = f.read()

    payload = json.dumps(
        {"trend": trend, "rows": detail_rows}, ensure_ascii=False, separators=(",", ":")
    ).replace("</script", "<\\/script")
    html = template.replace("__DATA_JSON__", payload)

    out_dir = os.path.dirname(args.out)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)

    scope = single_date or ("%s .. %s" % (start_date, end_date))
    print("Dashboard skriven till %s (%d detaljrader for %s, %d dagar i historiktrenden)" % (
        args.out, len(detail_rows), scope, len(trend)))


if __name__ == "__main__":
    main()
