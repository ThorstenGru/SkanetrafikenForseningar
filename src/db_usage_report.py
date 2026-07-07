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
               FROM pg_catalog.pg_statio_user_tables
               JOIN pg_stat_user_tables USING (relid)
               ORDER BY pg_total_relation_size(relid) DESC"""
        )
        print("\n%-28s %10s %10s %10s %12s" % ("table", "total", "table", "indexes", "approx_rows"))
        for relname, total_size, table_size, index_size, approx_rows in cur.fetchall():
            print("%-28s %10s %10s %10s %12s" % (relname, total_size, table_size, index_size, approx_rows))
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
