# Architecture

## Flow, in order

```
GitHub Actions (cron every 2h, .github/workflows/scan.yml)
        │
        ▼
src/scan.py
   ├─ 1. static_index.ensure_index()
   │      if data/static_index.sqlite is missing or older than
   │      STATIC_CACHE_MAX_AGE_DAYS (7 days):
   │        → downloads the full GTFS zip (~300 MB unpacked) to
   │          .gtfs_static_raw/ (never committed)
   │        → distills routes.txt + stops.txt + calendar.txt +
   │          calendar_dates.txt + one streaming pass over
   │          stop_times.txt (finds the last stop per trip_id)
   │        → writes data/static_index.sqlite (routes, stops, trip_meta,
   │          calendar, calendar_dates)
   │        → deletes .gtfs_static_raw/
   │
   ├─ 2. fetches TripUpdates.pb (delays + cancelled trips)
   ├─ 3. fetches ServiceAlerts.pb (cause/effect codes + free text)
   │
   └─ 4. batched db.upsert_* against Postgres (Supabase)
          → delays, trip_cancellations, seen_trips, alerts,
            alert_entities, scan_runs
        │
        ▼
GitHub Actions commits data/static_index.sqlite (only when it changed —
about weekly) and deploys the rebuilt dashboard to GitHub Pages

.github/workflows/housekeeping.yml (cron once daily)
   ├─ 1. src/coverage_check.py — see caveat below
   └─ 2. src/housekeeping.py — deletes rows older than 45 days everywhere
```

## Why static data is handled separately from realtime data

Trafiklab's static key has a very tight quota: 60 requests/30 days. If we
downloaded the raw GTFS zip (routes, stops, timetables for the whole region)
on every 2-hour run, the quota would be exhausted in a bit over a week.
Timetable data also changes rarely (a few times a year at major schedule
changes), so a week-long cache window gives a large margin (~4 requests/
month) without risking missing a timetable change for more than a few days.

The raw zip is too large (~300 MB unpacked, dominated by `stop_times.txt` at
~150 MB) to commit to git. We therefore run a one-off transformation: for
each `trip_id` we find the row with the highest `stop_sequence` in
`stop_times.txt` (a single streaming pass — memory use is bounded by the
number of trips, not the number of rows in the file) and only keep the
destination's `stop_id`/name. The result, `data/static_index.sqlite`, is a
few MB and gets committed normally.

## Why "scheduled time" doesn't require indexing all of `stop_times.txt`

GTFS-RT `StopTimeUpdate`, when Skånetrafiken publishes it, contains both an
absolute `time` field (actual arrival/departure, unix epoch) **and** a
`delay` field (seconds). Scheduled time is therefore simply:

```
scheduled_time = time - delay
```

This avoids having to look up exact timetable times in the 150 MB
`stop_times.txt` — the realtime feed already gives us both numbers we need.

## Deduplication

The key `(trip_id, trip_start_date, stop_sequence)` is unique per row in
`delays`. Note it's keyed on `stop_sequence`, not `stop_id` — a circular/
loop route can revisit the same physical stop twice in one trip, which
would otherwise collide. `stop_sequence` is guaranteed unique per trip by
the GTFS spec.

Every new poll of the same key **updates** the row instead of creating a
new one: `last_seen_at` and `poll_count` are updated, and
`max_abs_delay_sec` keeps the largest observed value (a delay can both grow
and shrink over the course of a trip).

Whole trips with `trip.schedule_relationship = CANCELED` are handled
separately in `trip_cancellations`, since such trips often have no
`stop_time_update` rows at all (and thus nothing to write to `delays`).

Writes are **batched**: scan.py accumulates all rows from one poll into
lists and does one `execute_values()` round-trip per table, not one
round-trip per row. A single poll can touch 5,000-15,000 delay rows — doing
that as individual statements against a cloud database was slow enough
(minutes) to occasionally hit Supabase's statement timeout. Batching brought
a full scan down to ~7 seconds.

## Coverage check — a real limitation, not swept under the rug

`seen_trips` logs every `trip_id` seen in a poll, regardless of delay,
specifically so we could diff a finished day's full schedule against what
actually appeared in the feed — catching trips that silently never showed
up at all.

**This turned out not to work as a simple diff.** Empirically (verified
2026-07-05 against real data): only about **5% of all scheduled trips ever
appear in the TripUpdates feed on a given day** — even on a day we scanned
continuously. Skånetrafiken's feed apparently only reports live predictions
for a subset of vehicles (likely those with GPS/AVL tracking), not for
every scheduled trip. A naive "scheduled minus seen" comparison would flag
~95% of completely normal, on-time service as "missing", which is false.

The fix in progress: establish a **per-line baseline visibility rate**
first (how often does line X normally appear in the feed at all, over a
rolling window), then only flag a trip as a genuine anomaly if it deviates
from *that line's own* typical visibility — not from 100% schedule
coverage. See `src/coverage_check.py` for the current state of this
redesign; treat any figures from `missing_trips` as unreliable until that
lands.

## Reason matching (ServiceAlerts)

`ServiceAlerts.pb` contains `cause`/`effect` codes (GTFS-RT spec) and free
text (`header_text`/`description_text`) in Swedish. Matching to a specific
delay is "best effort": we first look for an alert whose `informed_entity`
points exactly at the `trip_id`, then `stop_id`, then `route_id`. Most
routine delays (ordinary traffic congestion) have no published alert though
— `reason` is then `null`.

## GitHub Actions workflows

**`scan.yml`** (every 2 hours):
- `cron: "0 */2 * * *"` — runs around the clock (UTC).
- `workflow_dispatch` — can also be run manually (`gh workflow run scan.yml`).
- `concurrency` with `cancel-in-progress: false` — prevents two runs from
  racing on the same static-index commit if a run takes a while.
- Secrets `TRAFIKLAB_STATIC_KEY`/`TRAFIKLAB_REALTIME_KEY`/`DATABASE_URL` are
  injected as environment variables — the actual values never appear in
  code or logs.
- The commit step only commits `data/static_index.sqlite`, and only when it
  actually changed (weekly, not every 2h) — delay data itself lives in
  Postgres, not git, so there's no git-history growth from it.
- Builds the dashboard and deploys it to GitHub Pages every run.

**`housekeeping.yml`** (daily): runs the coverage check for yesterday, then
deletes everything older than 45 days.

## Dashboard (`src/build_dashboard.py`)

Reads directly from Postgres (no local SQLite involved for delay data — the
`delays` rows already carry denormalized route/stop names written at scan
time) and generates a JSON payload embedded into
`src/dashboard_template.html` (static HTML/CSS/vanilla JS, no external
dependencies). The history-per-day trend is a cheap SQL aggregate over the
full 45-day retention window; the raw detail log defaults to the last 3
days (or one specific day via `--date`) to keep the exported HTML bounded
as history grows — see [RUNBOOK.md](RUNBOOK.md#generate-a-dashboard).
