"""Generate a self-contained HTML dashboard of recorded deviations, from the
local forseningar.db. No network access required.

By default exports the FULL recorded history (all days), so you can browse
day-to-day trends and drill into any past day in the same file. Pass --date
to scope it down to a single day once the history grows large.

Usage:
    python src/build_dashboard.py                # all recorded history
    python src/build_dashboard.py --date 20260705 # just one day
    python src/build_dashboard.py --out dashboard.html
"""

import argparse
import json
import os
import sqlite3
from datetime import datetime, timezone

import config

TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard_template.html")


def fmt_time(epoch):
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, tz=timezone.utc).astimezone().strftime("%H:%M")


def build_alert_lookups(conn):
    by_trip, by_route, by_stop = {}, {}, {}
    for trip_id, route_id, stop_id, cause_label, header_text, description_text in conn.execute(
        """SELECT e.trip_id, e.route_id, e.stop_id, a.cause_label, a.header_text, a.description_text
           FROM alert_entities e JOIN alerts a ON a.alert_uid = e.alert_uid"""
    ):
        text = {"cause": cause_label, "header": header_text, "desc": description_text}
        if trip_id:
            by_trip.setdefault(trip_id, []).append(text)
        if route_id:
            by_route.setdefault(route_id, []).append(text)
        if stop_id:
            by_stop.setdefault(stop_id, []).append(text)
    return by_trip, by_route, by_stop


def best_reason(lookups, trip_id, route_id, stop_id):
    by_trip, by_route, by_stop = lookups
    for d, key in ((by_trip, trip_id), (by_stop, stop_id), (by_route, route_id)):
        if key in d:
            return d[key][0]["desc"].strip()
    return None


def classify(row):
    dep_delay = row["departure_delay_sec"]
    arr_delay = row["arrival_delay_sec"]
    delay_sec = dep_delay if dep_delay not in (None, 0) else arr_delay
    status = row["stop_schedule_relationship"]
    if status == "SKIPPED":
        return ("Hoppar over hallplats" if not row["is_final_stop"] else "Installd (nar inte slutstation)"), delay_sec
    if delay_sec and delay_sec > 60:
        return "Forsenad", delay_sec
    if delay_sec and delay_sec < -60:
        return "Fore tiden", delay_sec
    return "OK/marginell", delay_sec


def export_rows(conn, date_str=None):
    """date_str=None exports the full recorded history (all days)."""
    lookups = build_alert_lookups(conn)
    out = []

    where = "WHERE trip_start_date = ?" if date_str else ""
    params = (date_str,) if date_str else ()

    for row in conn.execute("SELECT * FROM delays %s" % where, params):
        status, delay_sec = classify(row)
        out.append({
            "trip": row["trip_id"],
            "date": row["trip_start_date"],
            "line": row["route_short_name"],
            "dest": row["destination_stop_name"],
            "stop": row["stop_name"],
            "seq": row["stop_sequence"],
            "final": bool(row["is_final_stop"]),
            "status": status,
            "relationship": row["stop_schedule_relationship"],
            "delayMin": round(delay_sec / 60, 1) if delay_sec is not None else None,
            "schedDep": fmt_time(row["scheduled_departure_epoch"]),
            "actDep": fmt_time(row["departure_time_epoch"]),
            "schedArr": fmt_time(row["scheduled_arrival_epoch"]),
            "actArr": fmt_time(row["arrival_time_epoch"]),
            "weekday": row["weekday"],
            "reason": best_reason(lookups, row["trip_id"], row["route_id"], row["stop_id"]),
            "firstSeen": row["first_seen_at"],
            "lastSeen": row["last_seen_at"],
            "polls": row["poll_count"],
        })

    for row in conn.execute("SELECT * FROM trip_cancellations %s" % where, params):
        out.append({
            "trip": row["trip_id"], "date": row["trip_start_date"],
            "line": row["route_short_name"], "dest": row["destination_stop_name"],
            "stop": "(HELA TUREN)", "seq": None, "final": None, "status": "Installd tur",
            "relationship": "CANCELED", "delayMin": None, "schedDep": None, "actDep": None,
            "schedArr": None, "actArr": None, "weekday": None,
            "reason": best_reason(lookups, row["trip_id"], row["route_id"], None),
            "firstSeen": row["first_seen_at"], "lastSeen": row["last_seen_at"], "polls": row["poll_count"],
        })

    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="YYYYMMDD. Omit to export the full recorded history.")
    parser.add_argument("--out", default=os.path.join(config.REPO_ROOT, "dashboard.html"))
    args = parser.parse_args()

    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = export_rows(conn, args.date)
    conn.close()

    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template = f.read()

    payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).replace("</script", "<\\/script")
    html = template.replace("__DATA_JSON__", payload)

    out_dir = os.path.dirname(args.out)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)

    scope = args.date or ("hela historiken, %d dagar" % len({r["date"] for r in rows}) if rows else "hela historiken")
    print("Dashboard skriven till %s (%d rader, %s)" % (args.out, len(rows), scope))


if __name__ == "__main__":
    main()
