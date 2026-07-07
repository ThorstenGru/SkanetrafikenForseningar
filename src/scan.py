"""Main entrypoint: refresh static index if stale, fetch TripUpdates +
ServiceAlerts from Trafiklab, and upsert everything into Postgres (Supabase).

Usage:
    python src/scan.py
"""

import os
import sqlite3
import sys
from datetime import date, datetime, timezone

import requests
from google.transit import gtfs_realtime_pb2

import config
import db
import static_index


def load_trip_meta(static_conn):
    routes = {}
    route_types = {}
    for rid, short, rt in static_conn.execute("SELECT route_id, short_name, route_type FROM routes"):
        routes[rid] = short
        route_types[rid] = rt
    stops = dict(static_conn.execute("SELECT stop_id, stop_name FROM stops").fetchall())
    trip_meta = {}
    for (trip_id, route_id, direction_id, trip_number, dest_stop_id, dest_stop_name,
         final_seq, distance_km, sommarticket_valid) in static_conn.execute(
        """SELECT trip_id, route_id, direction_id, trip_number, destination_stop_id,
                  destination_stop_name, final_stop_sequence, distance_km, sommarticket_valid
           FROM trip_meta"""
    ):
        trip_meta[trip_id] = {
            "route_id": route_id,
            "route_short_name": routes.get(route_id, route_id),
            "vehicle_type": config.route_type_label(route_types.get(route_id)),
            "trip_number": trip_number or None,
            "direction_id": direction_id,
            "destination_stop_name": dest_stop_name,
            "final_stop_sequence": final_seq,
            "distance_km": distance_km,
            "sommarticket_valid": bool(sommarticket_valid) if sommarticket_valid is not None else None,
        }
    return trip_meta, stops


def fetch_feed(url_tmpl, key, label):
    url = url_tmpl.format(op=config.OPERATOR, key=key)
    print("Fetching %s..." % label)
    resp = requests.get(url, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError("%s failed: HTTP %d: %s" % (label, resp.status_code, resp.text[:300]))
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(resp.content)
    return feed


def _epoch_to_dt(epoch):
    return datetime.fromtimestamp(epoch, tz=timezone.utc) if epoch is not None else None


def _parse_start_date(start_date_str, now):
    if not start_date_str:
        # Falls back to the scan's own reference instant, converted to
        # Europe/Stockholm -- not date.today(), which is UTC (and thus the
        # previous calendar date) for the last couple hours of every
        # Stockholm day on a GitHub Actions runner. See config.py's own
        # note on this exact class of bug.
        return now.astimezone(config.LOCAL_TZ).date()
    return date(int(start_date_str[0:4]), int(start_date_str[4:6]), int(start_date_str[6:8]))


def process_trip_updates(feed, trip_meta, stops, cur, now):
    seen_rows = []       # (trip_id, trip_start_date, route_short_name)
    cancellation_rows = []
    delay_rows = []

    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue
        tu = entity.trip_update
        trip_id = tu.trip.trip_id
        if not trip_id:
            # A handful of entities occasionally carry no trip_id at all
            # (unassigned-vehicle noise in the feed) — nothing meaningful to
            # key them on, and they'd collide with each other on insert.
            continue
        start_date = _parse_start_date(tu.trip.start_date, now)
        trip_sched_rel = config.TRIP_SCHEDULE_RELATIONSHIP_LABELS.get(tu.trip.schedule_relationship, str(tu.trip.schedule_relationship))

        meta = trip_meta.get(trip_id, {})
        route_id = meta.get("route_id") or tu.trip.route_id
        route_short_name = meta.get("route_short_name") or tu.trip.route_id or "unknown"
        vehicle_type = meta.get("vehicle_type", "UNKNOWN")
        trip_number = meta.get("trip_number")
        distance_km = meta.get("distance_km")
        sommarticket_valid = meta.get("sommarticket_valid")
        destination_stop_name = meta.get("destination_stop_name", "")
        direction_id = meta.get("direction_id")
        final_seq = meta.get("final_stop_sequence")

        # Every trip we see at all, regardless of delay — the presence log
        # that coverage_check.py diffs against the static schedule.
        seen_rows.append((trip_id, start_date, route_short_name))

        if tu.trip.schedule_relationship == 3:  # CANCELED (whole trip)
            cancellation_rows.append({
                "trip_id": trip_id, "trip_start_date": start_date, "route_id": route_id,
                "route_short_name": route_short_name, "vehicle_type": vehicle_type,
                "trip_number": trip_number, "distance_km": distance_km, "sommarticket_valid": sommarticket_valid,
                "destination_stop_name": destination_stop_name,
            })
            continue

        for stu in tu.stop_time_update:
            arrival_delay = stu.arrival.delay if stu.HasField("arrival") and stu.arrival.HasField("delay") else None
            departure_delay = stu.departure.delay if stu.HasField("departure") and stu.departure.HasField("delay") else None
            arrival_time = stu.arrival.time if stu.HasField("arrival") and stu.arrival.HasField("time") else None
            departure_time = stu.departure.time if stu.HasField("departure") and stu.departure.HasField("time") else None
            stop_sched_rel = config.SCHEDULE_RELATIONSHIP_LABELS.get(stu.schedule_relationship, str(stu.schedule_relationship))

            is_delay = (arrival_delay not in (None, 0)) or (departure_delay not in (None, 0))
            is_irregular = stu.schedule_relationship != 0  # not plain SCHEDULED (e.g. SKIPPED)
            if not is_delay and not is_irregular:
                continue

            scheduled_arrival = (arrival_time - arrival_delay) if (arrival_time is not None and arrival_delay is not None) else None
            scheduled_departure = (departure_time - departure_delay) if (departure_time is not None and departure_delay is not None) else None

            delay_rows.append({
                "trip_id": trip_id,
                "trip_start_date": start_date,
                "route_id": route_id,
                "route_short_name": route_short_name,
                "vehicle_type": vehicle_type,
                "trip_number": trip_number,
                "distance_km": distance_km,
                "sommarticket_valid": sommarticket_valid,
                "direction_id": direction_id,
                "destination_stop_name": destination_stop_name,
                "stop_id": stu.stop_id,
                "stop_name": stops.get(stu.stop_id, ""),
                "stop_sequence": stu.stop_sequence,
                "is_final_stop": bool(final_seq is not None and stu.stop_sequence == final_seq),
                "stop_schedule_relationship": stop_sched_rel,
                "trip_schedule_relationship": trip_sched_rel,
                "arrival_delay_sec": arrival_delay,
                "departure_delay_sec": departure_delay,
                "arrival_time": _epoch_to_dt(arrival_time),
                "departure_time": _epoch_to_dt(departure_time),
                "scheduled_arrival": _epoch_to_dt(scheduled_arrival),
                "scheduled_departure": _epoch_to_dt(scheduled_departure),
            })

    # Safety net: a single execute_values() upsert can't touch the same row
    # twice, so defensively collapse any remaining duplicate keys (keeping
    # the last occurrence) before batching. In practice this should be a
    # no-op once malformed empty-trip_id entities are filtered above.
    seen_rows = list({(t, d): (t, d, r) for t, d, r in seen_rows}.values())
    cancellation_rows = list({(r["trip_id"], r["trip_start_date"]): r for r in cancellation_rows}.values())
    delay_rows = list({(r["trip_id"], r["trip_start_date"], r["stop_sequence"]): r for r in delay_rows}.values())

    db.upsert_seen_trips_batch(cur, seen_rows, now)
    cancellations_new = db.upsert_cancellations_batch(cur, cancellation_rows, now)
    delays_new = db.upsert_delays_batch(cur, delay_rows, now)

    return len(delay_rows), delays_new, len(cancellation_rows)


def process_alerts(feed, cur, now):
    alerts = []
    for entity in feed.entity:
        if not entity.HasField("alert"):
            continue
        a = entity.alert
        header = a.header_text.translation[0].text if a.header_text.translation else ""
        desc = a.description_text.translation[0].text if a.description_text.translation else ""
        period_start = a.active_period[0].start if a.active_period and a.active_period[0].HasField("start") else None
        period_end = a.active_period[0].end if a.active_period and a.active_period[0].HasField("end") else None

        fields = {
            "cause_code": a.cause,
            "cause_label": config.CAUSE_LABELS.get(a.cause, str(a.cause)),
            "effect_code": a.effect,
            "effect_label": config.EFFECT_LABELS.get(a.effect, str(a.effect)),
            "header_text": header,
            "description_text": desc,
            "active_period_start": _epoch_to_dt(period_start),
            "active_period_end": _epoch_to_dt(period_end),
        }
        entities = [
            {"route_id": ie.route_id or None, "trip_id": ie.trip.trip_id or None, "stop_id": ie.stop_id or None}
            for ie in a.informed_entity
        ]
        alerts.append((entity.id, fields, entities))

    alerts = list({uid: (uid, f, e) for uid, f, e in alerts}.values())  # defensive, see process_trip_updates

    alerts_new = db.upsert_alerts_batch(cur, alerts, now)
    return len(alerts), alerts_new


def main():
    now = datetime.now(timezone.utc)
    if os.environ.get("FORCE_STATIC_REFRESH") == "true":
        static_refreshed = static_index.rebuild_index()
    else:
        static_refreshed = static_index.ensure_index()

    static_conn = sqlite3.connect(config.STATIC_INDEX_PATH)
    trip_meta, stops = load_trip_meta(static_conn)
    static_conn.close()

    conn = db.connect()
    cur = conn.cursor()
    error = None
    delays_seen = delays_new = cancellations_seen = alerts_seen = alerts_new = 0
    try:
        tu_feed = fetch_feed(config.TRIPUPDATES_URL_TMPL, config.realtime_key(), "TripUpdates")
        delays_seen, delays_new, cancellations_seen = process_trip_updates(tu_feed, trip_meta, stops, cur, now)

        alerts_feed = fetch_feed(config.SERVICEALERTS_URL_TMPL, config.realtime_key(), "ServiceAlerts")
        alerts_seen, alerts_new = process_alerts(alerts_feed, cur, now)

        conn.commit()
        print("Done: %d delays seen (%d new), %d cancelled trips, %d alerts seen (%d new)." % (
            delays_seen, delays_new, cancellations_seen, alerts_seen, alerts_new))
    except Exception as exc:
        conn.rollback()
        error = str(exc)
        print("ERROR during scan: %s" % error, file=sys.stderr)
    finally:
        db.record_scan_run(cur, {
            "run_at": now, "delays_seen": delays_seen, "delays_new": delays_new,
            "cancellations_seen": cancellations_seen, "alerts_seen": alerts_seen, "alerts_new": alerts_new,
            "static_refreshed": bool(static_refreshed), "error": error,
        })
        conn.commit()
        cur.close()
        conn.close()

    if error:
        sys.exit(1)


if __name__ == "__main__":
    main()
