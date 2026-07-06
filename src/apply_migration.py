"""Apply a SQL migration file against Postgres (Supabase).

Substitutes ${ENV_VAR_NAME} placeholders in the SQL with environment
variables before executing — the mechanism that keeps secrets (e.g. a
passphrase baked into an RLS policy) out of committed .sql files. See
docs/RUNBOOK.md#applying-migrations for how this is wired to
.github/workflows/migrate.yml.

Usage:
    python src/apply_migration.py src/migrations/001_claim_tracking.sql
"""

import os
import re
import sys

import db

PLACEHOLDER_RE = re.compile(r"\$\{([A-Z0-9_]+)\}")


def substitute_env(sql):
    def repl(match):
        name = match.group(1)
        value = os.environ.get(name)
        if value is None:
            raise RuntimeError("Migration references ${%s} but that environment variable is not set." % name)
        return value.replace("'", "''")  # only correct where the placeholder sits inside '...' in the SQL
    return PLACEHOLDER_RE.sub(repl, sql)


def main():
    if len(sys.argv) != 2:
        print("Usage: python src/apply_migration.py <path-to-sql-file>")
        sys.exit(1)

    with open(sys.argv[1], "r", encoding="utf-8") as f:
        sql = substitute_env(f.read())

    conn = db.connect()
    cur = conn.cursor()
    try:
        cur.execute(sql)
        conn.commit()
        print("Migration applied: %s" % sys.argv[1])
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
