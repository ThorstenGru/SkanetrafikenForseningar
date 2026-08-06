"""Build every published page from ONE pass over the database.

Why this exists (2026-08-06). Each page used to be its own process with its
own connection, and four of them -- build_compensation.py, build_claims.py,
build_mileage_claims.py and data_quality_check.py -- independently ran the
identical full-window `fetch_detail_rows()` + `merge_trafikverket()` pair,
while build_dashboard.py ran a fifth, narrower copy. Same rows, same window,
fetched five times per pipeline run, every run. On Supabase's free tier that
duplication was the dominant source of the organisation's egress: the org
was measured at 16.25 GB against a 5.5 GB allowance, with restriction (402s
on every project in the org, BliGlömd included) scheduled for 2026-08-07.

Everything here fetches once and renders from memory. The pages produced are
byte-for-byte what the individual scripts produce -- this is a plumbing
change, not a data change. Each build_*.py keeps a working `main()` for
standalone/manual use; they simply aren't how the pipeline builds any more.

ORDERING IS LOAD-BEARING. merge_trafikverket() mutates rows in place
(enrich_reasons() fills in `reason` on rows that had none), so the dashboard
must be rendered and written BEFORE the merge runs. The dashboard has never
included Trafikverket enrichment or gap-fill rows, and this file is not the
place to change that silently: its detail table would then disagree with its
own history trend, which is a pure SQL aggregate over `delays` alone. See
docs/ARCHITECTURE.md.

Usage:
    python src/build_all.py --out-dir pages_site
"""

import argparse
import os
import traceback
from datetime import timedelta

import build_claims
import build_compensation
import build_dashboard
import build_mileage_claims
import config
import data_quality_check
import db
from build_compensation import compute_compensation
from build_dashboard import fetch_detail_rows, fetch_recent_line_anomalies, fetch_trend
from trafikverket_merge import merge_trafikverket


def _slice(rows, start_date, end_date):
    """Rows whose trip date falls in [start, end]. `date` is a YYYYMMDD
    string, which sorts lexicographically in the same order as the dates it
    encodes -- so this is exactly the predicate the SQL BETWEEN applied, just
    without a second round trip to ask for rows we already hold."""
    return [r for r in rows if start_date.strftime("%Y%m%d") <= r["date"] <= end_date.strftime("%Y%m%d")]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default=os.path.join(config.REPO_ROOT, "pages_site"))
    parser.add_argument(
        "--dashboard-days", type=int, default=build_dashboard.DEFAULT_DETAIL_DAYS,
        help="Days of raw detail on the dashboard (its history trend always covers the whole season).")
    parser.add_argument(
        "--skip-data-quality", action="store_true",
        help="Skip the data_quality_runs bookkeeping pass.")
    args = parser.parse_args()

    out_dir = args.out_dir
    os.makedirs(out_dir, exist_ok=True)

    # Two ranges, deliberately. The claim pages have always been clamped to
    # the ticket purchase date as well as the season (config.claim_window());
    # the dashboard has always covered the season alone. They coincide today,
    # but deriving both and slicing per consumer means this file reproduces
    # each page's own window exactly rather than assuming they stay equal.
    win_start, win_end = config.window_bounds()
    claim_start, claim_end = config.claim_window()

    conn = db.connect()
    cur = conn.cursor()
    try:
        trend = fetch_trend(cur)
        line_anomalies = fetch_recent_line_anomalies(cur)

        # THE fetch. Everything below is served from this.
        rows = fetch_detail_rows(cur, win_start, win_end, None)
        print("Fetched %d trip row(s) for %s .. %s -- shared by every page below." % (
            len(rows), win_start, win_end))

        # --- Dashboard: BEFORE the Trafikverket merge mutates anything ---
        dash_start = max(win_end - timedelta(days=args.dashboard_days - 1), win_start)
        build_dashboard.render(
            os.path.join(out_dir, "index.html"),
            trend, _slice(rows, dash_start, win_end), line_anomalies,
            "%s .. %s" % (dash_start, win_end),
        )

        # --- Claim-facing pages: one merge, shared by all three ---
        merged, tv_stats = merge_trafikverket(
            _slice(rows, claim_start, claim_end), cur, claim_start, claim_end)

        # compute_compensation() is re-run per page rather than shared. It is
        # pure CPU (no database access), and its output dicts are shallow
        # copies whose `stops` lists the claims/mileage enrichment then
        # rebinds -- giving each page its own set is what lets them share the
        # expensive upstream rows without one page's enrichment leaking into
        # another's. See build_claims.render()'s own note.
        build_compensation.render(
            os.path.join(out_dir, "compensation.html"),
            compute_compensation(merged), claim_start, claim_end)
        build_claims.render(
            os.path.join(out_dir, "claims.html"),
            compute_compensation(merged), claim_start, claim_end)
        build_mileage_claims.render(
            os.path.join(out_dir, "mileage_claims.html"),
            compute_compensation(merged), claim_start, claim_end)

        # --- Bookkeeping, over the exact rows the pages were built from ---
        if not args.skip_data_quality:
            # Isolated the same way scan.yml's own `continue-on-error` step
            # isolated it before: this is a reporting pass over data the
            # pipeline already committed, and it must never be the reason a
            # page fails to publish.
            try:
                data_quality_check.record(cur, merged, tv_stats)
                conn.commit()
            except Exception:  # noqa: BLE001 -- see above
                conn.rollback()
                traceback.print_exc()
                print("Data quality bookkeeping failed -- pages were still built.")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
