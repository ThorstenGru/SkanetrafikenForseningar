"""Generate the "Ersättning vid försening" (delay compensation) estimate
page from the same per-trip data build_dashboard.py uses.

This is an ILLUSTRATIVE estimate only, not a real claim calculation — see
docs/COMPENSATION_RULES.md for the source rules, their disclaimers, and the
open questions still marked unclear there. Two independent compensation
paths are estimated per eligible trip, per Skånetrafiken's terms:
  - Price deduction (prisavdrag) — tiered % of the Sommarbiljett's
    per-single-trip price, cash or as a voucher code (+50%).
  - Alternative transport (own car) — the tax-free mileage rate x this
    trip's distance, capped at the published maximum. No voucher bonus is
    documented for this path, so cash and voucher are shown as equal.
These are alternatives, not additive — the rules explicitly forbid
claiming both for the same journey (section 3/4).

Only Sommarbiljett-valid trips delayed >=20 minutes at the final stop are
eligible. When the final stop was never captured in the feed, the largest
observed delay is used instead and flagged as approximate. Fully cancelled
trips are listed but excluded from the calculation (the rules don't specify
a clear formula for a trip that never ran at all). Trips whose reason
mentions a replacement bus are also listed but excluded, regardless of
delay length -- see docs/COMPENSATION_RULES.md for why.

Usage:
    python src/build_compensation.py                # full 45-day retention window
    python src/build_compensation.py --out other.html
"""

import argparse
import json
import os
import re
from datetime import datetime, timedelta

import config
import db
from build_dashboard import fetch_detail_rows
from trafikverket_merge import merge_trafikverket

TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "compensation_template.html")

# Same patterns already validated against live data (2026-07-08, found 198
# matching trips over 45 days) when investigating a real claim rejection --
# see docs/TRAFIKVERKET_INTEGRATION.md and the "resalternativ" discussion in
# COMPENSATION_RULES.md. Requested by the user as a hard rule, 2026-07-08:
# any journey whose reason text mentions a replacement bus is never
# claimable here, regardless of its delay length -- a replacement bus IS a
# resalternativ (alternative route to the final destination), which is
# exactly the undocumented mechanism Skånetrafiken cited when rejecting a
# real claim on this project. Rather than guess whether a specific bus
# substitution would or wouldn't survive that argument, this project simply
# never recommends one.
_REPLACEMENT_BUS_PATTERNS = [
    re.compile(r"ersättningsbuss", re.IGNORECASE),
    re.compile(r"buss.*ersätter", re.IGNORECASE | re.DOTALL),
    re.compile(r"ersätter.*tåg", re.IGNORECASE | re.DOTALL),
    re.compile(r"buss istället", re.IGNORECASE),
]


def _mentions_replacement_bus(reason):
    if not reason:
        return False
    return any(p.search(reason) for p in _REPLACEMENT_BUS_PATTERNS)


def _trip_earliest_time(r):
    """Best-known instant this trip actually happened, for the ticket-
    purchase cutoff below. Prefers the earliest recorded stop time (sched
    or actual) since that's precise; falls back to firstSeen (when the
    scanner first noticed the trip) for cancelled trips, which carry no
    per-stop detail at all."""
    candidates = [
        datetime.fromisoformat(t)
        for s in (r.get("stops") or [])
        for t in (s.get("schedTimeIso"), s.get("actTimeIso"))
        if t
    ]
    if candidates:
        return min(candidates)
    return datetime.fromisoformat(r["firstSeen"])


def compute_compensation(rows):
    purchased_at = config.sommarbiljett_purchased_at()
    out = []
    for r in rows:
        if _trip_earliest_time(r) < purchased_at:
            continue  # trip happened before this ticket was purchased — never eligible, never shown

        if r["status"] == "CANCELLED_TRIP":
            out.append(dict(r, calc="cancelled", delayUsedMin=None, delayApprox=False))
            continue

        if _mentions_replacement_bus(r.get("reason")):
            # Not "eligible" and not "cancelled" -- a distinct category so
            # the UI can say exactly why this one isn't claimable, rather
            # than silently dropping it (this project's own "no silent
            # caps" principle). Still carries whatever delay figure exists,
            # for visibility, but never a computed deduction amount.
            approx = r["finalDelayMin"] is None
            delay_min = r["finalDelayMin"] if not approx else r["maxDelayMin"]
            out.append(dict(r, calc="bus_replaced", delayUsedMin=delay_min, delayApprox=approx))
            continue

        delay_min = r["finalDelayMin"]
        approx = False
        if delay_min is None:
            delay_min = r["maxDelayMin"]
            approx = True
        if delay_min is None or delay_min < config.MIN_DELAY_FOR_COMPENSATION_MIN:
            continue  # not eligible, or no delay data at all — leave out of the estimate entirely

        pct = config.price_deduction_pct(delay_min)
        deduction_cash = round(pct * config.SOMMARBILJETT_SINGLE_TRIP_PRICE_SEK, 2)
        deduction_voucher = round(deduction_cash * config.VOUCHER_BONUS, 2)

        car_cash = None
        if r["distanceKm"]:
            car_cash = round(min(r["distanceKm"] * config.CAR_RATE_SEK_PER_KM, config.ALT_TRANSPORT_CAP_SEK), 2)

        out.append(dict(
            r,
            calc="eligible",
            delayUsedMin=delay_min,
            delayApprox=approx,
            deductionPct=int(round(pct * 100)),
            deductionCash=deduction_cash,
            deductionVoucher=deduction_voucher,
            carCash=car_cash,
            carVoucher=car_cash,
        ))
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=os.path.join(config.REPO_ROOT, "compensation.html"))
    args = parser.parse_args()

    end_date = datetime.now(config.LOCAL_TZ).date()
    start_date = end_date - timedelta(days=config.RETENTION_DAYS - 1)
    start_date = max(start_date, config.sommarbiljett_purchased_at().date())

    conn = db.connect()
    cur = conn.cursor()
    try:
        rows = fetch_detail_rows(cur, start_date, end_date, None)
        rows = merge_trafikverket(rows, cur, start_date, end_date)
    finally:
        cur.close()
        conn.close()

    comp_rows = compute_compensation(rows)

    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template = f.read()

    payload = json.dumps(
        {
            "rows": comp_rows,
            "windowStart": start_date.strftime("%Y%m%d"),
            "windowEnd": end_date.strftime("%Y%m%d"),
            "constants": {
                "ticketPriceSek": config.SOMMARBILJETT_PRICE_SEK,
                "divisor": config.SOMMARBILJETT_DIVISOR,
                "singleTripPriceSek": round(config.SOMMARBILJETT_SINGLE_TRIP_PRICE_SEK, 3),
                "carRateSekPerKm": config.CAR_RATE_SEK_PER_KM,
                "altTransportCapSek": config.ALT_TRANSPORT_CAP_SEK,
                "voucherBonus": config.VOUCHER_BONUS,
                "minDelayMin": config.MIN_DELAY_FOR_COMPENSATION_MIN,
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

    eligible = sum(1 for r in comp_rows if r["calc"] == "eligible")
    cancelled = sum(1 for r in comp_rows if r["calc"] == "cancelled")
    bus_replaced = sum(1 for r in comp_rows if r["calc"] == "bus_replaced")
    print("Compensation page written to %s (%d eligible trips, %d cancelled trips listed but excluded, %d bus-replaced trips listed but excluded, window %s..%s)" % (
        args.out, eligible, cancelled, bus_replaced, start_date, end_date))


if __name__ == "__main__":
    main()
