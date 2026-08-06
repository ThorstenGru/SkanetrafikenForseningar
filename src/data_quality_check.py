"""Runs after every scan (wired into scan.yml, continue-on-error): persists
a queryable trail of how much of this project's own delay data actually
rests on confirmed evidence, plus a handful of structural consistency
checks. See migration 018_data_quality_runs.sql for the full background.

Requested by the user 2026-07-20: "with every scanner run... review the
predictions if they have come true or cured themselves... make sure we
have every time a full, consistent and correct data set." Investigated
first: does GTFS-RT re-polling alone ever cure a stale prediction? No --
checked directly against the live data, most unconfirmed final-stop rows
have already been polled 15-20+ times and are still unconfirmed, because
GTFS-RT's own "arrival_time" is a rolling prediction that keeps moving
forward as a delay grows, right up until the vehicle actually arrives. The
only real cure is a second source (Trafikverket's post-event
TimeAtLocation, confirm_stale_finals() in trafikverket_merge.py, already
running on every build_compensation.py/build_claims.py call) -- this
script exists to persist that mechanism's own numbers so they're a
historical record, not a print() line that only ever existed in one
Action run's own log.

Usage:
    python src/data_quality_check.py
"""

from collections import Counter
from datetime import datetime, timezone

import config
import db
from build_compensation import _delay_basis
from build_dashboard import fetch_detail_rows
from trafikverket_merge import merge_trafikverket


def delay_basis_counts(rows):
    """Tallies _delay_basis() across every non-cancelled trip in the season
    window -- the same classification build_compensation.py uses for the
    compensation estimate, just applied to ALL trips (not only ones that
    clear the 20-min/150kr thresholds), since the question here is "how much
    of our data is confirmed" overall, not "how much is claimable".

    Takes already-merged rows rather than fetching its own (2026-08-06):
    when this runs as part of build_all.py it must count the exact same row
    set the pages were built from, and re-querying it was both a second
    source of truth and -- over the full window, on every scan -- a large
    share of this project's Supabase egress."""
    return Counter(_delay_basis(r) for r in rows if r["status"] != "CANCELLED_TRIP")


def _structural_checks(cur):
    """Basic invariants that should always hold if the data is internally
    consistent -- each returns a count of VIOLATIONS (0 is healthy).

    orphaned_final_stop_trips is the one exception to that "0 is healthy"
    framing, kept for backward-compat naming with migration 018's own
    column -- checked directly (2026-07-20) against a sample of 10 real
    rows: every one had exactly ONE recorded row total, at the final stop,
    with no earlier stop ever seen. That's a coverage characteristic of
    interval-based polling (this project only ever sees what's in the feed
    at poll time -- a trip that's already near its end when it first
    enters our polling window, or a long route where we happened to catch
    only the tail before it dropped from the feed, is expected), NOT
    corrupted data. A genuinely large SPIKE in this number (vs. its usual
    baseline) would be worth investigating -- the raw count on its own is
    not evidence of a bug."""
    checks = {}

    cur.execute(
        """SELECT count(*) FROM (
               SELECT trip_id, trip_start_date FROM delays WHERE is_final_stop = true
               EXCEPT
               SELECT trip_id, trip_start_date FROM delays WHERE is_origin_stop = true
           ) x"""
    )
    checks["orphaned_final_stop_trips"] = cur.fetchone()[0]

    cur.execute(
        """SELECT count(*) FROM delays
           WHERE arrival_time IS NOT NULL AND departure_time IS NOT NULL
             AND departure_time < arrival_time"""
    )
    checks["arrival_after_departure_rows"] = cur.fetchone()[0]

    cur.execute(
        """SELECT count(*) FROM delays
           WHERE abs(coalesce(arrival_delay_sec, 0)) > 86400
              OR abs(coalesce(departure_delay_sec, 0)) > 86400"""
    )
    checks["implausible_delay_rows"] = cur.fetchone()[0]

    cur.execute(
        """SELECT count(*) FROM (
               SELECT trip_id, trip_start_date FROM delays
               INTERSECT
               SELECT trip_id, trip_start_date FROM trip_cancellations
           ) x"""
    )
    checks["cancelled_and_delayed_trips"] = cur.fetchone()[0]

    return checks


def record(cur, rows, tv_stats):
    """Persist one data_quality_runs row for an already-merged row set.

    Callable directly by build_all.py (which has `rows`/`tv_stats` in hand
    from the shared query pass) as well as by this module's own main().
    Swallows its own failures exactly as before -- a reporting pass over
    data the pipeline has already committed must never take the build down
    with it."""
    now = datetime.now(timezone.utc)
    error = None
    basis_counts, struct_checks = Counter(), {}
    try:
        basis_counts = delay_basis_counts(rows)
        struct_checks = _structural_checks(cur)
    except Exception as exc:  # noqa: BLE001 -- log and persist, never break the scan pipeline
        import traceback
        traceback.print_exc()
        error = "%s: %s" % (type(exc).__name__, exc)
    finally:
        total = sum(basis_counts.values())
        cur.execute(
            """INSERT INTO data_quality_runs
               (run_at, final_stop_rows_total, final_stop_rows_unconfirmed,
                confirmed_via_trafikverket_now, max_delay_fallback_trips,
                orphaned_final_stop_trips, arrival_after_departure_rows,
                implausible_delay_rows, cancelled_and_delayed_trips, error)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                now, total or None,
                basis_counts.get("final_stop_prediction_unconfirmed"),
                tv_stats.get("confirmed"),
                basis_counts.get("max_delay_fallback"),
                struct_checks.get("orphaned_final_stop_trips"),
                struct_checks.get("arrival_after_departure_rows"),
                struct_checks.get("implausible_delay_rows"),
                struct_checks.get("cancelled_and_delayed_trips"),
                error,
            ),
        )

    if error:
        print("Data quality check FAILED: %s" % error)
        return

    print(
        "Data quality check: %d trip(s) considered -- %d confirmed final arrival, "
        "%d confirmed via Trafikverket, %d unconfirmed prediction, %d station-passed-late "
        "(final unknown), %d Trafikverket-only. Structural violations: %d orphaned, "
        "%d arrival-after-departure, %d implausible delay, %d cancelled-and-delayed." % (
            total,
            basis_counts.get("final_arrival_confirmed", 0),
            basis_counts.get("final_confirmed_via_trafikverket", 0),
            basis_counts.get("final_stop_prediction_unconfirmed", 0),
            basis_counts.get("max_delay_fallback", 0),
            basis_counts.get("trafikverket_only", 0),
            struct_checks.get("orphaned_final_stop_trips", 0),
            struct_checks.get("arrival_after_departure_rows", 0),
            struct_checks.get("implausible_delay_rows", 0),
            struct_checks.get("cancelled_and_delayed_trips", 0),
        )
    )


def main():
    """Standalone entry point -- fetches its own rows. build_all.py calls
    record() directly instead, reusing the rows it already has."""
    start_date, end_date = config.claim_window()

    conn = db.connect()
    cur = conn.cursor()
    try:
        rows = fetch_detail_rows(cur, start_date, end_date, None)
        rows, tv_stats = merge_trafikverket(rows, cur, start_date, end_date)
        record(cur, rows, tv_stats)
        conn.commit()
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
