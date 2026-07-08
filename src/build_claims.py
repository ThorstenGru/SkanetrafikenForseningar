"""Generate the "reasonable claim chains" page — a check on whether a set of
delay-compensation claims could plausibly represent one real rider's day,
not just a flat list of every delayed trip network-wide (which is what
compensation.html deliberately shows, per its own illustrative/network-wide
scope — see docs/COMPENSATION_RULES.md item 1).

A real Skånetrafiken claim is for a specific journey the rider actually
made. If someone claimed a trip from Helsingborg to Ystad, and separately a
trip from Simrishamn to Malmö the same day, an investigator would reasonably
ask "how did you get from Ystad to Simrishamn?" — there's no ticketed trip
in between. This page surfaces that check directly: for each day, it groups
eligible trips into the longest sequences where one trip's destination is
the next trip's origin (same place, within CLAIM_CHAIN_CONNECT_RADIUS_M —
see config.py — and in chronological order), and flags any leftover gap
between groups with that exact question.

"Same place" needs stop coordinates, which the realtime `delays` table
doesn't carry (only stop_name/stop_id) — this is why static_index.py's
`stops` table now also stores stop_lat/stop_lon (added 2026-07-06,
alongside this page). Trip endpoints (origin/destination stop identity) come
from static_index.py's `trip_meta` table, which already derives them from
the GTFS static schedule independent of realtime poll luck.

Usage:
    python src/build_claims.py                # full 45-day retention window
    python src/build_claims.py --out other.html
"""

import argparse
import json
import os
import shutil
import sqlite3
from datetime import datetime, timedelta

import config
import db
from build_dashboard import fetch_detail_rows, fmt_time
from build_compensation import compute_compensation

TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "claims_template.html")
CLAIM_FORM_PDF_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "claim_form_template.pdf")


def load_static_lookups():
    """stop_id -> {name, lat, lon}, and trip_id -> (origin_stop_id, destination_stop_id)."""
    conn = sqlite3.connect(config.STATIC_INDEX_PATH)
    try:
        stops = {
            stop_id: {"name": name, "lat": lat, "lon": lon}
            for stop_id, name, lat, lon in conn.execute("SELECT stop_id, stop_name, stop_lat, stop_lon FROM stops")
        }
        trip_endpoints = {
            trip_id: (origin_id, dest_id)
            for trip_id, origin_id, dest_id in conn.execute(
                "SELECT trip_id, origin_stop_id, destination_stop_id FROM trip_meta"
            )
        }
    finally:
        conn.close()
    return stops, trip_endpoints


def load_full_stop_schedule(trip_ids):
    """trip_id -> ordered [(stop_sequence, stop_id, stop_name, arrival_time,
    departure_time), ...] for every station on the trip's static timetable
    -- not just the ones a delay happened to be recorded for. Scoped to the
    trip_ids actually appearing on this page (dozens, not the whole
    network) via config.STOP_TIMES_CACHE_PATH, a separate never-committed
    file (see its own note in config.py/static_index.py) restored via
    actions/cache -- may not exist yet (cold cache), in which case this
    degrades gracefully to {} and merge_full_schedule() leaves the sparse
    live-only stop list untouched."""
    if not trip_ids or not os.path.exists(config.STOP_TIMES_CACHE_PATH):
        return {}
    conn = sqlite3.connect(config.STOP_TIMES_CACHE_PATH)
    try:
        conn.execute("ATTACH DATABASE ? AS main_idx", (config.STATIC_INDEX_PATH,))
        placeholders = ",".join("?" * len(trip_ids))
        rows = conn.execute(
            """SELECT st.trip_id, st.stop_sequence, st.stop_id, s.stop_name, st.arrival_time, st.departure_time
               FROM stop_times st
               LEFT JOIN main_idx.stops s ON s.stop_id = st.stop_id
               WHERE st.trip_id IN (%s)
               ORDER BY st.trip_id, st.stop_sequence""" % placeholders,
            list(trip_ids),
        )
        out = {}
        for trip_id, seq, stop_id, stop_name, arr, dep in rows:
            out.setdefault(trip_id, []).append((seq, stop_id, stop_name, arr, dep))
        return out
    except sqlite3.OperationalError:
        return {}  # e.g. a stale/corrupt cache missing the stop_times table
    finally:
        conn.close()


def _gtfs_time_to_local_dt(time_str, service_date_str):
    """GTFS times are HH:MM:SS and can exceed 24:00:00 for a trip that runs
    past midnight, relative to its service_date (YYYYMMDD). Attaches
    LOCAL_TZ directly to the resulting wall-clock time rather than doing
    proper aware-arithmetic across the addition -- a rare DST-transition
    day could be off by an hour, an accepted approximation for a display
    feature, not a legal timestamp."""
    if not time_str:
        return None
    try:
        h, m, s = (int(x) for x in time_str.split(":"))
    except ValueError:
        return None
    base = datetime.strptime(service_date_str, "%Y%m%d")
    return (base + timedelta(hours=h, minutes=m, seconds=s)).replace(tzinfo=config.LOCAL_TZ)


def merge_full_schedule(rows, full_schedule, stops):
    """Replaces each row's sparse, delay-only `stops` list (only stations
    where scan.py actually wrote a row -- see config.MIN_DELAY_TO_RECORD_SEC)
    with the complete scheduled journey: every station from the static
    timetable, carrying the live-recorded actual time/delay wherever we
    have one, and the scheduled time standing in for "on time, not
    specifically recorded" everywhere else. Matched by stop_sequence, which
    both the static timetable and `delays` key on (not stop_id -- a
    circular/loop route can revisit the same stop_id twice in one trip).

    Also stamps every stop (live and inferred alike) with lat/lon from the
    static `stops` lookup, so the browser can draw the full route line on a
    map -- the live-recorded rows only ever carried a name/time, never
    coordinates, since scan.py has no reason to look those up itself."""
    for r in rows:
        for s in (r.get("stops") or []):
            meta = stops.get(s.get("stopId"), {})
            s["lat"] = meta.get("lat")
            s["lon"] = meta.get("lon")
        schedule = full_schedule.get(r["trip"])
        if not schedule:
            continue  # no static schedule found for this trip_id -- leave the sparse live list as-is
        live_by_seq = {s["seq"]: s for s in (r.get("stops") or [])}
        merged = []
        for seq, stop_id, stop_name, arr_str, dep_str in schedule:
            live = live_by_seq.get(seq)
            if live:
                merged.append(live)
                continue
            sched_dt = _gtfs_time_to_local_dt(dep_str or arr_str, r["date"])
            meta = stops.get(stop_id, {})
            merged.append({
                "seq": seq, "stopId": stop_id, "name": stop_name, "final": False, "relationship": None,
                "delayMin": None, "recorded": False,
                "schedTime": fmt_time(sched_dt), "actTime": None,
                "schedTimeIso": sched_dt.isoformat() if sched_dt else None, "actTimeIso": None,
                "lat": meta.get("lat"), "lon": meta.get("lon"),
            })
        r["stops"] = merged
    return rows


def enrich_with_endpoints(rows, stops, trip_endpoints):
    """Attach origin/destination stop identity (name + lat/lon) to each row,
    plus the best-known timestamp for each end, so the browser can test
    whether two trips physically+chronologically connect without a routing
    API.

    destConfirmed is the important nuance: it's only true when the trip
    actually reached ITS OWN final stop (status DELAYED). A trip that was
    partially cancelled (skipped its final stop) or whose final stop was
    never captured in the feed did NOT confirm the rider ever reached the
    nominal destination — so it can anchor the START of a chain (the rider
    was seen at the origin) but must never anchor the next leg's origin,
    or the chain would silently paper over an unverified journey."""
    out = []
    for r in rows:
        origin_id, dest_id = trip_endpoints.get(r["trip"], (None, None))
        origin_meta = stops.get(origin_id, {})
        dest_meta = stops.get(dest_id, {})

        # Origin is the minimum-stop_sequence entry, not a stopId match --
        # a circular/loop route can revisit the same physical stop_id later
        # in the same trip (see scan.py's own note on this), which a naive
        # stopId match could mistake for the origin.
        stop_list = r.get("stops") or []
        origin_stop_entry = min(stop_list, key=lambda s: s["seq"]) if stop_list else None
        dest_stop_entry = next((s for s in stop_list if s.get("final")), None)

        out.append(dict(r))
        out[-1].update({
            "originStopId": origin_id,
            "originName": origin_meta.get("name"),
            "originLat": origin_meta.get("lat"),
            "originLon": origin_meta.get("lon"),
            "originTimeIso": (origin_stop_entry or {}).get("actTimeIso") or (origin_stop_entry or {}).get("schedTimeIso"),
            "destStopId": dest_id,
            "destLat": dest_meta.get("lat"),
            "destLon": dest_meta.get("lon"),
            "destTimeIso": (dest_stop_entry or {}).get("actTimeIso") or (dest_stop_entry or {}).get("schedTimeIso"),
            "destConfirmed": r.get("status") == "DELAYED",
        })
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=os.path.join(config.REPO_ROOT, "claims.html"))
    args = parser.parse_args()

    end_date = datetime.now(config.LOCAL_TZ).date()
    start_date = end_date - timedelta(days=config.RETENTION_DAYS - 1)
    start_date = max(start_date, config.sommarbiljett_purchased_at().date())

    conn = db.connect()
    cur = conn.cursor()
    try:
        rows = fetch_detail_rows(cur, start_date, end_date, None)
    finally:
        cur.close()
        conn.close()

    stops, trip_endpoints = load_static_lookups()
    comp_rows = compute_compensation(rows)
    full_schedule = load_full_stop_schedule([r["trip"] for r in comp_rows])
    comp_rows = merge_full_schedule(comp_rows, full_schedule, stops)
    claim_rows = enrich_with_endpoints(comp_rows, stops, trip_endpoints)

    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template = f.read()

    payload = json.dumps(
        {
            "rows": claim_rows,
            "windowStart": start_date.strftime("%Y%m%d"),
            "windowEnd": end_date.strftime("%Y%m%d"),
            "constants": {
                "ticketPriceSek": config.SOMMARBILJETT_PRICE_SEK,
                "singleTripPriceSek": round(config.SOMMARBILJETT_SINGLE_TRIP_PRICE_SEK, 3),
                "minDelayMin": config.MIN_DELAY_FOR_COMPENSATION_MIN,
                "connectRadiusM": config.CLAIM_CHAIN_CONNECT_RADIUS_M,
            },
            "supabase": {
                "url": config.SUPABASE_URL,
                "anonKey": config.supabase_anon_key(),
                "writePassphrase": config.claim_tracking_passphrase(),
            },
        },
        ensure_ascii=False, separators=(",", ":"),
    ).replace("</script", "<\\/script")
    html = template.replace("__DATA_JSON__", payload)

    out_dir = os.path.dirname(args.out)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)

    # claims.html fetches this by relative URL to fill it client-side (see
    # docs/COMPENSATION_RULES.md §16) -- needs to sit next to claims.html
    # wherever it's built (scan.yml, backfill.yml, and deploy-pages.yml all
    # build this page into different working copies of pages_site/).
    shutil.copy(CLAIM_FORM_PDF_PATH, os.path.join(out_dir or ".", "claim_form_template.pdf"))

    eligible = sum(1 for r in claim_rows if r["calc"] == "eligible")
    with_coords = sum(1 for r in claim_rows if r["originLat"] is not None and r["destLat"] is not None)
    print("Claim-chain page written to %s (%d eligible trips, %d with both endpoints geolocated, window %s..%s)" % (
        args.out, eligible, with_coords, start_date, end_date))


if __name__ == "__main__":
    main()
