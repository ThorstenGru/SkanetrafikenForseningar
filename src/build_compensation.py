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
from datetime import datetime

import config
import db
from build_dashboard import fetch_detail_rows
from trafikverket_merge import merge_trafikverket

TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "compensation_template.html")

# The replacement-bus rule and its patterns moved to config.py on
# 2026-08-06 so build_dashboard.py can apply it while it still has every
# matching alert in hand, not just the one that won the display race -- see
# _replacement_bus_in_alerts() there, and this module's own use below.
# Re-exported under the old private name; nothing else about the rule
# changed.
_mentions_replacement_bus = config.mentions_replacement_bus


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


def _delay_basis(r):
    """Explains what a row's own delay number actually rests on --
    requested by the user 2026-07-20 after raising a direct concern that
    some "eligible" trips might not have a real delay behind them at all.
    A data audit against the live payload confirmed the concern was
    warranted: of 843 eligible trips, only 20% had a genuinely confirmed
    final-arrival delay; the rest split across a stale unconfirmed
    prediction (36%), a second-source Trafikverket confirmation (22%,
    trustworthy but independent), an intermediate-stop-only fallback with
    no final-stop observation at all (11% -- "a station was passed late",
    not necessarily the train itself at its destination), or Trafikverket
    as the sole, uncorroborated source (10%). Every eligible/bus_replaced
    row now carries this explicitly rather than a single generic "approx."
    label, so the UI can say exactly which kind of evidence backs the
    number. Order matters -- checked most-authoritative-exception first:
    singleSourceOnly and finalConfirmedByTrafikverket are about WHICH
    source produced the number, checked before finalDelayMin's own
    presence/confirmation state."""
    if r.get("singleSourceOnly"):
        return "trafikverket_only"
    if r.get("finalConfirmedByTrafikverket"):
        return "final_confirmed_via_trafikverket"
    if r.get("finalDelayMin") is None:
        return "max_delay_fallback"
    if r.get("finalStopUnconfirmed"):
        return "final_stop_prediction_unconfirmed"
    return "final_arrival_confirmed"


def compute_compensation(rows):
    purchased_at = config.sommarbiljett_purchased_at()
    today = datetime.now(config.LOCAL_TZ).date()
    out = []
    low_value_skipped = 0
    for r in rows:
        if _trip_earliest_time(r) < purchased_at:
            continue  # trip happened before this ticket was purchased — never eligible, never shown

        # Confirmed directly by Skånetrafiken support, 2026-07-09 (see
        # config.SKANETRAFIKEN_REGISTRATION_LAG_DAYS): their own system can
        # take 1-2 days to fully register a trip's delay, and a claim filed
        # before that can be auto-rejected against a stale, too-low number
        # even when the true delay clears the threshold. Flagged here, not
        # silently -- carried through to every calc branch below via
        # dict(r, ...).
        trip_date = datetime.strptime(r["date"], "%Y%m%d").date()
        r = dict(r, recentTrip=(today - trip_date).days < config.SKANETRAFIKEN_REGISTRATION_LAG_DAYS)

        if r["status"] == "CANCELLED_TRIP":
            out.append(dict(r, calc="cancelled", delayUsedMin=None, delayApprox=False))
            continue

        if _mentions_replacement_bus(r.get("reason")):
            # Not "eligible" and not "cancelled" -- a distinct category so
            # the UI can say exactly why this one isn't claimable, rather
            # than silently dropping it (this project's own "no silent
            # caps" principle). Still carries whatever delay figure exists,
            # for visibility, but never a computed deduction amount.
            approx = r["finalDelayMin"] is None or bool(r.get("finalStopUnconfirmed"))
            delay_min = r["finalDelayMin"] if r["finalDelayMin"] is not None else r["maxDelayMin"]
            out.append(dict(r, calc="bus_replaced", delayUsedMin=delay_min, delayApprox=approx, delayBasis=_delay_basis(r)))
            continue

        delay_min = r["finalDelayMin"]
        # delayApprox also covers finalStopUnconfirmed -- found by code
        # review 2026-07-09 on a real journey (Öresundståg 20154): the
        # final stop WAS captured, but only as a live prediction taken
        # while the trip was still ~50 minutes from actually arriving,
        # captured once and never updated (see build_dashboard.py's own
        # note on how this is detected). That's not a confirmed number any
        # more than "final stop never captured at all" is -- both get the
        # same treatment: shown, flagged "approx.", never auto-recommended
        # (ruleFullyApplies() in claims_template.html already gates on
        # !delayApprox).
        approx = bool(r.get("finalStopUnconfirmed"))
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

        # Requested by the user 2026-07-20: a claim worth less than this
        # isn't worth the effort of filing, so don't even list it. Checked
        # against the best-case amount across both payout paths (voucher
        # price-deduction, or mileage reimbursement) -- the same
        # max(deductionVoucher, carCash) metric claims_template.html's own
        # legValue()/chain-scoring already uses, so "best possible amount"
        # means the same thing everywhere on this project.
        if max(deduction_voucher, car_cash or 0) < config.MIN_CLAIM_VALUE_SEK:
            low_value_skipped += 1
            continue

        out.append(dict(
            r,
            calc="eligible",
            delayUsedMin=delay_min,
            delayApprox=approx,
            delayBasis=_delay_basis(r),
            deductionPct=int(round(pct * 100)),
            deductionCash=deduction_cash,
            deductionVoucher=deduction_voucher,
            carCash=car_cash,
            carVoucher=car_cash,
        ))
    if low_value_skipped:
        print("compute_compensation: %d otherwise-eligible trip(s) skipped -- best-case amount under %d kr" % (
            low_value_skipped, config.MIN_CLAIM_VALUE_SEK))
    return out


def render(out_path, comp_rows, start_date, end_date):
    """Write compensation HTML from rows the caller has already fetched and
    run through compute_compensation(). Separated from main() (2026-08-06)
    so build_all.py can render every page from one shared query pass -- see
    build_all.py's own module docstring."""
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

    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    eligible = sum(1 for r in comp_rows if r["calc"] == "eligible")
    cancelled = sum(1 for r in comp_rows if r["calc"] == "cancelled")
    bus_replaced = sum(1 for r in comp_rows if r["calc"] == "bus_replaced")
    print("Compensation page written to %s (%d eligible trips, %d cancelled trips listed but excluded, %d bus-replaced trips listed but excluded, window %s..%s)" % (
        out_path, eligible, cancelled, bus_replaced, start_date, end_date))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=os.path.join(config.REPO_ROOT, "compensation.html"))
    args = parser.parse_args()

    start_date, end_date = config.claim_window()

    conn = db.connect()
    cur = conn.cursor()
    try:
        rows = fetch_detail_rows(cur, start_date, end_date, None)
        rows, _tv_stats = merge_trafikverket(rows, cur, start_date, end_date)
    finally:
        cur.close()
        conn.close()

    render(args.out, compute_compensation(rows), start_date, end_date)


if __name__ == "__main__":
    main()
