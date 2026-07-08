"""Merges Trafikverket's TrainAnnouncement data (src/scan_trafikverket.py)
into the row shape build_dashboard.fetch_detail_rows() already produces, for
build_compensation.py and build_claims.py to consume unchanged.

**The hard rule this module exists to enforce** (see
docs/TRAFIKVERKET_INTEGRATION.md Question #3): Trafikverket's own data must
NEVER override an existing GTFS-RT verdict. Confirmed directly, 2026-07-08 --
train 1206's Kristianstad C arrival showed `Canceled: true` in Trafikverket's
own system while this project's GTFS-RT `delays` table AND Skånetrafiken's
own customer app both independently confirmed the train actually arrived,
delayed. Two agreeing sources beat one outlier.

Two, and only two, things this module does:
1. **Enrich** trips GTFS-RT already has data for, with Trafikverket's
   structured `Deviation` reason text when this project's own alert-matching
   (build_dashboard.best_reason) came up empty. Never touches delay/status.
2. **Gap-fill** trips GTFS-RT has ZERO data for at all (the ~95% coverage
   hole documented in ARCHITECTURE.md) — but ONLY when Trafikverket itself
   gives an unambiguous, actually-recorded arrival time at the trip's final
   stop. A `Canceled: true` with no recorded arrival/estimate at all (the
   exact pattern that turned out to be wrong for train 1206) is deliberately
   NOT enough to manufacture a claim from -- skipped rather than guessed.
   Every gap-filled row is tagged `singleSourceOnly: true`, which
   claims_template.html's `ruleFullyApplies()` treats the same as an
   unconfirmed approximation: shown, never auto-recommended.
"""

import sqlite3

import config
from scan import load_trip_meta


def _load_static_trip_number_index():
    """trip_number (str) -> list of (trip_id, meta) from the static index,
    the same trip_meta scan.py already builds -- reused here rather than
    re-deriving it, so this module's notion of a trip's route/destination/
    distance/sommarticket_valid always matches what scan.py itself uses."""
    conn = sqlite3.connect(config.STATIC_INDEX_PATH)
    try:
        trip_meta, _stops = load_trip_meta(conn)
    finally:
        conn.close()
    index = {}
    for trip_id, meta in trip_meta.items():
        if meta.get("trip_number"):
            index.setdefault(str(meta["trip_number"]), []).append((trip_id, meta))
    return index


def _load_static_stop_names():
    conn = sqlite3.connect(config.STATIC_INDEX_PATH)
    try:
        return dict(conn.execute("SELECT stop_id, stop_name FROM stops"))
    finally:
        conn.close()


def _load_location_signature_map(cur):
    """location_signature -> stop_id, and the reverse -- both directions
    needed (forward to look up a train's stop by signature, reverse to find
    which signature corresponds to a GTFS stop_id we already know from
    trip_meta)."""
    cur.execute("SELECT location_signature, stop_id FROM location_signature_map")
    rows = cur.fetchall()
    sig_to_stop = dict(rows)
    stop_to_sig = {stop_id: sig for sig, stop_id in rows}
    return sig_to_stop, stop_to_sig


def _existing_gtfs_keys(cur, start_date, end_date):
    """(trip_number, trip_start_date) pairs GTFS-RT already has SOME data
    for -- delayed or cancelled -- within the window. Trafikverket is only
    ever consulted for keys NOT in this set."""
    cur.execute(
        """SELECT DISTINCT trip_number, trip_start_date FROM delays
           WHERE trip_number IS NOT NULL AND trip_start_date BETWEEN %s AND %s
           UNION
           SELECT DISTINCT trip_number, trip_start_date FROM trip_cancellations
           WHERE trip_number IS NOT NULL AND trip_start_date BETWEEN %s AND %s""",
        (start_date, end_date, start_date, end_date),
    )
    return {(trip_number, d) for trip_number, d in cur.fetchall()}


def _fetch_announcement_groups(cur, start_date, end_date):
    """(advertised_train_number, traffic_date) -> list of raw announcement
    rows (as dicts) for that physical trip."""
    cur.execute(
        """SELECT advertised_train_number, traffic_date, location_signature, activity_type,
                  advertised_time_at_location, estimated_time_at_location, time_at_location,
                  canceled, deviation_text
           FROM train_announcements
           WHERE traffic_date BETWEEN %s AND %s""",
        (start_date, end_date),
    )
    groups = {}
    for (train_number, traffic_date, sig, activity, advertised_at, estimated_at, actual_at,
         canceled, deviation_text) in cur.fetchall():
        groups.setdefault((train_number, traffic_date), []).append({
            "location_signature": sig, "activity_type": activity,
            "advertised_at": advertised_at, "estimated_at": estimated_at, "actual_at": actual_at,
            "canceled": canceled, "deviation_text": deviation_text,
        })
    return groups


def _delay_min(advertised_at, estimated_at, actual_at):
    """Minutes late, using the actually-recorded time when we have one,
    falling back to the estimate. Returns None if neither exists -- exactly
    the ambiguous "Canceled, no time at all" pattern this module refuses to
    build a claim from."""
    at = actual_at or estimated_at
    if at is None or advertised_at is None:
        return None
    return round((at - advertised_at).total_seconds() / 60, 1)


def _fmt_time(dt):
    if dt is None:
        return None
    return dt.astimezone(config.LOCAL_TZ).strftime("%H:%M")


def build_gapfill_rows(cur, start_date, end_date):
    """Rows for trips GTFS-RT never saw at all, built ONLY where Trafikverket
    gives an unambiguous real delay at the trip's own final stop. Returns
    (rows, skipped_count) -- skipped_count is trips that matched a known
    Skåne train number but couldn't be confidently resolved (no location
    crosswalk hit, or the ambiguous Canceled-with-no-time pattern), logged
    rather than silently dropped so the gap this module leaves is visible."""
    trip_number_index = _load_static_trip_number_index()
    stop_names = _load_static_stop_names()
    _sig_to_stop, stop_to_sig = _load_location_signature_map(cur)
    existing_keys = _existing_gtfs_keys(cur, start_date, end_date)
    groups = _fetch_announcement_groups(cur, start_date, end_date)

    rows = []
    skipped = 0
    for (train_number, traffic_date), announcements in groups.items():
        if (train_number, traffic_date) in existing_keys:
            continue  # GTFS-RT already has this trip -- enrichment territory, not gap-fill

        candidates = trip_number_index.get(train_number)
        if not candidates:
            continue  # not a train number this project's static schedule knows -- likely an unrelated national train, see Question #3

        by_sig = {}
        for a in announcements:
            by_sig.setdefault(a["location_signature"], []).append(a)

        row = None
        for trip_id, meta in candidates:
            if not meta.get("sommarticket_valid"):
                continue  # same scope restriction fetch_detail_rows() applies -- see COMPENSATION_RULES.md
            origin_sig = stop_to_sig.get(meta.get("origin_stop_id"))
            dest_sig = stop_to_sig.get(meta.get("destination_stop_id"))
            if dest_sig is None or dest_sig not in by_sig:
                continue  # can't confirm this specific trip_id's final stop without the crosswalk covering it

            dest_arrival = next((a for a in by_sig[dest_sig] if a["activity_type"] == "Ankomst"), None)
            if dest_arrival is None:
                continue
            final_delay = _delay_min(dest_arrival["advertised_at"], dest_arrival["estimated_at"], dest_arrival["actual_at"])
            if final_delay is None:
                # The exact ambiguous pattern found for train 1206: Canceled
                # with no recorded time at all. Not enough to claim on.
                skipped += 1
                continue

            origin_departure = None
            if origin_sig and origin_sig in by_sig:
                origin_departure = next((a for a in by_sig[origin_sig] if a["activity_type"] == "Avgang"), None)
            origin_delay = (
                _delay_min(origin_departure["advertised_at"], origin_departure["estimated_at"], origin_departure["actual_at"])
                if origin_departure else None
            )

            stops = [{
                "seq": 1, "stopId": meta.get("origin_stop_id"),
                "name": stop_names.get(meta.get("origin_stop_id")), "final": False, "relationship": "SCHEDULED",
                "delayMin": origin_delay,
                "schedTime": _fmt_time(origin_departure["advertised_at"]) if origin_departure else None,
                "actTime": _fmt_time(origin_departure["actual_at"] or origin_departure["estimated_at"]) if origin_departure else None,
                "schedTimeIso": origin_departure["advertised_at"].isoformat() if origin_departure else None,
                "actTimeIso": (origin_departure["actual_at"] or origin_departure["estimated_at"]).isoformat()
                    if origin_departure and (origin_departure["actual_at"] or origin_departure["estimated_at"]) else None,
            }, {
                "seq": meta.get("final_stop_sequence"), "stopId": meta.get("destination_stop_id"),
                "name": meta.get("destination_stop_name") or stop_names.get(meta.get("destination_stop_id")),
                "final": True, "relationship": "SCHEDULED",
                "delayMin": final_delay,
                "schedTime": _fmt_time(dest_arrival["advertised_at"]),
                "actTime": _fmt_time(dest_arrival["actual_at"] or dest_arrival["estimated_at"]),
                "schedTimeIso": dest_arrival["advertised_at"].isoformat(),
                "actTimeIso": (dest_arrival["actual_at"] or dest_arrival["estimated_at"]).isoformat(),
            }]

            deviations = sorted(set(
                a["deviation_text"] for a in announcements if a["deviation_text"]
            ))
            row = {
                "trip": trip_id, "date": traffic_date.strftime("%Y%m%d"), "line": meta["route_short_name"],
                "vehicleType": meta.get("vehicle_type") or "UNKNOWN", "tripNumber": train_number,
                "dest": meta.get("destination_stop_name"), "distanceKm": meta.get("distance_km"),
                "status": "DELAYED" if final_delay > 0.5 else ("EARLY" if final_delay < -0.5 else "ON_TIME"),
                "finalDelayMin": final_delay,
                "maxDelayMin": max(final_delay, origin_delay) if origin_delay is not None else final_delay,
                "reason": "Trafikverket: " + "; ".join(deviations) if deviations else None,
                "stops": stops,
                "firstSeen": dest_arrival["advertised_at"].isoformat(),
                "lastSeen": (dest_arrival["actual_at"] or dest_arrival["estimated_at"] or dest_arrival["advertised_at"]).isoformat(),
                "polls": len(announcements),
                "singleSourceOnly": True,
            }
            break

        if row:
            rows.append(row)
        else:
            skipped += 1

    return rows, skipped


def enrich_reasons(rows, cur, start_date, end_date):
    """Fills in `reason` from Trafikverket's Deviation text for rows that
    already have GTFS-RT data but no reason of their own (best_reason() in
    build_dashboard.py came up empty). Never touches delay/status/calc --
    text only."""
    groups = _fetch_announcement_groups(cur, start_date, end_date)
    by_key = {}
    for (train_number, traffic_date), announcements in groups.items():
        deviations = sorted(set(a["deviation_text"] for a in announcements if a["deviation_text"]))
        if deviations:
            by_key[(train_number, traffic_date.strftime("%Y%m%d"))] = "; ".join(deviations)

    for r in rows:
        if r.get("reason") or not r.get("tripNumber"):
            continue
        text = by_key.get((r["tripNumber"], r["date"]))
        if text:
            r["reason"] = "Trafikverket: " + text
    return rows


def merge_trafikverket(rows, cur, start_date, end_date):
    """Top-level entry point for build_compensation.py / build_claims.py.
    Degrades gracefully (returns `rows` unchanged) on ANY failure -- unlike
    scan_trafikverket.py (which has its own `continue-on-error` step in
    scan.yml), build_compensation.py/build_claims.py are NOT
    continue-on-error in the workflow: a raised exception here would take
    down claims.html/compensation.html generation entirely for a still-new,
    less-tested integration that's explicitly optional. Deliberately a
    broad catch (not just psycopg2.Error/sqlite3.Error) for that reason --
    a bug in this module's own logic should be visible in Action logs, not
    invisible, but it must never be fatal to the page build. See
    docs/TRAFIKVERKET_INTEGRATION.md."""
    try:
        rows = enrich_reasons(rows, cur, start_date, end_date)
        gapfill_rows, skipped = build_gapfill_rows(cur, start_date, end_date)
    except Exception as exc:  # noqa: BLE001 -- intentional, see docstring
        import traceback
        traceback.print_exc()
        print("Trafikverket merge skipped (%s): %s" % (type(exc).__name__, exc))
        return rows
    if gapfill_rows or skipped:
        print("Trafikverket gap-fill: %d trip(s) added (GTFS-RT had zero data), %d skipped (ambiguous or unmatched)" % (
            len(gapfill_rows), skipped))
    return rows + gapfill_rows
