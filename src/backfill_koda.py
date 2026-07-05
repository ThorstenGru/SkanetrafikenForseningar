"""One-off backfill: pull historical TripUpdates + ServiceAlerts snapshots
from Trafiklab's KoDa archive (https://www.trafiklab.se/api/our-apis/koda/)
for a range of past days, and feed them through the same processing
pipeline as a live scan — so historical rows are written exactly like a
live scan would have written them, just after the fact.

KoDa stores a snapshot of each realtime feed roughly every 15-60 seconds,
going back years, packaged as one 7z archive per (operator, feed, date).
Archives are built on demand: the first request for a given day can return
HTTP 202 ("being prepared") for anywhere from under a minute up to ~60
minutes before the real archive is ready.

For each requested day we download the full-day archive for both feeds,
then pick the single stored snapshot closest to each of our usual polling
marks (every N hours, Europe/Stockholm clock, matching scan.py's live
cadence) and run it through scan.process_trip_updates()/process_alerts()
using that snapshot's own embedded feed.header.timestamp as "now" — not
wall-clock time — so first_seen/last_seen/scan_runs carry true historical
timestamps.

This only approximates a real 2-hourly scan: any delay that appeared and
fully resolved between two sampled marks is invisible, exactly like it
would be invisible to the live scanner too (same cadence, same blind
spot). It also reuses TODAY's static index (routes/trip metadata) for the
whole backfilled range — acceptable because Skånetrafiken's timetable
changes only a few times a year and 32 days is short, but if a schedule
change fell inside the backfilled range, some trip_id lookups may miss.

Usage:
    python src/backfill_koda.py --days 32                # last 32 full days
    python src/backfill_koda.py --days 32 --interval-hours 2
    python src/backfill_koda.py --start 2026-06-01 --end 2026-07-04
"""

import argparse
import io
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone

import py7zr
import requests
from google.transit import gtfs_realtime_pb2

import config
import db
import scan
import static_index

KODA_BASE = "https://api.koda.trafiklab.se/KoDa/api/v2"
POLL_INTERVAL_SEC = 30
MAX_POLL_MINUTES = 60


def _koda_url(feed, day):
    return "%s/gtfs-rt/%s/%s?date=%s&key=%s" % (
        KODA_BASE, config.OPERATOR, feed, day.isoformat(), config.koda_key()
    )


def fetch_day_snapshots(feed, day):
    """Downloads and extracts one day's worth of a KoDa feed. Returns a list
    of (timestamp_utc, raw_protobuf_bytes) sorted by timestamp, one per
    snapshot actually stored that day."""
    url = _koda_url(feed, day)
    deadline = time.time() + MAX_POLL_MINUTES * 60
    while True:
        resp = requests.get(url, timeout=120)
        if resp.status_code == 200 and resp.headers.get("Content-Type", "").startswith("application/x-7z"):
            break
        if resp.status_code in (200, 202):
            # 200 with a JSON body also means "still building" in practice.
            if time.time() > deadline:
                raise RuntimeError(
                    "KoDa archive for %s %s never became ready after %d min" % (feed, day, MAX_POLL_MINUTES)
                )
            time.sleep(POLL_INTERVAL_SEC)
            continue
        if resp.status_code == 404:
            print("  %s %s: no archive available (404) - skipping." % (feed, day))
            return []
        raise RuntimeError("KoDa request failed: HTTP %d: %s" % (resp.status_code, resp.text[:300]))

    snapshots = []
    with tempfile.TemporaryDirectory() as tmpdir:
        with py7zr.SevenZipFile(io.BytesIO(resp.content), mode="r") as archive:
            archive.extractall(path=tmpdir)
        for root, _dirs, files in os.walk(tmpdir):
            for fname in files:
                with open(os.path.join(root, fname), "rb") as f:
                    raw = f.read()
                if not raw:
                    continue
                feed_msg = gtfs_realtime_pb2.FeedMessage()
                try:
                    feed_msg.ParseFromString(raw)
                except Exception:
                    continue
                ts = feed_msg.header.timestamp
                if not ts:
                    continue
                snapshots.append((datetime.fromtimestamp(ts, tz=timezone.utc), raw))
    snapshots.sort(key=lambda x: x[0])
    return snapshots


def _pick_nearest(snapshots, target_utc, tolerance_seconds):
    best, best_diff = None, None
    for ts, raw in snapshots:
        diff = abs((ts - target_utc).total_seconds())
        if best_diff is None or diff < best_diff:
            best, best_diff = (ts, raw), diff
    if best is not None and best_diff <= tolerance_seconds:
        return best
    return None


def _target_marks_utc(day, interval_hours):
    """Local Europe/Stockholm poll marks for one calendar day, as UTC datetimes."""
    marks = []
    hour = 0
    while hour < 24:
        local = datetime(day.year, day.month, day.day, hour, 0, tzinfo=config.LOCAL_TZ)
        marks.append(local.astimezone(timezone.utc))
        hour += interval_hours
    return marks


def backfill_day(day, interval_hours, trip_meta, stops, cur):
    print("Fetching KoDa archives for %s..." % day)
    tu_snapshots = fetch_day_snapshots("TripUpdates", day)
    alert_snapshots = fetch_day_snapshots("ServiceAlerts", day)
    print("  %d TripUpdates snapshot(s), %d ServiceAlerts snapshot(s) stored for %s" % (
        len(tu_snapshots), len(alert_snapshots), day))
    if not tu_snapshots and not alert_snapshots:
        return 0

    tolerance = max(900, interval_hours * 1800)  # up to half an interval, min 15 min
    marks_processed = 0
    for mark in _target_marks_utc(day, interval_hours):
        tu_pick = _pick_nearest(tu_snapshots, mark, tolerance)
        alert_pick = _pick_nearest(alert_snapshots, mark, tolerance)
        if not tu_pick and not alert_pick:
            continue

        now = tu_pick[0] if tu_pick else alert_pick[0]
        error = None
        delays_seen = delays_new = cancellations_seen = alerts_seen = alerts_new = 0
        try:
            if tu_pick:
                feed_msg = gtfs_realtime_pb2.FeedMessage()
                feed_msg.ParseFromString(tu_pick[1])
                delays_seen, delays_new, cancellations_seen = scan.process_trip_updates(
                    feed_msg, trip_meta, stops, cur, now
                )
            if alert_pick:
                feed_msg = gtfs_realtime_pb2.FeedMessage()
                feed_msg.ParseFromString(alert_pick[1])
                alerts_seen, alerts_new = scan.process_alerts(feed_msg, cur, now)
        except Exception as exc:
            error = str(exc)
            print("  ERROR processing snapshot at %s: %s" % (now, error), file=sys.stderr)

        db.record_scan_run(cur, {
            "run_at": now, "delays_seen": delays_seen, "delays_new": delays_new,
            "cancellations_seen": cancellations_seen, "alerts_seen": alerts_seen, "alerts_new": alerts_new,
            "static_refreshed": False, "error": error,
        })
        marks_processed += 1
    return marks_processed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=32, help="How many full days back to backfill (ending yesterday).")
    parser.add_argument("--interval-hours", type=int, default=2, help="Sampling cadence, matching the live scanner.")
    parser.add_argument("--start", default=None, help="YYYY-MM-DD, overrides --days")
    parser.add_argument("--end", default=None, help="YYYY-MM-DD, defaults to yesterday")
    args = parser.parse_args()

    today = datetime.now(config.LOCAL_TZ).date()
    if args.start:
        start = datetime.strptime(args.start, "%Y-%m-%d").date()
        end = datetime.strptime(args.end, "%Y-%m-%d").date() if args.end else today - timedelta(days=1)
    else:
        end = today - timedelta(days=1)
        start = end - timedelta(days=args.days - 1)

    print("Backfilling %s..%s (every %dh, Europe/Stockholm)" % (start, end, args.interval_hours))

    static_index.ensure_index()
    static_conn = sqlite3.connect(config.STATIC_INDEX_PATH)
    trip_meta, stops = scan.load_trip_meta(static_conn)
    static_conn.close()

    conn = db.connect()
    cur = conn.cursor()
    total_marks = 0
    days_done = 0
    try:
        day = start
        while day <= end:
            n = backfill_day(day, args.interval_hours, trip_meta, stops, cur)
            conn.commit()
            total_marks += n
            days_done += 1
            print("  -> %d mark(s) recorded for %s (committed)" % (n, day))
            day += timedelta(days=1)
    finally:
        cur.close()
        conn.close()

    print("Backfill complete: %d day(s), %d mark(s) total." % (days_done, total_marks))

    print("Recomputing line-visibility baselines for each backfilled day...")
    coverage_script = __file__.replace("backfill_koda.py", "coverage_check.py")
    day = start
    while day <= end:
        subprocess.run(
            [sys.executable, coverage_script, "--date", day.strftime("%Y%m%d")],
            check=True,
        )
        day += timedelta(days=1)


if __name__ == "__main__":
    main()
