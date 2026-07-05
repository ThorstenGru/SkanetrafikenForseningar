"""Daily housekeeping: delete rows older than config.RETENTION_DAYS from every
table. Postgres autovacuum reclaims the space on its own — no manual VACUUM
needed (unlike SQLite).

Usage:
    python src/housekeeping.py
"""

from datetime import date, datetime, timedelta, timezone

import config
import db


def main():
    now = datetime.now(timezone.utc)
    cutoff_date = date.today() - timedelta(days=config.RETENTION_DAYS)
    cutoff_ts = now - timedelta(days=config.RETENTION_DAYS)

    conn = db.connect()
    cur = conn.cursor()
    error = None
    counts = {}
    try:
        cur.execute("DELETE FROM delays WHERE trip_start_date < %s", (cutoff_date,))
        counts["delays_deleted"] = cur.rowcount

        cur.execute("DELETE FROM trip_cancellations WHERE trip_start_date < %s", (cutoff_date,))
        counts["cancellations_deleted"] = cur.rowcount

        cur.execute("DELETE FROM seen_trips WHERE trip_start_date < %s", (cutoff_date,))
        counts["seen_trips_deleted"] = cur.rowcount

        cur.execute("DELETE FROM line_daily_visibility WHERE trip_start_date < %s", (cutoff_date,))
        counts["line_visibility_deleted"] = cur.rowcount

        cur.execute("DELETE FROM line_visibility_anomalies WHERE trip_start_date < %s", (cutoff_date,))
        counts["line_visibility_deleted"] += cur.rowcount

        # Alerts have no trip_start_date — key off when we last saw them active.
        cur.execute("DELETE FROM alerts WHERE last_seen_at < %s", (cutoff_ts,))
        counts["alerts_deleted"] = cur.rowcount

        cur.execute("DELETE FROM scan_runs WHERE run_at < %s", (cutoff_ts,))
        counts["scan_runs_deleted"] = cur.rowcount

        conn.commit()
        print("Housekeeping done (cutoff %s): %s" % (cutoff_date, counts))
    except Exception as exc:
        conn.rollback()
        error = str(exc)
        print("ERROR during housekeeping: %s" % error)
    finally:
        cur.execute(
            """INSERT INTO housekeeping_runs
               (run_at, cutoff_date, delays_deleted, cancellations_deleted, seen_trips_deleted,
                line_visibility_deleted, alerts_deleted, scan_runs_deleted, error)
               VALUES (%(run_at)s, %(cutoff_date)s, %(delays_deleted)s, %(cancellations_deleted)s,
                       %(seen_trips_deleted)s, %(line_visibility_deleted)s, %(alerts_deleted)s,
                       %(scan_runs_deleted)s, %(error)s)""",
            {
                "run_at": now, "cutoff_date": cutoff_date, "error": error,
                "delays_deleted": counts.get("delays_deleted"),
                "cancellations_deleted": counts.get("cancellations_deleted"),
                "seen_trips_deleted": counts.get("seen_trips_deleted"),
                "line_visibility_deleted": counts.get("line_visibility_deleted"),
                "alerts_deleted": counts.get("alerts_deleted"),
                "scan_runs_deleted": counts.get("scan_runs_deleted"),
            },
        )
        conn.commit()
        cur.close()
        conn.close()

    if error:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
