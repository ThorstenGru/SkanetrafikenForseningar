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
a clear formula for a trip that never ran at all).

Usage:
    python src/build_compensation.py                # full 45-day retention window
    python src/build_compensation.py --out other.html
"""

import argparse
import json
import os
from datetime import date, timedelta

import config
import db
from build_dashboard import fetch_detail_rows

TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "compensation_template.html")


def compute_compensation(rows):
    out = []
    for r in rows:
        if r["status"] == "CANCELLED_TRIP":
            out.append(dict(r, calc="cancelled", delayUsedMin=None, delayApprox=False))
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

    end_date = date.today()
    start_date = end_date - timedelta(days=config.RETENTION_DAYS - 1)

    conn = db.connect()
    cur = conn.cursor()
    try:
        rows = fetch_detail_rows(cur, start_date, end_date, None)
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
    print("Compensation page written to %s (%d eligible trips, %d cancelled trips listed but excluded, window %s..%s)" % (
        args.out, eligible, cancelled, start_date, end_date))


if __name__ == "__main__":
    main()
