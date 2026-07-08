"""One-off diagnostic: list current Postgres sessions/locks, and optionally
terminate a stuck one. Written to investigate repeated scan.py hangs/
statement-timeouts possibly caused by a zombie connection left over from a
GH Actions job killed mid-transaction by a timeout-minutes cutoff.

Usage:
    python src/db_activity_check.py            # list only
    python src/db_activity_check.py --kill PID  # terminate one backend
"""

import argparse

import db


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--kill", type=int, default=None, help="pg_terminate_backend() this PID")
    args = parser.parse_args()

    conn = db.connect()
    cur = conn.cursor()
    try:
        if args.kill:
            cur.execute("SELECT pg_terminate_backend(%s)", (args.kill,))
            print("Terminate result for PID %s: %s" % (args.kill, cur.fetchone()[0]))
            conn.commit()
            return

        cur.execute(
            """SELECT pid, state, wait_event_type, wait_event, xact_start, query_start,
                      now() - query_start AS query_age, now() - xact_start AS xact_age,
                      left(query, 120) AS query
               FROM pg_stat_activity
               WHERE datname = current_database() AND pid <> pg_backend_pid()
               ORDER BY xact_start ASC NULLS LAST"""
        )
        rows = cur.fetchall()
        print("%d other session(s) on this database:" % len(rows))
        for pid, state, wait_type, wait_event, xact_start, query_start, query_age, xact_age, query in rows:
            print("\nPID %s  state=%s  wait=%s/%s" % (pid, state, wait_type, wait_event))
            print("  query_age=%s  xact_age=%s" % (query_age, xact_age))
            print("  query: %s" % query)

        cur.execute(
            """SELECT blocked.pid AS blocked_pid, blocking.pid AS blocking_pid,
                      left(blocked.query, 80) AS blocked_query
               FROM pg_locks bl
               JOIN pg_stat_activity blocked ON blocked.pid = bl.pid
               JOIN pg_locks kl ON kl.locktype = bl.locktype AND kl.database IS NOT DISTINCT FROM bl.database
                    AND kl.relation IS NOT DISTINCT FROM bl.relation AND kl.pid != bl.pid AND kl.granted
               JOIN pg_stat_activity blocking ON blocking.pid = kl.pid
               WHERE NOT bl.granted"""
        )
        blocks = cur.fetchall()
        print("\n%d blocking relationship(s):" % len(blocks))
        for blocked_pid, blocking_pid, blocked_query in blocks:
            print("  PID %s is blocked by PID %s -- query: %s" % (blocked_pid, blocking_pid, blocked_query))
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
