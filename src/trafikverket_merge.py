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

Three things this module does:
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
3. **Confirm stale finals** — `confirm_stale_finals()`, added 2026-07-09
   after the Öresundståg 20154 case (see build_dashboard.py's own note on
   `final_stop_unconfirmed`): GTFS-RT tracked that trip, but our last poll
   landed ~50 min before its own recorded "actual" arrival time, so the
   number we had was a live mid-journey prediction (+23.6 min), never
   confirmed after the fact. Skånetrafiken's own app later showed the real
   outcome: +3 min. This does NOT violate the hard rule below --
   `finalStopUnconfirmed=True` means GTFS-RT itself never reached a verdict
   for that trip, so there is no existing verdict to override. Trafikverket
   is only trusted here when it has a REAL post-arrival observation
   (`actual_at`, not an estimate) recorded strictly AFTER our own last poll
   -- i.e. genuinely new information from a source that kept watching the
   train after we stopped, not a competing guess.
"""

import sqlite3
from datetime import datetime

import config
from build_dashboard import _is_delay_irrelevant_alert
from scan import load_trip_meta


def _load_static_data():
    """(trip_number_index, stop_names) from a single pass over the static
    index -- trip_number (str) -> list of (trip_id, meta), and stop_id ->
    stop_name. Previously two separate functions each opening their own
    sqlite3 connection to the same file; load_trip_meta() already returns
    the stop-name dict as its second value, so the second connection was
    pure duplicate I/O for data already in hand (found by code review
    2026-07-08)."""
    conn = sqlite3.connect(config.STATIC_INDEX_PATH)
    try:
        trip_meta, stops = load_trip_meta(conn)
    finally:
        conn.close()
    index = {}
    for trip_id, meta in trip_meta.items():
        if meta.get("trip_number"):
            index.setdefault(str(meta["trip_number"]), []).append((trip_id, meta))
    return index, stops


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


def _stop_name_to_sig(stop_to_sig, stop_names):
    """stop_name -> location_signature, derived from stop_to_sig (the exact
    stop_id crosswalk, built by matching Trafikverket's own TrainStation
    coordinates against this project's GTFS stops within 500m -- see
    build_location_signature_map.py). GTFS static data commonly has several
    stop_id variants for one physical station (different boarding
    platforms/directions), and the crosswalk build only matched ONE variant
    per station -- so a trip_meta entry whose own origin/destination_stop_id
    happens to be a different variant of that same station is invisible to
    a lookup keyed on stop_id alone. Found 2026-07-09 investigating why
    Öresundståg 20154 (Helsingborg C -> Göteborg C) wasn't picked up by
    confirm_stale_finals: its destination_stop_id had no crosswalk row, but
    a different Göteborg C stop_id variant did. Same physical station, so
    matching by name (not id) is the correct fallback, not a loosening of
    the match's confidence."""
    name_to_sig = {}
    for stop_id, sig in stop_to_sig.items():
        name = stop_names.get(stop_id)
        if name and name not in name_to_sig:
            name_to_sig[name] = sig
    return name_to_sig


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
    rows (as dicts) for that physical trip. Called once per
    merge_trafikverket() invocation and shared between enrich_reasons() and
    build_gapfill_rows() -- both used to independently re-run this exact
    query, doubling the round-trip for no reason (found by code review
    2026-07-08).

    Does NOT select the `canceled` column -- fetched in an earlier version
    but never actually read by either caller (the ambiguous-cancellation
    guard is done purely via _delay_min() returning None when there's no
    actual_at/estimated_at, not by checking this flag directly). Leaving it
    out avoids both the unused-data smell and any temptation to read it
    naively elsewhere -- see this module's own docstring on why a lone
    Canceled=true is not reliable."""
    cur.execute(
        """SELECT advertised_train_number, traffic_date, location_signature, activity_type,
                  advertised_time_at_location, estimated_time_at_location, time_at_location,
                  deviation_text
           FROM train_announcements
           WHERE traffic_date BETWEEN %s AND %s""",
        (start_date, end_date),
    )
    groups = {}
    for (train_number, traffic_date, sig, activity, advertised_at, estimated_at, actual_at,
         deviation_text) in cur.fetchall():
        groups.setdefault((train_number, traffic_date), []).append({
            "location_signature": sig, "activity_type": activity,
            "advertised_at": advertised_at, "estimated_at": estimated_at, "actual_at": actual_at,
            "deviation_text": deviation_text,
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


def build_gapfill_rows(cur, start_date, end_date, trip_number_index, stop_names, stop_to_sig, name_to_sig, groups):
    """Rows for trips GTFS-RT never saw at all, built ONLY where Trafikverket
    gives an unambiguous real delay at the trip's own final stop. Returns
    (rows, skipped_count) -- skipped_count is trips that matched a known
    Skåne train number but couldn't be confidently resolved (no location
    crosswalk hit, or the ambiguous Canceled-with-no-time pattern), logged
    rather than silently dropped so the gap this module leaves is visible.

    trip_number_index/stop_names/stop_to_sig/groups are loaded once by the
    caller (merge_trafikverket) and passed in -- this used to reload all of
    them itself, duplicating enrich_reasons()'s identical `groups` query,
    confirm_stale_finals()'s identical location-signature-map query, and
    each of its own two static-index loads within a single merge call
    (found by code review 2026-07-08)."""
    existing_keys = _existing_gtfs_keys(cur, start_date, end_date)

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
            origin_sig = stop_to_sig.get(meta.get("origin_stop_id")) or name_to_sig.get(stop_names.get(meta.get("origin_stop_id")))
            dest_sig = stop_to_sig.get(meta.get("destination_stop_id")) or name_to_sig.get(meta.get("destination_stop_name"))
            if dest_sig is None or dest_sig not in by_sig:
                continue  # can't confirm this specific trip_id's final stop without the crosswalk covering it

            dest_arrival = next((a for a in by_sig[dest_sig] if a["activity_type"] == "Ankomst"), None)
            if dest_arrival is None:
                continue
            final_delay = _delay_min(dest_arrival["advertised_at"], dest_arrival["estimated_at"], dest_arrival["actual_at"])
            if final_delay is None:
                # The exact ambiguous pattern found for train 1206: Canceled
                # with no recorded time at all. Not enough to claim on --
                # counted once below (the group as a whole is skipped, not
                # counted here too, or a group with several candidates would
                # be double-counted for a single logical failure).
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
                # Thresholds must match build_dashboard.classify_trip()'s
                # >60s/<-60s exactly (i.e. >1.0/<-1.0 minutes here) -- found
                # by code review 2026-07-08 using >0.5/<-0.5, which gave a
                # GTFS-RT-sourced trip and a Trafikverket-sourced trip
                # different DELAYED/ON_TIME verdicts for the same delay
                # length purely because of which source happened to report it.
                "status": "DELAYED" if final_delay > 1.0 else ("EARLY" if final_delay < -1.0 else "ON_TIME"),
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


def enrich_reasons(rows, groups):
    """Fills in `reason` from Trafikverket's Deviation text for rows that
    already have GTFS-RT data but no reason of their own (best_reason() in
    build_dashboard.py came up empty). Never touches delay/status/calc --
    text only. `groups` is loaded once by the caller (merge_trafikverket)
    and shared with build_gapfill_rows() -- see its own docstring.

    Same _is_delay_irrelevant_alert() guard as best_reason() -- unlikely to
    ever match here (Trafikverket's own Deviation vocabulary is things like
    "Inställt"/"Buss ersätter"/"Spårändrat", not a Skånetrafiken-specific
    bike-capacity notice), but cheap to apply for the same reason: a reason
    unrelated to timing should never be shown as if it explains a delay."""
    by_key = {}
    for (train_number, traffic_date), announcements in groups.items():
        deviations = sorted(set(
            a["deviation_text"] for a in announcements
            if a["deviation_text"] and not _is_delay_irrelevant_alert(a["deviation_text"])
        ))
        if deviations:
            by_key[(train_number, traffic_date.strftime("%Y%m%d"))] = "; ".join(deviations)

    for r in rows:
        if r.get("reason") or not r.get("tripNumber"):
            continue
        text = by_key.get((r["tripNumber"], r["date"]))
        if text:
            r["reason"] = "Trafikverket: " + text
    return rows


def confirm_stale_finals(rows, trip_number_index, stop_names, stop_to_sig, name_to_sig, groups):
    """For rows whose final-stop delay is only an unconfirmed live
    prediction (`finalStopUnconfirmed=True` -- see build_dashboard.py:
    GTFS-RT's own last poll happened BEFORE the trip's recorded "actual"
    arrival, so the number on file was captured mid-journey), check whether
    Trafikverket independently recorded a REAL observation
    (`time_at_location`, not an estimate) at this exact trip's own final
    stop, strictly AFTER our last poll. If so, that's new information from
    a source that kept watching the train after we stopped -- not
    Trafikverket overriding an existing GTFS-RT verdict (there wasn't one
    yet), and not trusted on an estimate alone, which would carry the same
    "still just a prediction" problem this exists to fix.

    stop_to_sig is the exact stop_id crosswalk; name_to_sig is the
    same-station-name fallback (see _stop_name_to_sig()) for when the
    trip's own destination_stop_id is a different GTFS platform variant
    than the one the crosswalk happened to match.

    Returns (rows, confirmed_count). Mutates matching rows in place:
    finalDelayMin/maxDelayMin/status are corrected and
    finalStopUnconfirmed is cleared; finalConfirmedByTrafikverket=True is
    set so the UI can show this number came from a second source, not our
    own scanner catching up."""
    trip_id_to_meta = {tid: meta for cands in trip_number_index.values() for tid, meta in cands}
    confirmed = 0
    for r in rows:
        if not r.get("finalStopUnconfirmed") or not r.get("tripNumber"):
            continue
        meta = trip_id_to_meta.get(r["trip"])
        if not meta:
            continue
        dest_sig = stop_to_sig.get(meta.get("destination_stop_id")) or name_to_sig.get(
            meta.get("destination_stop_name") or stop_names.get(meta.get("destination_stop_id"))
        )
        if dest_sig is None:
            continue
        try:
            trip_date = datetime.strptime(r["date"], "%Y%m%d").date()
        except ValueError:
            continue
        announcements = groups.get((r["tripNumber"], trip_date))
        if not announcements:
            continue
        dest_arrival = next(
            (a for a in announcements
             if a["location_signature"] == dest_sig and a["activity_type"] == "Ankomst"),
            None,
        )
        # actual_at specifically -- an estimate would just be a second,
        # differently-timed prediction, not the post-arrival confirmation
        # this function exists to require.
        if dest_arrival is None or dest_arrival["actual_at"] is None:
            continue
        last_seen = datetime.fromisoformat(r["lastSeen"])
        if dest_arrival["actual_at"] <= last_seen:
            continue  # not a later observation than we already have -- no new information
        final_delay = _delay_min(
            dest_arrival["advertised_at"], dest_arrival["estimated_at"], dest_arrival["actual_at"]
        )
        if final_delay is None:
            continue
        r["finalDelayMin"] = final_delay
        r["maxDelayMin"] = max(r["maxDelayMin"], final_delay) if r["maxDelayMin"] is not None else final_delay
        r["finalStopUnconfirmed"] = False
        r["finalConfirmedByTrafikverket"] = True
        r["status"] = "DELAYED" if final_delay > 1.0 else ("EARLY" if final_delay < -1.0 else "ON_TIME")
        confirmed += 1
    return rows, confirmed


def merge_trafikverket(rows, cur, start_date, end_date):
    """Top-level entry point for build_compensation.py / build_claims.py /
    data_quality_check.py. Degrades gracefully (returns `rows` unchanged,
    stats all zero/None) on ANY failure -- unlike scan_trafikverket.py
    (which has its own `continue-on-error` step in scan.yml),
    build_compensation.py/build_claims.py are NOT continue-on-error in the
    workflow: a raised exception here would take down claims.html/
    compensation.html generation entirely for a still-new, less-tested
    integration that's explicitly optional. Deliberately a broad catch
    (not just psycopg2.Error/sqlite3.Error) for that reason -- a bug in
    this module's own logic should be visible in Action logs, not
    invisible, but it must never be fatal to the page build. See
    docs/TRAFIKVERKET_INTEGRATION.md.

    Returns (rows, stats) -- stats is {"confirmed", "gapfilled", "skipped"}
    (None values on failure). Added 2026-07-20 so data_quality_check.py can
    persist these same numbers (a queryable trail, not just a print() line
    in one Action run's own log) without duplicating this module's own
    logic -- see migration 018_data_quality_runs.sql."""
    try:
        trip_number_index, stop_names = _load_static_data()
        _sig_to_stop, stop_to_sig = _load_location_signature_map(cur)
        name_to_sig = _stop_name_to_sig(stop_to_sig, stop_names)
        groups = _fetch_announcement_groups(cur, start_date, end_date)
        rows = enrich_reasons(rows, groups)
        rows, confirmed = confirm_stale_finals(rows, trip_number_index, stop_names, stop_to_sig, name_to_sig, groups)
        gapfill_rows, skipped = build_gapfill_rows(
            cur, start_date, end_date, trip_number_index, stop_names, stop_to_sig, name_to_sig, groups
        )
    except Exception as exc:  # noqa: BLE001 -- intentional, see docstring
        import traceback
        traceback.print_exc()
        print("Trafikverket merge skipped (%s): %s" % (type(exc).__name__, exc))
        return rows, {"confirmed": None, "gapfilled": None, "skipped": None}
    if confirmed:
        print("Trafikverket confirmed %d previously-unconfirmed final-stop prediction(s) with a later post-arrival observation" % confirmed)
    if gapfill_rows or skipped:
        print("Trafikverket gap-fill: %d trip(s) added (GTFS-RT had zero data), %d skipped (ambiguous or unmatched)" % (
            len(gapfill_rows), skipped))
    return rows + gapfill_rows, {"confirmed": confirmed, "gapfilled": len(gapfill_rows), "skipped": skipped}
