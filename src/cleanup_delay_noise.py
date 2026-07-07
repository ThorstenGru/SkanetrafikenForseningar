"""One-off: delete sub-5-minute delay noise from `delays` (keeping origin/
final endpoints and irregular stops regardless of magnitude, matching
scan.py's new write filter -- see config.MIN_DELAY_TO_RECORD_SEC), then
VACUUM FULL the table so Postgres actually returns the freed space to
disk. Written for the 2026-07-07 free-tier storage incident: sub-5-minute
GTFS-RT jitter was 94% of this table's rows/bytes for zero compensation
value.

Requires migrations/010_add_origin_stop_flag.sql applied first -- an
earlier version of this script had no way to identify origin-stop rows
(only is_final_stop existed) and deleted them along with real noise,
undoing scan.py's "always confirm the origin" fix. Never loosen this
back to just is_final_stop=false.

VACUUM cannot run inside a transaction block, so the delete and the
vacuum use separate connections/commits.

Usage:
    python src/cleanup_delay_noise.py
"""

import config
import db


def main():
    conn = db.connect()
    cur = conn.cursor()
    try:
        cur.execute(
            """DELETE FROM delays
               WHERE GREATEST(COALESCE(ABS(arrival_delay_sec), 0), COALESCE(ABS(departure_delay_sec), 0)) < %s
                 AND is_final_stop = false
                 AND is_origin_stop = false
                 AND stop_schedule_relationship = 'SCHEDULED'""",
            (config.MIN_DELAY_TO_RECORD_SEC,),
        )
        deleted = cur.rowcount
        conn.commit()
        print("Deleted %d noise row(s) from delays" % deleted)
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    conn = db.connect()
    conn.autocommit = True  # required: VACUUM cannot run inside a transaction block
    cur = conn.cursor()
    try:
        print("Running VACUUM FULL on delays (reclaims the file space, can take a moment)...")
        cur.execute("VACUUM FULL delays")
        print("VACUUM FULL complete.")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
