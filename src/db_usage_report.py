"""One-off diagnostic: print total database size and a per-table size/row-count
breakdown. Read-only -- no writes, safe to run against a struggling database.

Usage:
    python src/db_usage_report.py
"""

import db


def main():
    conn = db.connect()
    cur = conn.cursor()
    try:
        cur.execute("SELECT pg_size_pretty(pg_database_size(current_database()))")
        print("Total database size: %s" % cur.fetchone()[0])

        cur.execute(
            """SELECT relname,
                      pg_size_pretty(pg_total_relation_size(relid)) AS total_size,
                      pg_size_pretty(pg_relation_size(relid)) AS table_size,
                      pg_size_pretty(pg_total_relation_size(relid) - pg_relation_size(relid)) AS index_size,
                      n_live_tup AS approx_rows
               FROM pg_stat_user_tables
               ORDER BY pg_total_relation_size(relid) DESC"""
        )
        print("\n%-28s %10s %10s %10s %12s" % ("table", "total", "table", "indexes", "approx_rows"))
        for relname, total_size, table_size, index_size, approx_rows in cur.fetchall():
            print("%-28s %10s %10s %10s %12s" % (relname, total_size, table_size, index_size, approx_rows))

        # How much of `delays` is trivial noise (GTFS-RT reports nonzero
        # delay constantly, down to single seconds) versus delays that
        # could ever matter for a claim (>=20 min) or are worth watching
        # (1-20 min)? Answers "what can we actually afford to drop".
        cur.execute(
            """SELECT
                   CASE
                       WHEN GREATEST(COALESCE(ABS(arrival_delay_sec), 0), COALESCE(ABS(departure_delay_sec), 0)) = 0
                           THEN '0s (endpoint/irregular only, no real delay)'
                       WHEN GREATEST(COALESCE(ABS(arrival_delay_sec), 0), COALESCE(ABS(departure_delay_sec), 0)) < 60
                           THEN '1-59s (noise)'
                       WHEN GREATEST(COALESCE(ABS(arrival_delay_sec), 0), COALESCE(ABS(departure_delay_sec), 0)) < 300
                           THEN '1-5 min'
                       WHEN GREATEST(COALESCE(ABS(arrival_delay_sec), 0), COALESCE(ABS(departure_delay_sec), 0)) < 1200
                           THEN '5-20 min'
                       ELSE '>=20 min (compensation-eligible range)'
                   END AS bucket,
                   COUNT(*) AS rows,
                   pg_size_pretty(SUM(pg_column_size(d.*))::bigint) AS approx_bytes
               FROM delays d
               GROUP BY 1
               ORDER BY 1"""
        )
        print("\nDelay-magnitude breakdown (approx bytes = sum of each row's on-disk width, indexes not included):")
        print("%-45s %10s %14s" % ("bucket", "rows", "approx_size"))
        for bucket, rows, approx_bytes in cur.fetchall():
            print("%-45s %10s %14s" % (bucket, rows, approx_bytes))
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
