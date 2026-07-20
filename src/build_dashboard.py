"""Generate a self-contained HTML dashboard from Postgres. No local SQLite
file involved for delay data — only the small static_index.sqlite (routes/
stops cache) is read locally, and even that isn't needed here since delays
rows already carry denormalized route/stop names written at scan time.

Two different windows, for two different jobs:
  - The "history per day" table is a cheap SQL aggregate (COUNT/AVG/MAX
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
import re
from datetime import date, datetime, timedelta, timezone

import psycopg2
import psycopg2.extras

import config
import db

# Alerts that describe something other than the train running late --
# found 2026-07-20 investigating a real user concern that a seasonal bike-
# capacity notice ("Platsbrist för cyklar" / "Det kan vara platsbrist för
# cyklar i sommar...") was showing up as the delay "reason" for real,
# substantial delays (25-82 min) on routes 804/805/806/817. Root cause: this
# specific alert has NO trip_id at all, only route_id+stop_id, with an
# active_period spanning 2026-06-05..2026-08-15 (2.5 months) -- so
# best_reason()'s trip->stop->route fallback picks it up for almost any
# delay on those routes that lacks a more specific trip-level alert,
# masking whatever the real cause actually was. Confirmed this never
# affects delay_sec/status/calc (best_reason() is display-only, see its own
# docstring) -- only the misleading TEXT shown as "why?". Excluded at the
# lookup-build stage so it can never win the fallback, regardless of how
# specific/unspecific the alternative candidates are.
#
# "hiss" (elevator) added same day, same user, same pattern: checked
# directly -- "Hissen ... är ur funktion" (elevator out of order) is a real,
# common Trafikverket/Skånetrafiken alert (cause TECHNICAL_PROBLEM, e.g.
# "Hissen från södra änden av perrongen på spår 1-2 på Helsingborg C är ur
# funktion"), an accessibility/facility notice with nothing to do with
# train timing, currently the displayed reason for 179 real eligible delays
# (29-67 min). \b word-boundary on both terms to avoid over-matching inside
# an unrelated longer word.
_DELAY_IRRELEVANT_ALERT_RE = re.compile(r"\b(platsbrist|hiss(en)?)\b", re.IGNORECASE)


def _is_delay_irrelevant_alert(desc):
    return bool(desc) and bool(_DELAY_IRRELEVANT_ALERT_RE.search(desc))

TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard_template.html")

DEFAULT_DETAIL_DAYS = 3


def fmt_time(dt):
    if dt is None:
        return None
    return dt.astimezone(config.LOCAL_TZ).strftime("%H:%M")


def build_alert_lookups(cur):
    """trip_id/route_id/stop_id are STATIC identifiers that recur across every
    calendar day a trip/route/stop exists -- an alert_entities row carries no
    date of its own, only a link to whichever alert mentioned it. Without a
    date check, a single alert from one specific day (e.g. a signal fault on
    2026-06-26) would get permanently attached to every future/past
    occurrence of that same recurring trip_id, silently overwriting the
    correct day's own reason (or lack of one). Found 2026-07-08 while
    investigating a real claim rejection -- a delay reason shown for one
    day's trip turned out to belong to a different day entirely. Each alert
    now carries its own active_period so best_reason() can require the
    alert to have actually been active on the specific day being displayed.

    Alerts matching _is_delay_irrelevant_alert() (e.g. the seasonal bike-
    capacity notice, see that function's own note) are dropped here, before
    they ever enter by_trip/by_route/by_stop -- so they can never be
    selected by best_reason()'s fallback, no matter how much more specific
    a real candidate would otherwise have to be to beat them."""
    cur.execute(
        """SELECT e.trip_id, e.route_id, e.stop_id, a.description_text,
                  a.active_period_start, a.active_period_end
           FROM alert_entities e JOIN alerts a ON a.alert_uid = e.alert_uid"""
    )
    by_trip, by_route, by_stop = {}, {}, {}
    for trip_id, route_id, stop_id, desc, start, end in cur.fetchall():
        if _is_delay_irrelevant_alert(desc):
            continue
        entry = (desc, start, end)
        if trip_id:
            by_trip.setdefault(trip_id, []).append(entry)
        if route_id:
            by_route.setdefault(route_id, []).append(entry)
        if stop_id:
            by_stop.setdefault(stop_id, []).append(entry)
    return by_trip, by_route, by_stop


def _alert_active_on(start, end, day_start, day_end):
    # A GTFS-RT alert with no active_period at all means "always active" --
    # matches the spec, and matches how ServiceAlerts.pb entries with an
    # empty active_period list have historically been stored here (both
    # bounds NULL). A one-sided bound (only start or only end) is treated as
    # open on the missing side, not as "never matches".
    if start is not None and start > day_end:
        return False
    if end is not None and end < day_start:
        return False
    return True


def _trip_time_window(stops, day_start):
    """The real window this specific trip occurrence actually ran in,
    padded 2h either side -- anchored to this trip's OWN recorded stop
    times rather than a blanket calendar-day guess. Found by code review
    2026-07-08: the original fixed +36h day_end overlapped the *next*
    calendar day's own window by 12h (day D's window ran to D+1 12:00,
    while D+1's own window started at D+1 00:00), which could reattach a
    same-recurring-trip_id alert from the wrong day right back onto this
    one -- the exact class of bug the date-scoping fix was meant to kill.
    Falls back to a tightened calendar heuristic (day_start to +8h, covers
    a last train arriving in the small hours) only when this trip has no
    recorded per-stop times at all -- e.g. a fully cancelled trip, which
    never gets per-stop rows (see trip_cancellations handling below)."""
    timestamps = []
    for s in stops:
        for key in ("actTimeIso", "schedTimeIso"):
            v = s.get(key)
            if v:
                timestamps.append(datetime.fromisoformat(v))
    if timestamps:
        return min(timestamps) - timedelta(hours=2), max(timestamps) + timedelta(hours=2)
    return day_start, day_start + timedelta(hours=8)


def best_reason(lookups, trip_id, route_id, stop_id, day_start, day_end):
    by_trip, by_route, by_stop = lookups
    for d, key in ((by_trip, trip_id), (by_stop, stop_id), (by_route, route_id)):
        for desc, start, end in d.get(key, ()):
            if _alert_active_on(start, end, day_start, day_end):
                return desc.strip()
    return None


def classify_trip(final_relationship, final_delay_sec, is_cancelled):
    """Status is based on the FINAL STOP specifically (what Skånetrafiken's
    compensation rule actually measures — delay "to your final destination"),
    not on any intermediate stop. See docs/COMPENSATION_RULES.md."""
    if is_cancelled:
        return "CANCELLED_TRIP"
    if final_relationship == "SKIPPED":
        return "PARTIAL_CANCELLATION"  # never reached its own final stop
    if final_relationship is None:
        return "UNKNOWN_FINAL_STATUS"  # final stop never captured in the feed at all
    if final_delay_sec and final_delay_sec > 60:
        return "DELAYED"
    if final_delay_sec and final_delay_sec < -60:
        return "EARLY"
    return "ON_TIME"


def fetch_history_trend(cur):
    """Cheap daily aggregate over the full retention window. Scoped to
    Sommarbiljett-valid trips only (excludes the Ven ferry and any
    Öresund/Denmark-bound service — see docs/COMPENSATION_RULES.md)."""
    cur.execute(
        """SELECT
               trip_start_date,
               COUNT(*) FILTER (WHERE stop_schedule_relationship != 'SKIPPED') AS delay_rows,
               COUNT(*) FILTER (WHERE stop_schedule_relationship = 'SKIPPED') AS skipped_rows,
               AVG(GREATEST(COALESCE(departure_delay_sec, arrival_delay_sec, 0), 0)) FILTER (WHERE COALESCE(departure_delay_sec, arrival_delay_sec, 0) > 60) AS avg_delay_sec,
               MAX(GREATEST(COALESCE(departure_delay_sec, arrival_delay_sec, 0), 0)) AS worst_delay_sec
           FROM delays
           WHERE sommarticket_valid = true
           GROUP BY trip_start_date"""
    )
    delay_agg = {row[0]: row[1:] for row in cur.fetchall()}

    cur.execute("SELECT trip_start_date, COUNT(*) FROM trip_cancellations WHERE sommarticket_valid = true GROUP BY trip_start_date")
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


def fetch_line_anomalies_by_day(cur):
    """Count of lines flagged below their own visibility baseline, per day.
    Will be empty for weeks after launch — needs MIN_BASELINE_DAYS of history
    first (see coverage_check.py). That's correct, not a bug."""
    cur.execute("SELECT trip_start_date, COUNT(*) FROM line_visibility_anomalies GROUP BY trip_start_date")
    return {d.strftime("%Y%m%d"): c for d, c in cur.fetchall()}


def fetch_recent_line_anomalies(cur, limit=50):
    cur.execute(
        """SELECT trip_start_date, route_short_name, scheduled_count, seen_count, actual_rate, baseline_rate, baseline_days
           FROM line_visibility_anomalies ORDER BY trip_start_date DESC, route_short_name LIMIT %s""",
        (limit,),
    )
    return [
        {
            "date": d.strftime("%Y%m%d"), "line": route, "scheduled": sched, "seen": seen_n,
            "actualRate": round(actual * 100, 1), "baselineRate": round(baseline * 100, 1), "baselineDays": days,
        }
        for d, route, sched, seen_n, actual, baseline, days in cur.fetchall()
    ]


def fetch_detail_rows(cur, start_date, end_date, single_date):
    """One row per (trip_id, trip_start_date) — not per stop. Two delay
    metrics are tracked deliberately, per the user's decision (2026-07-05):
      - finalDelayMin: the delay AT THE FINAL STOP specifically. This is
        what Skånetrafiken's compensation rule literally measures ("delay
        to your final destination") — see docs/COMPENSATION_RULES.md.
      - maxDelayMin: the largest delay observed anywhere along the trip,
        across all its stops and all polls. Can be higher than the final
        delay if time was made up before arrival.
    Scoped to sommarticket_valid=true only (excludes the Ven ferry and any
    Öresund/Denmark-bound service, which Sommarbiljetten doesn't cover)."""
    lookups = build_alert_lookups(cur)

    if single_date:
        where, params = "trip_start_date = %s", (single_date,)
    else:
        where, params = "trip_start_date BETWEEN %s AND %s", (start_date, end_date)

    trips = {}

    cur.execute(
        """SELECT trip_id, trip_start_date, route_id, route_short_name, vehicle_type, trip_number,
                  distance_km, destination_stop_name, stop_id, stop_name, stop_sequence, is_final_stop,
                  stop_schedule_relationship, arrival_delay_sec, departure_delay_sec, max_abs_delay_sec,
                  arrival_time, departure_time, scheduled_arrival, scheduled_departure,
                  first_seen_at, last_seen_at, poll_count
           FROM delays WHERE sommarticket_valid = true AND %s""" % where,
        params,
    )
    for (trip_id, d, route_id, route_short_name, vehicle_type, trip_number, distance_km, dest,
         stop_id, stop_name, seq, is_final, stop_rel, arr_delay, dep_delay, max_abs_delay,
         arr_time, dep_time, sched_arr, sched_dep,
         first_seen, last_seen, polls) in cur.fetchall():
        key = (trip_id, d)
        t = trips.get(key)
        if t is None:
            t = {
                "trip": trip_id, "date": d.strftime("%Y%m%d"), "line": route_short_name,
                "vehicleType": vehicle_type or "UNKNOWN", "tripNumber": trip_number, "dest": dest,
                "distanceKm": distance_km, "route_id": route_id, "stop_ids": [], "stops": [],
                "final_relationship": None, "final_delay_sec": None, "max_delay_sec": None,
                "final_stop_unconfirmed": False,
                "is_cancelled": False, "firstSeen": first_seen, "lastSeen": last_seen, "polls": 0,
            }
            trips[key] = t
        t["stop_ids"].append(stop_id)
        stop_delay_sec = dep_delay if dep_delay not in (None, 0) else arr_delay
        sched_dt = sched_dep or sched_arr
        act_dt = dep_time or arr_time
        t["stops"].append({
            "seq": seq, "stopId": stop_id, "name": stop_name, "final": bool(is_final), "relationship": stop_rel,
            "delayMin": round(stop_delay_sec / 60, 1) if stop_delay_sec is not None else None,
            "schedTime": fmt_time(sched_dt), "actTime": fmt_time(act_dt),
            "schedTimeIso": sched_dt.isoformat() if sched_dt else None,
            "actTimeIso": act_dt.isoformat() if act_dt else None,
        })
        t["polls"] += polls
        t["firstSeen"] = min(t["firstSeen"], first_seen)
        t["lastSeen"] = max(t["lastSeen"], last_seen)
        t["max_delay_sec"] = max(t["max_delay_sec"] or 0, max_abs_delay or 0)
        if is_final:
            # ARRIVAL delay, not departure -- Skånetrafiken's own rule is
            # literally "delay to your final destination" (arrival), and a
            # train's own "departure" from its terminus is usually just the
            # empty stock continuing on, not a passenger-relevant event.
            # Found by code review 2026-07-09 on a real journey (Öresundståg
            # 20154) where this alone overstated the claim by ~11 minutes
            # (23.6 vs the already-recorded 12.9 arrival figure) --
            # previously used the same dep-preferred logic as every other
            # stop, which is the right call for an INTERMEDIATE stop (when
            # did the delay become visible) but the wrong one for the final
            # stop specifically.
            final_relevant_delay_sec = arr_delay if arr_delay not in (None, 0) else dep_delay
            final_relevant_actual_time = arr_time if arr_delay not in (None, 0) else dep_time
            t["final_relationship"] = stop_rel
            t["final_delay_sec"] = final_relevant_delay_sec
            # If the last time we ever polled this trip was BEFORE the
            # "actual" timestamp stored for its final stop, that timestamp
            # is mathematically a live GTFS-RT PREDICTION captured while the
            # trip was still in progress, never a confirmed post-arrival
            # observation -- the same train (20154) above was polled exactly
            # once, ~50 minutes before its own recorded "actual" arrival
            # time, while the delay was still growing early in the journey.
            # Skånetrafiken's own app later confirmed the train recovered to
            # +3 min; ours never got a later poll to find that out. Flagged
            # here rather than silently trusted -- see delayApprox's own
            # precedent for "don't recommend a claim on an unconfirmed
            # number."
            t["final_stop_unconfirmed"] = bool(
                final_relevant_actual_time and last_seen < final_relevant_actual_time
            )

    cur.execute(
        """SELECT trip_id, trip_start_date, route_id, route_short_name, vehicle_type, trip_number,
                  distance_km, destination_stop_name, first_seen_at, last_seen_at, poll_count
           FROM trip_cancellations WHERE sommarticket_valid = true AND %s""" % where,
        params,
    )
    for (trip_id, d, route_id, route_short_name, vehicle_type, trip_number, distance_km, dest,
         first_seen, last_seen, polls) in cur.fetchall():
        key = (trip_id, d)
        trips[key] = {
            "trip": trip_id, "date": d.strftime("%Y%m%d"), "line": route_short_name,
            "vehicleType": vehicle_type or "UNKNOWN", "tripNumber": trip_number, "dest": dest,
            "distanceKm": distance_km, "route_id": route_id, "stop_ids": [], "stops": [],
            "final_relationship": None, "final_delay_sec": None, "max_delay_sec": None,
            "final_stop_unconfirmed": False,
            "is_cancelled": True, "firstSeen": first_seen, "lastSeen": last_seen, "polls": polls,
        }

    out = []
    for (_trip_id_key, trip_date), t in trips.items():
        calendar_day_start = datetime.combine(trip_date, datetime.min.time(), tzinfo=config.LOCAL_TZ)
        day_start, day_end = _trip_time_window(t["stops"], calendar_day_start)
        reason = best_reason(lookups, t["trip"], t["route_id"], None, day_start, day_end)
        if reason is None:
            for sid in t["stop_ids"]:
                reason = best_reason(lookups, t["trip"], t["route_id"], sid, day_start, day_end)
                if reason:
                    break
        out.append({
            "trip": t["trip"], "date": t["date"], "line": t["line"], "vehicleType": t["vehicleType"],
            "tripNumber": t["tripNumber"], "dest": t["dest"], "distanceKm": t["distanceKm"],
            "status": classify_trip(t["final_relationship"], t["final_delay_sec"], t["is_cancelled"]),
            "finalDelayMin": round(t["final_delay_sec"] / 60, 1) if t["final_delay_sec"] is not None else None,
            "maxDelayMin": round(t["max_delay_sec"] / 60, 1) if t["max_delay_sec"] is not None else None,
            "finalStopUnconfirmed": t["final_stop_unconfirmed"],
            "reason": reason,
            "stops": sorted(t["stops"], key=lambda s: s["seq"] if s["seq"] is not None else 0),
            "firstSeen": t["firstSeen"].isoformat(), "lastSeen": t["lastSeen"].isoformat(), "polls": t["polls"],
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
        end_date = datetime.now(config.LOCAL_TZ).date()
        start_date = end_date - timedelta(days=args.days - 1)

    conn = db.connect()
    cur = conn.cursor()
    try:
        trend = fetch_history_trend(cur)
        anomalies_by_day = fetch_line_anomalies_by_day(cur)
        for row in trend:
            row["lineAnomalies"] = anomalies_by_day.get(row["date"], 0)
        detail_rows = fetch_detail_rows(cur, start_date, end_date, single_date)
        line_anomalies = fetch_recent_line_anomalies(cur)
    finally:
        cur.close()
        conn.close()

    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template = f.read()

    payload = json.dumps(
        {"trend": trend, "rows": detail_rows, "lineAnomalies": line_anomalies},
        ensure_ascii=False, separators=(",", ":"),
    ).replace("</script", "<\\/script")
    html = template.replace("__DATA_JSON__", payload)

    out_dir = os.path.dirname(args.out)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)

    scope = single_date or ("%s .. %s" % (start_date, end_date))
    print("Dashboard written to %s (%d detail rows for %s, %d days in history trend)" % (
        args.out, len(detail_rows), scope, len(trend)))


if __name__ == "__main__":
    main()
