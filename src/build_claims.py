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
import sqlite3
from datetime import date, timedelta

import config
import db
from build_dashboard import fetch_detail_rows
from build_compensation import compute_compensation

TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "claims_template.html")


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

        origin_stop_entry = None
        dest_stop_entry = None
        for s in r.get("stops") or []:
            if origin_id and s.get("stopId") == origin_id:
                origin_stop_entry = s
            if s.get("final"):
                dest_stop_entry = s

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

    end_date = date.today()
    start_date = end_date - timedelta(days=config.RETENTION_DAYS - 1)

    conn = db.connect()
    cur = conn.cursor()
    try:
        rows = fetch_detail_rows(cur, start_date, end_date, None)
    finally:
        cur.close()
        conn.close()

    comp_rows = compute_compensation(rows)
    stops, trip_endpoints = load_static_lookups()
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

    eligible = sum(1 for r in claim_rows if r["calc"] == "eligible")
    with_coords = sum(1 for r in claim_rows if r["originLat"] is not None and r["destLat"] is not None)
    print("Claim-chain page written to %s (%d eligible trips, %d with both endpoints geolocated, window %s..%s)" % (
        args.out, eligible, with_coords, start_date, end_date))


if __name__ == "__main__":
    main()
