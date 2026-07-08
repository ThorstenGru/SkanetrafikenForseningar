"""Second, independent rail-delay source: Trafikverket's own TrainAnnouncement
feed (api.trafikinfo.trafikverket.se), alongside the existing Trafiklab
GTFS-RT scanner (scan.py).

Why this exists: Trafiklab's GTFS-RT TripUpdates only reports live
predictions for ~5% of scheduled trips (see docs/ARCHITECTURE.md's coverage
section) — Skånetrafiken's onboard AVL equipment apparently isn't fitted (or
isn't reporting) on most vehicles. Trafikverket, as the track infrastructure
owner, runs its own track-side train-describer system independent of that —
it's the source their own "Tågläget" reporting is built on, and it covers
essentially all train movement nationally. Confirmed 2026-07-08 against this
project's own Supabase data: two departures the rider saw flagged in
Skånetrafiken's own app had zero rows anywhere in `delays` or
`trip_cancellations` — the GTFS-RT feed never had them.

**STATUS: unverified skeleton.** Written from Trafikverket's publicly
documented request/response shape (XML/JSON query language, changeid-based
incremental polling) without a live API key to test against — registration
lives at api.trafikinfo.trafikverket.se, a separate product from Trafiklab.
See docs/TRAFIKVERKET_INTEGRATION.md for the full research writeup and the
open questions flagged inline below with "VERIFY:" — resolve all of those
against a real response before this runs in scan.yml.

Scope: rail only. Does not, and structurally cannot, cover SkåneExpressen or
any other bus service — Trafikverket only tracks vehicles on their own rail
network.
"""

import json
from datetime import datetime, timedelta, timezone

import requests

import config
import db


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def build_query(changeid, location_signatures):
    """Trafikverket's query language is XML-in-a-request-body regardless of
    whether the response comes back as XML or JSON (selected by the URL's
    own file extension — config.TRAFIKVERKET_API_URL ends in .json).

    VERIFY: schemaversion "1.9" is the latest confirmed via search
    (2026-07-08) but Trafikverket versions this independently of when this
    file was written — check the current version at
    api.trafikinfo.trafikverket.se/API/Model before first real run.

    VERIFY: exact field names below (AdvertisedTimeAtLocation,
    EstimatedTimeAtLocation, TimeAtLocation, TrackAtLocation, Deviation,
    ModifiedTime, Canceled, ActivityType, LocationSignature,
    AdvertisedTrainNumber, Operator) are the commonly-cited ones from public
    writeups, not confirmed against Trafikverket's own schema docs (those
    require a registered account to view in full) — cross-check the first
    real response's actual keys against this list.
    """
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=config.TRAFIKVERKET_ANNOUNCEMENT_LOOKBACK_MIN)
    window_end = now + timedelta(hours=config.TRAFIKVERKET_ANNOUNCEMENT_LOOKAHEAD_HOURS)

    # VERIFY: combining a changeid with a fresh time-window filter on the
    # same request is untested — Trafikverket's changeid model is meant to
    # replace re-filtering (it returns exactly what changed since last time,
    # regardless of the original filter's window), so the AdvertisedTimeAt
    # Location bounds below may only be correct/needed on the FIRST request
    # (changeid absent). If real traffic shows changeid alone drifting the
    # window forward incorrectly, drop the time filter once changeid is set.
    location_filter = "".join(
        '<EQ name="LocationSignature" value="%s" />' % sig for sig in location_signatures
    )
    if not location_signatures:
        # First-ever run, before location_signature_map has been populated:
        # cannot filter by station yet. Falls back to a pure time-window
        # query so there's at least something to bootstrap the crosswalk
        # from -- expect this to be a large, noisy result; narrow to
        # location_signatures as soon as the crosswalk exists.
        location_block = ""
    else:
        location_block = "<OR>%s</OR>" % location_filter

    changeid_attr = ' changeid="%s"' % changeid if changeid else ""

    return """<REQUEST>
  <LOGIN authenticationkey="%s" />
  <QUERY objecttype="TrainAnnouncement" schemaversion="1.9"%s includedeletedobjects="true">
    <FILTER>
      <AND>
        <GTE name="AdvertisedTimeAtLocation" value="%s" />
        <LTE name="AdvertisedTimeAtLocation" value="%s" />
        %s
      </AND>
    </FILTER>
  </QUERY>
</REQUEST>""" % (
        config.trafikverket_key(),
        changeid_attr,
        _iso(window_start),
        _iso(window_end),
        location_block,
    )


def fetch(changeid, location_signatures):
    query = build_query(changeid, location_signatures)
    resp = requests.post(
        config.TRAFIKVERKET_API_URL,
        data=query,
        headers={"Content-Type": "text/xml", "Accept": "application/json"},
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError("Trafikverket TrainAnnouncement failed: HTTP %d: %s" % (resp.status_code, resp.text[:500]))
    payload = resp.json()
    # VERIFY: envelope shape (RESPONSE.RESULT[0].TrainAnnouncement /
    # RESPONSE.RESULT[0].INFO.LASTCHANGEID) is the commonly-documented one
    # for this API family but not confirmed against a live response here.
    result = payload["RESPONSE"]["RESULT"][0]
    announcements = result.get("TrainAnnouncement", [])
    next_changeid = result.get("INFO", {}).get("LASTCHANGEID", changeid)
    return announcements, next_changeid


def _parse_dt(value):
    if not value:
        return None
    # Trafikverket timestamps are ISO 8601 with offset (VERIFY on first real
    # response) -- fromisoformat handles that directly in Python 3.11+.
    return datetime.fromisoformat(value)


def to_row(announcement, now):
    """Maps one raw TrainAnnouncement object to TRAIN_ANNOUNCEMENT_COLUMNS.
    Returns None for anything unparseable, or not publicly advertised,
    rather than raising -- a malformed single announcement shouldn't abort
    the whole poll.

    CONFIRMED against a real response 2026-07-08 (see
    docs/TRAFIKVERKET_INTEGRATION.md -- this replaced several guessed field
    names from the initial unverified skeleton):
    - The train-number field is `AdvertisedTrainIdent`, NOT
      `AdvertisedTrainNumber` (that name doesn't exist in the real schema).
    - `Operator` doesn't reliably appear; `TrainOwner` does. Reading both
      with `TrainOwner` preferred, since we don't yet know if they're ever
      both present with different values.
    - Not every row carries `AdvertisedTimeAtLocation` -- rows with
      `Advertised: false` (internal/technical stops not shown to
      passengers) can lack it entirely. Filtered out below rather than
      falling back to `TimeAtLocation` for the date, since an unadvertised
      stop isn't something a rider experiences or could claim against.
    - `Deviation` CONFIRMED 2026-07-08 (train 1206's own cancelled
      Kristianstad C arrival carried two): a list of `{"Code": ...,
      "Description": ...}` objects, e.g. `{"Code": "ANA027", "Description":
      "Inställt"}`. Joined below on `Description` -- the human-readable
      Swedish text -- since `Code` alone isn't useful for display and this
      project doesn't have (or need) a lookup table for Trafikverket's own
      deviation-code catalogue.
    - `Canceled: true` on one specific station's announcement does NOT
      reliably mean the train never physically arrived there -- confirmed
      directly against this exact train (1206, 2026-07-08): Trafikverket's
      own record showed `Canceled: true` + `Deviation: ["Inställt", "Nästa
      avgång"]` for its Kristianstad C arrival, while this project's own
      GTFS-RT `delays` table AND Skånetrafiken's own customer app both
      independently confirmed the train actually arrived, delayed by
      +32.9 min. See docs/TRAFIKVERKET_INTEGRATION.md Question #3 for the
      full writeup and the resulting hard rule: `canceled` from this table
      must never override an existing GTFS-RT verdict in
      `delays`/`trip_cancellations` -- only fill in when GTFS-RT has
      nothing at all for the trip, and even then, surface for manual
      confirmation rather than auto-including in a claim.
    """
    if not announcement.get("Advertised", False):
        return None
    try:
        advertised_at = _parse_dt(announcement["AdvertisedTimeAtLocation"])
        deviations = announcement.get("Deviation") or []
        return {
            "advertised_train_number": str(announcement["AdvertisedTrainIdent"]),
            "traffic_date": advertised_at.astimezone(config.LOCAL_TZ).date(),
            "location_signature": announcement["LocationSignature"],
            "activity_type": announcement["ActivityType"],
            "advertised_time_at_location": advertised_at,
            "estimated_time_at_location": _parse_dt(announcement.get("EstimatedTimeAtLocation")),
            "time_at_location": _parse_dt(announcement.get("TimeAtLocation")),
            "canceled": bool(announcement.get("Canceled", False)),
            "track_at_location": announcement.get("TrackAtLocation"),
            "deviation_text": "; ".join(d.get("Description", "") for d in deviations if d.get("Description")) or None,
            "operator": announcement.get("TrainOwner") or announcement.get("Operator"),
            "modified_time": _parse_dt(announcement.get("ModifiedTime")) or now,
        }
    except (KeyError, ValueError) as exc:
        print("Skipping malformed TrainAnnouncement (%s): %r" % (exc, announcement))
        return None


def load_location_signatures(cur):
    cur.execute("SELECT location_signature FROM location_signature_map")
    return [r[0] for r in cur.fetchall()]


def main():
    now = datetime.now(timezone.utc)
    conn = db.connect()
    try:
        cur = conn.cursor()
        changeid = db.get_trafikverket_changeid(cur)
        location_signatures = load_location_signatures(cur)
        if not location_signatures:
            print(
                "WARNING: location_signature_map is empty -- querying without a "
                "station filter (see module docstring). Populate the crosswalk "
                "before running this on a schedule, or every poll will pull "
                "Trafikverket's entire national train-announcement volume."
            )

        raw_announcements, next_changeid = fetch(changeid, location_signatures)
        rows = [r for r in (to_row(a, now) for a in raw_announcements) if r is not None]

        inserted = db.upsert_train_announcements_batch(cur, rows, now)
        db.set_trafikverket_changeid(cur, next_changeid, now)
        conn.commit()
        print("Trafikverket scan: %d announcements seen, %d new" % (len(rows), inserted))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
