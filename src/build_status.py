"""Builds a live status dashboard for every component this project depends
on: the Supabase database, each GitHub Actions workflow, the deployed Pages
site, and the static GTFS index. Refreshed every 15 minutes by status.yml,
independent of (and much lighter than) the live scanner -- this page needs
to work and say something useful even when the database itself is down,
since that's exactly the situation it exists to surface. Never touches
Trafiklab's static API (60 req/30 days quota) or KoDa -- static-index
freshness is read from the committed sqlite file itself, not re-fetched.

Usage:
    python src/build_status.py --out status.html
"""

import argparse
import json
import os
import sqlite3
import time
from datetime import datetime, timezone

import psycopg2
import requests

import config

TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "status_template.html")
DB_PROBE_TIMEOUT_SEC = 8
GITHUB_API_TIMEOUT_SEC = 10

WORKFLOWS = [
    ("scan.yml", "Scan Skånetrafiken delays"),
    ("backfill.yml", "Backfill historical data (KoDa)"),
    ("housekeeping.yml", "Daily housekeeping"),
    ("migrate.yml", "Apply database migration"),
    ("deploy-pages.yml", "Deploy pages"),
    ("db_usage_report.yml", "DB usage report"),
    ("status.yml", "Status dashboard (this page)"),
]

PAGE_PATHS = [
    ("index.html", "Delay dashboard"),
    ("compensation.html", "Compensation estimate"),
    ("claims.html", "Reasonable claim chains"),
]

SITE_BASE = "https://thorstengru.github.io/SkanetrafikenForseningar/"


def check_database():
    """A bare SELECT 1 with a short timeout -- the whole point is to fail
    fast and clearly rather than hang, which is exactly what happened
    during the 2026-07-07 disk-full incident this page was built for."""
    start = time.time()
    try:
        conn = psycopg2.connect(config.database_url(), connect_timeout=DB_PROBE_TIMEOUT_SEC)
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        cur.close()
        conn.close()
        return {"ok": True, "latencyMs": round((time.time() - start) * 1000), "error": None}
    except Exception as exc:
        return {"ok": False, "latencyMs": round((time.time() - start) * 1000), "error": str(exc)[:300]}


def db_table_sizes():
    try:
        conn = psycopg2.connect(config.database_url(), connect_timeout=DB_PROBE_TIMEOUT_SEC)
        cur = conn.cursor()
        cur.execute("SELECT pg_size_pretty(pg_database_size(current_database()))")
        total = cur.fetchone()[0]
        cur.execute(
            """SELECT relname, pg_size_pretty(pg_total_relation_size(relid)), n_live_tup
               FROM pg_catalog.pg_statio_user_tables
               JOIN pg_stat_user_tables USING (relid)
               ORDER BY pg_total_relation_size(relid) DESC LIMIT 12"""
        )
        tables = [{"name": n, "size": s, "rows": r} for n, s, r in cur.fetchall()]
        cur.close()
        conn.close()
        return {"total": total, "tables": tables}
    except Exception:
        return None


def check_workflows():
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY", "ThorstenGru/SkanetrafikenForseningar")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = "Bearer %s" % token
    out = []
    for filename, label in WORKFLOWS:
        entry = {"label": label, "status": None, "conclusion": None, "at": None, "url": None}
        try:
            resp = requests.get(
                "https://api.github.com/repos/%s/actions/workflows/%s/runs" % (repo, filename),
                params={"per_page": 1},
                headers=headers,
                timeout=GITHUB_API_TIMEOUT_SEC,
            )
            resp.raise_for_status()
            runs = resp.json().get("workflow_runs", [])
            if runs:
                r = runs[0]
                entry.update({
                    "status": r.get("status"),
                    "conclusion": r.get("conclusion"),
                    "at": r.get("updated_at") or r.get("created_at"),
                    "url": r.get("html_url"),
                })
            else:
                entry["status"] = "no runs yet"
        except Exception as exc:
            entry["status"] = "error"
            entry["error"] = str(exc)[:200]
        out.append(entry)
    return out


def check_pages():
    out = []
    for path, label in PAGE_PATHS:
        entry = {"label": label, "path": path}
        try:
            resp = requests.head(SITE_BASE + path, timeout=GITHUB_API_TIMEOUT_SEC, allow_redirects=True)
            entry["ok"] = resp.status_code == 200
            entry["statusCode"] = resp.status_code
        except Exception as exc:
            entry["ok"] = False
            entry["statusCode"] = None
            entry["error"] = str(exc)[:200]
        out.append(entry)
    return out


def static_index_info():
    path = config.STATIC_INDEX_PATH
    if not os.path.exists(path):
        return None
    try:
        conn = sqlite3.connect(path)
        row = conn.execute("SELECT built_at FROM meta").fetchone()
        conn.close()
        if row and row[0]:
            return {"builtAt": datetime.fromtimestamp(row[0], tz=timezone.utc).isoformat()}
    except Exception as exc:
        return {"error": str(exc)[:200]}
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=os.path.join(config.REPO_ROOT, "status.html"))
    args = parser.parse_args()

    database = check_database()
    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "database": database,
        "tableSizes": db_table_sizes() if database["ok"] else None,
        "workflows": check_workflows(),
        "pages": check_pages(),
        "staticIndex": static_index_info(),
    }

    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template = f.read()
    payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</script", "<\\/script")
    html = template.replace("__DATA_JSON__", payload_json)

    out_dir = os.path.dirname(args.out)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)
    print("Status report written to %s (db_ok=%s)" % (args.out, database["ok"]))


if __name__ == "__main__":
    main()
