"""Main entrypoint: refresh static index if stale, fetch TripUpdates +
ServiceAlerts from Trafiklab, and upsert everything into data/forseningar.db.

Usage:
    python src/scan.py
"""

import sqlite3
import sys
from datetime import datetime, timezone

import requests
from google.transit import gtfs_realtime_pb2

import config
import db
import static_index


def load_trip_meta(static_conn):
    routes = dict(static_conn.execute("SELECT route_id, short_name FROM routes").fetchall())
    stops = dict(static_conn.execute("SELECT stop_id, stop_name FROM stops").fetchall())
    trip_meta = {}
    for trip_id, route_id, direction_id, dest_stop_id, dest_stop_name, final_seq in static_conn.execute(
        "SELECT trip_id, route_id, direction_id, destination_stop_id, destination_stop_name, final_stop_sequence FROM trip_meta"
    ):
        trip_meta[trip_id] = {
            "route_id": route_id,
            "route_short_name": routes.get(route_id, route_id),
            "direction_id": direction_id,
            "destination_stop_name": dest_stop_name,
            "final_stop_sequence": final_seq,
        }
    return trip_meta, stops


def fetch_feed(url_tmpl, key, label):
    url = url_tmpl.format(op=config.OPERATOR, key=key)
    print("Hamtar %s..." % label)
    resp = requests.get(url, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError("%s misslyckades: HTTP %d: %s" % (label, resp.status_code, resp.text[:300]))
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(resp.content)
    return feed


def process_trip_updates(feed, trip_meta, stops, conn, now_iso):
    delays_seen = 0
    delays_new = 0
    cancellations_seen = 0

    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue
        tu = entity.trip_update
        trip_id = tu.trip.trip_id
        start_date = tu.trip.start_date or datetime.now(timezone.utc).strftime("%Y%m%d")
        trip_sched_rel = config.TRIP_SCHEDULE_RELATIONSHIP_LABELS.get(tu.trip.schedule_relationship, str(tu.trip.schedule_relationship))

        meta = trip_meta.get(trip_id, {})
        route_id = meta.get("route_id") or tu.trip.route_id
        route_short_name = meta.get("route_short_name") or tu.trip.route_id or "okand"
        destination_stop_name = meta.get("destination_stop_name", "")
        direction_id = meta.get("direction_id")
        final_seq = meta.get("final_stop_sequence")

        try:
            weekday = datetime.strptime(start_date, "%Y%m%d").weekday()
        except ValueError:
            weekday = None

        if tu.trip.schedule_relationship == 3:  # CANCELED (whole trip)
            cancellations_seen += 1
            db.upsert_cancellation(conn, {
                "trip_id": trip_id, "trip_start_date": start_date, "route_id": route_id,
                "route_short_name": route_short_name, "destination_stop_name": destination_stop_name,
            }, now_iso)
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

            row = {
                "trip_id": trip_id,
                "trip_start_date": start_date,
                "route_id": route_id,
                "route_short_name": route_short_name,
                "direction_id": direction_id,
                "destination_stop_name": destination_stop_name,
                "stop_id": stu.stop_id,
                "stop_name": stops.get(stu.stop_id, ""),
                "stop_sequence": stu.stop_sequence,
                "is_final_stop": 1 if (final_seq is not None and stu.stop_sequence == final_seq) else 0,
                "stop_schedule_relationship": stop_sched_rel,
                "trip_schedule_relationship": trip_sched_rel,
                "arrival_delay_sec": arrival_delay,
                "departure_delay_sec": departure_delay,
                "arrival_time_epoch": arrival_time,
                "departure_time_epoch": departure_time,
                "scheduled_arrival_epoch": scheduled_arrival,
                "scheduled_departure_epoch": scheduled_departure,
                "weekday": weekday,
            }
            delays_seen += 1
            if db.upsert_delay(conn, row, now_iso):
                delays_new += 1

    return delays_seen, delays_new, cancellations_seen


def process_alerts(feed, conn, now_iso):
    alerts_seen = 0
    alerts_new = 0
    for entity in feed.entity:
        if not entity.HasField("alert"):
            continue
        alerts_seen += 1
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
            "active_period_start_epoch": period_start,
            "active_period_end_epoch": period_end,
        }
        entities = [
            {"route_id": ie.route_id or None, "trip_id": ie.trip.trip_id or None, "stop_id": ie.stop_id or None}
            for ie in a.informed_entity
        ]
        if db.upsert_alert(conn, entity.id, fields, entities, now_iso):
            alerts_new += 1
    return alerts_seen, alerts_new


def main():
    now_iso = datetime.now(timezone.utc).isoformat()
    static_refreshed = static_index.ensure_index()

    static_conn = sqlite3.connect(config.STATIC_INDEX_PATH)
    trip_meta, stops = load_trip_meta(static_conn)
    static_conn.close()

    conn = db.connect()
    error = None
    delays_seen = delays_new = cancellations_seen = alerts_seen = alerts_new = 0
    try:
        tu_feed = fetch_feed(config.TRIPUPDATES_URL_TMPL, config.realtime_key(), "TripUpdates")
        delays_seen, delays_new, cancellations_seen = process_trip_updates(tu_feed, trip_meta, stops, conn, now_iso)

        alerts_feed = fetch_feed(config.SERVICEALERTS_URL_TMPL, config.realtime_key(), "ServiceAlerts")
        alerts_seen, alerts_new = process_alerts(alerts_feed, conn, now_iso)

        conn.commit()
        print("Klart: %d forseningar sedda (%d nya), %d installda turer, %d alerts sedda (%d nya)." % (
            delays_seen, delays_new, cancellations_seen, alerts_seen, alerts_new))
    except Exception as exc:
        conn.rollback()
        error = str(exc)
        print("FEL under scan: %s" % error, file=sys.stderr)
    finally:
        db.record_scan_run(conn, {
            "run_at": now_iso, "delays_seen": delays_seen, "delays_new": delays_new,
            "cancellations_seen": cancellations_seen, "alerts_seen": alerts_seen, "alerts_new": alerts_new,
            "static_refreshed": bool(static_refreshed), "error": error,
        })
        conn.commit()
        conn.close()

    if error:
        sys.exit(1)


if __name__ == "__main__":
    main()
