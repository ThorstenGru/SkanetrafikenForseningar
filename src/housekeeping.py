"""Daily housekeeping: delete every row that falls OUTSIDE the fixed season
window (config.WINDOW_START .. config.WINDOW_END). Postgres autovacuum
reclaims the space on its own — no manual VACUUM needed (unlike SQLite).

Two-sided on purpose, and fixed rather than rolling. The previous version
deleted anything older than a rolling RETENTION_DAYS=45 cutoff, which meant
the "keep" range crept forward one day per day: from 2026-08-10 onward it
would have started deleting 2026-06-25, then 06-26, then 06-27 — the
earliest days of the very season this project exists to document — and
recorded each deletion as a routine success. A window pinned to two literal
dates cannot walk into its own data no matter how long the project runs.

The upper bound matters too: "nothing after 20 August" is as much a
requirement as "nothing before 25 June" (user, 2026-08-06). Scanning stops
at WINDOW_END so little should ever land past it, but a late poll crossing
local midnight, a manual backfill run with the wrong argument, or a replayed
workflow all can — and this is the one place that reliably catches it.

Operational log tables (scan_runs, housekeeping_runs) get the LOWER bound
only. They describe the pipeline, not the season, and a two-sided window
applied to them would have this script delete its own just-written audit row
on every post-season run.

Usage:
    python src/housekeeping.py
"""

from datetime import datetime, time, timedelta, timezone

import config
import db


def main():
    now = datetime.now(timezone.utc)
    start_date = config.WINDOW_START
    end_date = config.WINDOW_END

    # Half-open [start, end+1) in local time — `delays.trip_start_date` is a
    # DATE, but alerts/scan_runs are TIMESTAMPTZ and must be bounded by the
    # Stockholm midnights either side of the window, not UTC ones.
    start_ts = datetime.combine(start_date, time.min, tzinfo=config.LOCAL_TZ)
    end_ts_exclusive = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=config.LOCAL_TZ)

    conn = db.connect()
    cur = conn.cursor()
    error = None
    counts = {}
    try:
        for table, key, count_key in (
            ("delays", "trip_start_date", "delays_deleted"),
            ("trip_cancellations", "trip_start_date", "cancellations_deleted"),
            ("seen_trips", "trip_start_date", "seen_trips_deleted"),
            ("line_daily_visibility", "trip_start_date", "line_visibility_deleted"),
            ("line_visibility_anomalies", "trip_start_date", "line_anomalies_deleted"),
            # Added 2026-07-08 alongside the Trafikverket integration --
            # without a retention path of its own this table grew forever
            # (see docs/TRAFIKVERKET_INTEGRATION.md). Keyed on Trafikverket's
            # own traffic_date, not trip_start_date.
            ("train_announcements", "traffic_date", "train_announcements_deleted"),
        ):
            cur.execute(
                "DELETE FROM %s WHERE %s < %%s OR %s > %%s" % (table, key, key),
                (start_date, end_date),
            )
            counts[count_key] = cur.rowcount

        # Alerts have no trip date of their own — key off when we last saw
        # them active in the feed.
        cur.execute(
            "DELETE FROM alerts WHERE last_seen_at < %s OR last_seen_at >= %s",
            (start_ts, end_ts_exclusive),
        )
        counts["alerts_deleted"] = cur.rowcount

        # Lower bound only — see module docstring.
        cur.execute("DELETE FROM scan_runs WHERE run_at < %s", (start_ts,))
        counts["scan_runs_deleted"] = cur.rowcount

        conn.commit()
        print("Housekeeping done (window %s .. %s): %s" % (start_date, end_date, counts))
    except Exception as exc:
        conn.rollback()
        error = str(exc)
        print("ERROR during housekeeping: %s" % error)
    finally:
        cur.execute(
            """INSERT INTO housekeeping_runs
               (run_at, cutoff_date, delays_deleted, cancellations_deleted, seen_trips_deleted,
                line_visibility_deleted, line_anomalies_deleted, alerts_deleted, scan_runs_deleted,
                train_announcements_deleted, error)
               VALUES (%(run_at)s, %(cutoff_date)s, %(delays_deleted)s, %(cancellations_deleted)s,
                       %(seen_trips_deleted)s, %(line_visibility_deleted)s, %(line_anomalies_deleted)s,
                       %(alerts_deleted)s, %(scan_runs_deleted)s, %(train_announcements_deleted)s, %(error)s)""",
            {
                # cutoff_date keeps its original meaning -- "everything before
                # this is gone" -- which is now simply the window's own start.
                "run_at": now, "cutoff_date": start_date, "error": error,
                "delays_deleted": counts.get("delays_deleted"),
                "cancellations_deleted": counts.get("cancellations_deleted"),
                "seen_trips_deleted": counts.get("seen_trips_deleted"),
                "line_visibility_deleted": counts.get("line_visibility_deleted"),
                "line_anomalies_deleted": counts.get("line_anomalies_deleted"),
                "alerts_deleted": counts.get("alerts_deleted"),
                "scan_runs_deleted": counts.get("scan_runs_deleted"),
                "train_announcements_deleted": counts.get("train_announcements_deleted"),
            },
        )
        # housekeeping_runs is this script's OWN audit table -- every other
        # table it touches gets a window, but this one never did, so it grew
        # one row/day forever. Pruned separately from the try/except above
        # (deliberately not counted in that same row, which would need yet
        # another column for a self-referential count) -- found by code
        # review 2026-07-08. Lower bound only, so the row inserted moments
        # ago on a post-season run survives its own cleanup.
        cur.execute("DELETE FROM housekeeping_runs WHERE run_at < %s", (start_ts,))
        print("Pruned %d old housekeeping_runs row(s)" % cur.rowcount)
        conn.commit()
        cur.close()
        conn.close()

    if error:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
