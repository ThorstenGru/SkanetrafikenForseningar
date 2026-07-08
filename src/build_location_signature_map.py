"""One-off (re-runnable) import of Trafikverket's own LocationSignature ->
station crosswalk into `location_signature_map`, resolving open question #2
from docs/TRAFIKVERKET_INTEGRATION.md.

Trafikverket publishes a `TrainStation` object type carrying exactly this
mapping (signature, official name, WGS84 coordinates) for the whole
national network -- confirmed 2026-07-08 to be only ~700 stations, small
enough to fetch in one call and match locally rather than hand-typing
Skåne's ~100+ stations one by one.

Matching is nearest-neighbour by coordinates against this project's own
static `stops` table (data/static_index.sqlite), not by name -- station
names differ enough between the two systems (e.g. "Kristianstad C" vs
"Kristianstad central") that a name match would miss real matches or
false-match unrelated stations that happen to share a word.

Usage:
    python src/build_location_signature_map.py                # matches + upserts
    python src/build_location_signature_map.py --dry-run       # matches only, prints, no DB write
"""

import argparse
import math
from datetime import datetime, timezone

import psycopg2.extras
import requests

import config
import db

TRAFIKVERKET_QUERY = """<REQUEST>
  <LOGIN authenticationkey="%s" />
  <QUERY objecttype="TrainStation" schemaversion="1.4">
    <FILTER><EQ name="Advertised" value="true" /></FILTER>
  </QUERY>
</REQUEST>"""

# Real-world SWEREF99TM/WGS84 station coordinates from two independent
# systems for the same physical place normally agree within a few tens of
# metres. 500 m leaves headroom for a station's official coordinate point
# sitting at a different platform/entrance than ours, without being loose
# enough to false-match a genuinely different nearby stop.
MATCH_RADIUS_M = 500


def _haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def fetch_train_stations():
    query = TRAFIKVERKET_QUERY % config.trafikverket_key()
    resp = requests.post(
        config.TRAFIKVERKET_API_URL,
        data=query,
        headers={"Content-Type": "text/xml", "Accept": "application/json"},
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError("Trafikverket TrainStation failed: HTTP %d: %s" % (resp.status_code, resp.text[:500]))
    payload = resp.json()
    result = payload["RESPONSE"]["RESULT"][0]
    if "ERROR" in result:
        raise RuntimeError("Trafikverket TrainStation query error: %s" % result["ERROR"])
    return result.get("TrainStation", [])


def _station_latlon(station):
    """WGS84 geometry comes back as a WKT-ish string: 'POINT (lon lat)'."""
    wgs84 = (station.get("Geometry") or {}).get("WGS84")
    if not wgs84:
        return None, None
    inner = wgs84.strip().removeprefix("POINT (").removesuffix(")")
    lon_str, lat_str = inner.split(" ")
    return float(lat_str), float(lon_str)


def load_our_stops():
    import sqlite3
    conn = sqlite3.connect(config.STATIC_INDEX_PATH)
    try:
        return conn.execute("SELECT stop_id, stop_name, stop_lat, stop_lon FROM stops").fetchall()
    finally:
        conn.close()


def match_stations(stations, our_stops):
    """Returns (matches, unmatched_signatures, unmatched_our_stop_count).
    matches: list of (location_signature, stop_id, stop_name)."""
    located_stops = [(sid, name, lat, lon) for sid, name, lat, lon in our_stops if lat is not None and lon is not None]

    matches = []
    unmatched_signatures = []
    matched_stop_ids = set()
    for station in stations:
        lat, lon = _station_latlon(station)
        if lat is None:
            unmatched_signatures.append(station["LocationSignature"])
            continue
        best = None
        best_dist = None
        for sid, name, slat, slon in located_stops:
            dist = _haversine_m(lat, lon, slat, slon)
            if dist <= MATCH_RADIUS_M and (best_dist is None or dist < best_dist):
                best, best_dist = (sid, name), dist
        if best:
            matches.append((station["LocationSignature"], best[0], best[1]))
            matched_stop_ids.add(best[0])
        else:
            unmatched_signatures.append(station["LocationSignature"])

    unmatched_our_stops = len(located_stops) - len(matched_stop_ids)
    return matches, unmatched_signatures, unmatched_our_stops


def upsert_matches(cur, matches, now):
    if not matches:
        return
    values = [(sig, stop_id, name, now) for sig, stop_id, name in matches]
    psycopg2.extras.execute_values(
        cur,
        """INSERT INTO location_signature_map (location_signature, stop_id, stop_name, verified_at)
           VALUES %s
           ON CONFLICT (location_signature) DO UPDATE SET
               stop_id = EXCLUDED.stop_id, stop_name = EXCLUDED.stop_name, verified_at = EXCLUDED.verified_at""",
        values,
    )


def _sql_literal(value):
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def write_sql(matches, path, now_iso):
    """Alternative to a direct psycopg2 write, for environments (like this
    one) with Supabase CLI/Management-API access but no direct Postgres
    password -- run the emitted file with
    `supabase db query --linked -f <path>`, same as any other migration."""
    with open(path, "w", encoding="utf-8") as f:
        f.write("-- Generated by build_location_signature_map.py -- not a migration, re-run anytime to refresh.\n")
        for sig, stop_id, name in matches:
            f.write(
                "INSERT INTO location_signature_map (location_signature, stop_id, stop_name, verified_at) "
                "VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (location_signature) DO UPDATE SET stop_id = EXCLUDED.stop_id, "
                "stop_name = EXCLUDED.stop_name, verified_at = EXCLUDED.verified_at;\n"
                % (_sql_literal(sig), _sql_literal(stop_id), _sql_literal(name), _sql_literal(now_iso))
            )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Match and print only, no DB write.")
    parser.add_argument("--sql-out", default=None, help="Write upserts to this SQL file instead of connecting via psycopg2 (for environments without a direct DB password -- apply with `supabase db query --linked -f <file>`).")
    args = parser.parse_args()

    stations = fetch_train_stations()
    our_stops = load_our_stops()
    matches, unmatched_signatures, unmatched_our_stops = match_stations(stations, our_stops)

    print("Trafikverket stations fetched: %d" % len(stations))
    print("Matched to our own GTFS stops: %d (within %d m)" % (len(matches), MATCH_RADIUS_M))
    print("Our stops with no Trafikverket match (buses/trams/ferries, expected): %d" % unmatched_our_stops)
    print("Trafikverket stations with no match on our side (out-of-network or coordinate mismatch): %d" % len(unmatched_signatures))

    if args.dry_run:
        for sig, stop_id, name in matches[:20]:
            print("  %s -> %s (%s)" % (sig, stop_id, name))
        return

    now = datetime.now(timezone.utc)
    if args.sql_out:
        write_sql(matches, args.sql_out, now.isoformat())
        print("SQL written to %s (%d upserts)" % (args.sql_out, len(matches)))
        return

    conn = db.connect()
    try:
        cur = conn.cursor()
        upsert_matches(cur, matches, now)
        conn.commit()
        cur.close()
    finally:
        conn.close()
    print("location_signature_map updated: %d rows" % len(matches))


if __name__ == "__main__":
    main()
