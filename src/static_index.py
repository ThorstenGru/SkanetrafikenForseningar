"""Download and cache Trafiklab's static GTFS Regional data, then distill it
into a small SQLite index (routes, stops, per-trip destination, and calendar
service-day rules) that we keep committed to the repo. The raw GTFS zip
(~300 MB uncompressed) is downloaded to a scratch directory and deleted
again — it is never committed.

The calendar/calendar_dates tables exist so coverage_check.py can answer
"which trip_ids were actually scheduled to run on date X" without needing
the raw stop_times.txt.
"""

import csv
import io
import os
import shutil
import sqlite3
import sys
import time
import zipfile

import requests

import config


def _is_index_fresh():
    if not os.path.exists(config.STATIC_INDEX_PATH):
        return False
    conn = sqlite3.connect(config.STATIC_INDEX_PATH)
    try:
        row = conn.execute("SELECT built_at FROM meta LIMIT 1").fetchone()
    except sqlite3.OperationalError:
        return False
    finally:
        conn.close()
    if not row:
        return False
    age_days = (time.time() - row[0]) / 86400
    return age_days < config.STATIC_CACHE_MAX_AGE_DAYS


def _download_and_extract_raw():
    os.makedirs(config.RAW_STATIC_CACHE_DIR, exist_ok=True)
    url = config.STATIC_URL_TMPL.format(op=config.OPERATOR, key=config.static_key())
    print("Fetching static GTFS data for '%s' (uses 1 static request from the monthly quota)..." % config.OPERATOR)
    resp = requests.get(url, timeout=120)
    if resp.status_code != 200:
        raise RuntimeError("Static GTFS fetch failed: HTTP %d: %s" % (resp.status_code, resp.text[:300]))
    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        z.extractall(config.RAW_STATIC_CACHE_DIR)
    print("Static GTFS extracted to %s" % config.RAW_STATIC_CACHE_DIR)


def _build_trip_destinations(raw_dir):
    """Single streaming pass over stop_times.txt: for each trip_id, find the
    stop with the highest stop_sequence (the trip's final destination)."""
    stop_times_path = os.path.join(raw_dir, "stop_times.txt")
    last_stop = {}  # trip_id -> (max_seq, stop_id)
    with open(stop_times_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            trip_id = row["trip_id"]
            seq = int(row["stop_sequence"])
            current = last_stop.get(trip_id)
            if current is None or seq > current[0]:
                last_stop[trip_id] = (seq, row["stop_id"])
    return last_stop


def rebuild_index():
    """Download static GTFS fresh, distill it into STATIC_INDEX_PATH, and
    delete the raw download. Returns True if it actually refreshed."""
    if os.path.exists(config.RAW_STATIC_CACHE_DIR):
        shutil.rmtree(config.RAW_STATIC_CACHE_DIR)

    try:
        _download_and_extract_raw()

        routes = {}
        with open(os.path.join(config.RAW_STATIC_CACHE_DIR, "routes.txt"), "r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                routes[row["route_id"]] = (
                    row.get("route_short_name") or row.get("route_long_name") or row["route_id"],
                    row.get("route_long_name", ""),
                    int(row["route_type"]) if row.get("route_type") not in (None, "") else None,
                )

        stops = {}
        with open(os.path.join(config.RAW_STATIC_CACHE_DIR, "stops.txt"), "r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                stops[row["stop_id"]] = row.get("stop_name", "")

        last_stop = _build_trip_destinations(config.RAW_STATIC_CACHE_DIR)

        trips_path = os.path.join(config.RAW_STATIC_CACHE_DIR, "trips.txt")
        os.makedirs(config.DATA_DIR, exist_ok=True)
        if os.path.exists(config.STATIC_INDEX_PATH):
            os.remove(config.STATIC_INDEX_PATH)
        conn = sqlite3.connect(config.STATIC_INDEX_PATH)
        conn.execute("CREATE TABLE meta (built_at REAL)")
        conn.execute("CREATE TABLE routes (route_id TEXT PRIMARY KEY, short_name TEXT, long_name TEXT, route_type INTEGER)")
        conn.execute("CREATE TABLE stops (stop_id TEXT PRIMARY KEY, stop_name TEXT)")
        conn.execute(
            "CREATE TABLE trip_meta ("
            "trip_id TEXT PRIMARY KEY, route_id TEXT, direction_id INTEGER, service_id TEXT, "
            "destination_stop_id TEXT, destination_stop_name TEXT, final_stop_sequence INTEGER)"
        )
        conn.execute(
            "CREATE TABLE calendar ("
            "service_id TEXT PRIMARY KEY, monday INTEGER, tuesday INTEGER, wednesday INTEGER, "
            "thursday INTEGER, friday INTEGER, saturday INTEGER, sunday INTEGER, "
            "start_date TEXT, end_date TEXT)"
        )
        conn.execute("CREATE TABLE calendar_dates (service_id TEXT, date TEXT, exception_type INTEGER)")
        conn.execute("CREATE INDEX idx_calendar_dates_svc ON calendar_dates (service_id, date)")

        conn.executemany("INSERT INTO routes VALUES (?, ?, ?, ?)", [(k, v[0], v[1], v[2]) for k, v in routes.items()])
        conn.executemany("INSERT INTO stops VALUES (?, ?)", list(stops.items()))

        with open(trips_path, "r", encoding="utf-8-sig", newline="") as f:
            trip_rows = []
            for row in csv.DictReader(f):
                trip_id = row["trip_id"]
                dest_seq, dest_stop_id = last_stop.get(trip_id, (None, None))
                trip_rows.append((
                    trip_id,
                    row.get("route_id", ""),
                    int(row["direction_id"]) if row.get("direction_id") not in (None, "") else None,
                    row.get("service_id", ""),
                    dest_stop_id,
                    stops.get(dest_stop_id, "") if dest_stop_id else "",
                    dest_seq,
                ))
            conn.executemany("INSERT INTO trip_meta VALUES (?, ?, ?, ?, ?, ?, ?)", trip_rows)

        calendar_path = os.path.join(config.RAW_STATIC_CACHE_DIR, "calendar.txt")
        calendar_rows = []
        if os.path.exists(calendar_path):
            with open(calendar_path, "r", encoding="utf-8-sig", newline="") as f:
                for row in csv.DictReader(f):
                    calendar_rows.append((
                        row["service_id"], int(row["monday"]), int(row["tuesday"]), int(row["wednesday"]),
                        int(row["thursday"]), int(row["friday"]), int(row["saturday"]), int(row["sunday"]),
                        row["start_date"], row["end_date"],
                    ))
            conn.executemany("INSERT INTO calendar VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", calendar_rows)

        calendar_dates_path = os.path.join(config.RAW_STATIC_CACHE_DIR, "calendar_dates.txt")
        calendar_dates_rows = []
        if os.path.exists(calendar_dates_path):
            with open(calendar_dates_path, "r", encoding="utf-8-sig", newline="") as f:
                for row in csv.DictReader(f):
                    calendar_dates_rows.append((row["service_id"], row["date"], int(row["exception_type"])))
            conn.executemany("INSERT INTO calendar_dates VALUES (?, ?, ?)", calendar_dates_rows)

        conn.execute("INSERT INTO meta VALUES (?)", (time.time(),))
        conn.commit()
        conn.close()
        print("Static index built: %d routes, %d stops, %d trips, %d calendar rows, %d calendar_dates rows." % (
            len(routes), len(stops), len(trip_rows), len(calendar_rows), len(calendar_dates_rows)))
        return True
    finally:
        if os.path.exists(config.RAW_STATIC_CACHE_DIR):
            shutil.rmtree(config.RAW_STATIC_CACHE_DIR)


def ensure_index():
    """Rebuild the static index only if missing or older than the cache window."""
    if _is_index_fresh():
        print("Static index is fresh (< %d days), using cache." % config.STATIC_CACHE_MAX_AGE_DAYS)
        return False
    return rebuild_index()


if __name__ == "__main__":
    sys.exit(0 if ensure_index() is not None else 1)
