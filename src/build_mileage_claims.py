"""Generate the "Confirmed mileage claims" page -- a much stricter subset of
compute_compensation()'s output than compensation.html/claims.html show,
scoped specifically to §4 of docs/COMPENSATION_RULES.md ("Compensation for
alternative transport" -- the own-car/mileage reimbursement path).

Requested by the user 2026-07-20: "I would like to see all journeys where
§4 is completely fulfilled, fulfilled by the book, and which are reasonable
to claim (where Skånetrafikens handläggare says 'yes -- that makes
sense')." §4 itself only requires >=20 min delay, a reasonable/minimized
documented cost, and mutual exclusivity with price deduction -- but "a
handläggare says yes" needs the underlying DELAY ITSELF to be beyond
reasonable doubt too, which is where this page goes further than §4's own
text: it only keeps rows whose delayBasis is the strongest evidence tier
this project has (a genuinely confirmed final arrival, from GTFS-RT itself
or corroborated by Trafikverket) -- excluding unconfirmed predictions,
"station passed late" intermediate-only fallbacks, and single-source
Trafikverket-only rows, all of which are exactly the kind of number a case
handler could reasonably push back on. Also excludes recentTrip (still
inside Skånetrafiken's own 1-2 day registration-lag window -- see
config.SKANETRAFIKEN_REGISTRATION_LAG_DAYS) and anything without a real
distanceKm (mileage is literally uncomputable without one).

Usage:
    python src/build_mileage_claims.py                # full 45-day retention window
    python src/build_mileage_claims.py --out other.html
"""

import argparse
import json
import os
from datetime import datetime, timedelta

import config
import db
from build_dashboard import fetch_detail_rows
from build_compensation import compute_compensation
from trafikverket_merge import merge_trafikverket

TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mileage_claims_template.html")

# The two delayBasis values (build_compensation.py's _delay_basis()) strong
# enough for this page: either GTFS-RT itself captured a genuine
# post-arrival observation, or a second source (Trafikverket) corroborated
# an otherwise-unconfirmed one. Everything else (final_stop_prediction_
# unconfirmed, max_delay_fallback, trafikverket_only) is exactly the kind
# of number this page exists to exclude.
STRICT_DELAY_BASES = {"final_arrival_confirmed", "final_confirmed_via_trafikverket"}


def _origin_name(r):
    """The row's own `stops` list already carries every stop's name (no
    extra static-index lookup needed) -- min stop_sequence is the origin,
    same convention build_claims.py's enrich_with_endpoints() uses."""
    stops = r.get("stops") or []
    if not stops:
        return None
    return min(stops, key=lambda s: s.get("seq") or 0).get("name")


def strictly_qualified_mileage_claims(comp_rows):
    """Returns (qualified_rows, exclusion_counts) -- exclusion_counts is
    disclosed in the build log, not silently dropped, per this project's
    own "no silent caps" principle (see e.g. build_compensation.py's own
    low_value_skipped count)."""
    qualified = []
    excluded = {"not_eligible": 0, "weak_delay_basis": 0, "recent_trip": 0, "no_distance": 0, "below_150kr": 0}
    for r in comp_rows:
        if r["calc"] != "eligible":
            excluded["not_eligible"] += 1
            continue
        if r.get("delayBasis") not in STRICT_DELAY_BASES:
            excluded["weak_delay_basis"] += 1
            continue
        if r.get("recentTrip"):
            excluded["recent_trip"] += 1
            continue
        if not r.get("distanceKm"):
            excluded["no_distance"] += 1
            continue
        if r.get("carCash") is None or r["carCash"] < config.MIN_CLAIM_VALUE_SEK:
            excluded["below_150kr"] += 1
            continue
        qualified.append(dict(r, originName=_origin_name(r)))
    return qualified, excluded


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=os.path.join(config.REPO_ROOT, "mileage_claims.html"))
    args = parser.parse_args()

    end_date = datetime.now(config.LOCAL_TZ).date()
    start_date = end_date - timedelta(days=config.RETENTION_DAYS - 1)
    start_date = max(start_date, config.sommarbiljett_purchased_at().date())

    conn = db.connect()
    cur = conn.cursor()
    try:
        rows = fetch_detail_rows(cur, start_date, end_date, None)
        rows, _tv_stats = merge_trafikverket(rows, cur, start_date, end_date)
    finally:
        cur.close()
        conn.close()

    comp_rows = compute_compensation(rows)
    qualified, excluded = strictly_qualified_mileage_claims(comp_rows)
    qualified.sort(key=lambda r: r["date"], reverse=True)

    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template = f.read()

    payload = json.dumps(
        {
            "rows": qualified,
            "windowStart": start_date.strftime("%Y%m%d"),
            "windowEnd": end_date.strftime("%Y%m%d"),
            "excluded": excluded,
            "constants": {
                "carRateSekPerKm": config.CAR_RATE_SEK_PER_KM,
                "altTransportCapSek": config.ALT_TRANSPORT_CAP_SEK,
                "minDelayMin": config.MIN_DELAY_FOR_COMPENSATION_MIN,
                "minClaimValueSek": config.MIN_CLAIM_VALUE_SEK,
            },
        },
        ensure_ascii=False, separators=(",", ":"),
    ).replace("</script", "<\\/script")
    html = template.replace("__DATA_JSON__", payload)

    out_dir = os.path.dirname(args.out)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)

    print("Mileage claims page written to %s (%d qualified, excluded: %s, window %s..%s)" % (
        args.out, len(qualified), excluded, start_date, end_date))


if __name__ == "__main__":
    main()
