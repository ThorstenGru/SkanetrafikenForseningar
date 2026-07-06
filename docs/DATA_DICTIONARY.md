# Data Dictionary

## Postgres (Supabase) — see `src/schema.sql` for the authoritative DDL

### `delays`

One row per unique `(trip_id, trip_start_date, stop_sequence)`. Updated (not
duplicated) on every new poll of the same key.

| Column | Type | Description |
|---|---|---|
| `trip_id` | TEXT | Trafiklab's internal trip ID (stable per scheduled trip pattern). |
| `trip_start_date` | DATE | From GTFS-RT `trip.start_date`. Needed to distinguish the same trip on different days. |
| `route_id` | TEXT | Route ID from the static data. |
| `route_short_name` | TEXT | Line number, e.g. `"817"`. |
| `vehicle_type` | TEXT | `BUS` / `RAIL` / `TRAM` / `FERRY` / `METRO` / `DEMAND_RESPONSIVE_BUS` (Närtrafik) / `UNKNOWN`. Derived from GTFS `route_type` (Skånetrafiken uses extended hierarchical vehicle-type codes: 100=rail, 700=bus, 900=tram, 1000=ferry, 1501=demand-responsive — see `config.ROUTE_TYPE_LABELS`). |
| `trip_number` | TEXT | The operational train/bus number as shown in Skånetrafiken's own app (e.g. "1725" for a Pågatåg) — from GTFS `trips.txt`'s `samtrafiken_internal_trip_number`, populated for 100% of trips. Verified against a real screenshot match. |
| `distance_km` | REAL | Total distance travelled for the whole trip pattern, computed from `shape_dist_traveled` in `stop_times.txt` (Skånetrafiken's own published distance, not a third-party routing estimate). For rail/tram this is track distance, which may differ from road-driving distance. `NULL` if `shape_dist_traveled` is missing for any stop on the trip. |
| `sommarticket_valid` | BOOLEAN | False for the Ven ferry and any trip touching a Danish stop (Öresundsbron/Copenhagen-bound services) — Sommarbiljetten doesn't cover either. Danish stops are identified by a zone-code segment in `stop_id` (positions 7:10 == `"045"`), verified empirically against known Öresund-side stations. The dashboard and history trend are scoped to `sommarticket_valid = true` only. |
| `direction_id` | SMALLINT | 0/1, GTFS direction. |
| `destination_stop_name` | TEXT | The trip's final destination, derived from the last stop in `stop_times.txt`. |
| `stop_id` | TEXT | Stop ID for this row. |
| `stop_name` | TEXT | Human-readable stop name. |
| `stop_sequence` | INTEGER | The stop's ordinal position in the trip. **Part of the primary key**, not `stop_id` — a circular/loop route can revisit the same physical stop twice in one trip. |
| `is_final_stop` | BOOLEAN | True if this is the trip's last stop — most relevant for compensation claims. |
| `stop_schedule_relationship` | TEXT | `SCHEDULED` / `SKIPPED` / `NO_DATA` / `UNSCHEDULED` for this specific stop. |
| `trip_schedule_relationship` | TEXT | `SCHEDULED` / `ADDED` / `CANCELED` / etc for the whole trip. |
| `arrival_delay_sec` / `departure_delay_sec` | INTEGER | Delay in seconds (negative = early). |
| `arrival_time` / `departure_time` | TIMESTAMPTZ | Actual time. |
| `scheduled_arrival` / `scheduled_departure` | TIMESTAMPTZ | Computed as `time - delay`. |
| `max_abs_delay_sec` | INTEGER | Largest observed absolute delay across all polls of this row. |
| `first_seen_at` / `last_seen_at` | TIMESTAMPTZ | When this row was first/last seen in the feed. |
| `poll_count` | INTEGER | Number of times this row has been updated. |

### `trip_cancellations`

One row per `(trip_id, trip_start_date)` where the whole trip has
`schedule_relationship = CANCELED` (as opposed to `delays`, where individual
stops can be `SKIPPED` while the trip otherwise runs).

| Column | Description |
|---|---|
| `trip_id`, `trip_start_date` | See above. |
| `route_id`, `route_short_name`, `vehicle_type`, `trip_number`, `distance_km`, `sommarticket_valid`, `destination_stop_name` | See above. |
| `first_seen_at`, `last_seen_at`, `poll_count` | See above. |

### `seen_trips`

One row per `(trip_id, trip_start_date)` for **every** trip observed in a
poll, regardless of delay status — the presence log that
`coverage_check.py` uses (see [ARCHITECTURE.md](ARCHITECTURE.md) for why a
naive diff against the full schedule doesn't work).

| Column | Description |
|---|---|
| `trip_id`, `trip_start_date`, `route_short_name` | See above. |
| `first_seen_at`, `last_seen_at`, `poll_count` | See above. |

### `line_daily_visibility`

Populated by `coverage_check.py` for every fully-completed day: for each
line, what fraction of its scheduled trips appeared (with any status) in
the realtime feed that day. This is the raw data the baseline/anomaly
detection is computed from — see [ARCHITECTURE.md](ARCHITECTURE.md).

| Column | Description |
|---|---|
| `trip_start_date`, `route_short_name` | See above. |
| `scheduled_count` | Trips scheduled for this line that day. |
| `seen_count` | How many of those appeared in `seen_trips`. |
| `visibility_rate` | `seen_count / scheduled_count`. |
| `computed_at` | TIMESTAMPTZ. |

### `line_visibility_anomalies`

A line-day is inserted here only when its `visibility_rate` drops well
below *that line's own* rolling baseline (not below 100% of schedule).
Requires at least `MIN_BASELINE_DAYS` (7) of prior history for a line
before it can be evaluated at all — stays empty for the first couple of
weeks after launch, which is correct, not a bug.

| Column | Description |
|---|---|
| `trip_start_date`, `route_short_name` | See above. |
| `scheduled_count`, `seen_count` | That day's counts. |
| `actual_rate` | That day's visibility rate. |
| `baseline_rate` | The line's average rate over the prior rolling window. |
| `baseline_days` | How many prior days contributed to the baseline. |
| `detected_at` | TIMESTAMPTZ. |

### `alerts`

One row per unique `alert_uid` (GTFS-RT entity ID from `ServiceAlerts.pb`).

| Column | Description |
|---|---|
| `alert_uid` | The feed's entity ID, primary key. |
| `cause_code` / `cause_label` | GTFS-RT `Alert.Cause` enum (e.g. `CONSTRUCTION`, `OTHER_CAUSE`). Often `OTHER_CAUSE` — the real reason is in the free text. |
| `effect_code` / `effect_label` | GTFS-RT `Alert.Effect` enum. |
| `header_text` / `description_text` | Swedish free text from Skånetrafiken. |
| `active_period_start` / `active_period_end` | TIMESTAMPTZ validity period (can be `NULL` = until further notice). |
| `first_seen_at` / `last_seen_at` | See above. |

### `alert_entities`

Join table: an alert can apply to several routes/trips/stops at once.

| Column | Description |
|---|---|
| `alert_uid` | FK to `alerts`. |
| `route_id`, `trip_id`, `stop_id` | Which of these is set varies — Skånetrafiken specifies different granularity per alert. |

### `scan_runs`

One log row per run, for troubleshooting and to see the history of
successful/failed runs.

| Column | Description |
|---|---|
| `run_at` | TIMESTAMPTZ of the run. |
| `delays_seen` / `delays_new` | Rows processed / new this run. |
| `cancellations_seen` | Whole-trip cancellations this run. |
| `alerts_seen` / `alerts_new` | Same, for alerts. |
| `static_refreshed` | True if the static index was rebuilt this run. |
| `error` | Error text if any (`NULL` on success). |

### `housekeeping_runs`

One log row per daily housekeeping run.

| Column | Description |
|---|---|
| `run_at`, `cutoff_date` | When it ran and the retention cutoff used. |
| `*_deleted` | Row counts deleted per table. |
| `error` | Error text if any. |

## `data/static_index.sqlite` (local file, committed to git)

Rebuilt by `src/static_index.py`, at most once a week.

| Table | Contents |
|---|---|
| `meta` | One row: `built_at` (unix epoch of the last rebuild). |
| `routes` | `route_id` → `short_name`, `long_name`, `route_type` (raw GTFS code — see `config.ROUTE_TYPE_LABELS` for the bus/rail/tram/ferry mapping). |
| `stops` | `stop_id` → `stop_name`, `stop_lat`, `stop_lon` (lat/lon added 2026-07-06 for `claims.html`'s "same place" check — see `COMPENSATION_RULES.md` §10). |
| `trip_meta` | `trip_id` → `route_id`, `direction_id`, `service_id`, `trip_number`, `origin_stop_id`, `destination_stop_id`, `destination_stop_name`, `final_stop_sequence`, `distance_km`, `sommarticket_valid`. |
| `calendar` | `service_id` → weekday flags (`monday`..`sunday`), `start_date`, `end_date`. |
| `calendar_dates` | `service_id`, `date`, `exception_type` (1=added, 2=removed) — exceptions to the base calendar. |

`calendar`/`calendar_dates` exist so `coverage_check.py` can determine which
`trip_id`s were actually scheduled to run on a given date.
