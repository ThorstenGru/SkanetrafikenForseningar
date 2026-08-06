# Architecture

## Flow, in order

Capture and rendering are two separate pipelines on two separate schedules.
That split (2026-08-06) is the single most important thing to understand
here: `scan.py` almost only *writes*, so it is nearly free on Supabase's
egress meter and runs as often as GitHub will allow; the page builders only
*read*, so they are where all the egress lives and they run every third day.
See "Why rendering is decoupled from capture" below.

```
GitHub Actions (cron every 15 min, .github/workflows/scan.yml)
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
          (rows dated outside the season window are dropped here, at
           write time — see "The season window" below)
        │
        ▼
GitHub Actions commits data/static_index.sqlite (only when it changed —
about weekly). That is all scan.yml does; it publishes nothing.

.github/workflows/build.yml (cron every third day)
        │
        ▼
src/build_all.py  ── ONE pass over the database, shared by every page
   ├─ fetch_trend() + fetch_recent_line_anomalies()   (cheap SQL aggregates)
   ├─ fetch_detail_rows()  ← the single expensive query
   ├─ build_dashboard.render()      → index.html      (pre-merge rows)
   ├─ merge_trafikverket()  ← the single Trafikverket query
   ├─ build_compensation.render()   → compensation.html
   ├─ build_claims.render()         → claims.html
   ├─ build_mileage_claims.render() → mileage_claims.html
   └─ data_quality_check.record()   → data_quality_runs
        │
        ▼
GitHub Pages

.github/workflows/status.yml (cron every 30 min) → status.html, independently

.github/workflows/housekeeping.yml (cron once daily)
   ├─ 1. src/coverage_check.py — see caveat below
   └─ 2. src/housekeeping.py — deletes rows OUTSIDE the season window
```

## The season window

This project documents exactly one Sommarbiljett season: **25 June – 20
August 2026**, fixed in `config.WINDOW_START` / `config.WINDOW_END`. Nothing
before, nothing after. Every query range, every page's window metadata and
every housekeeping cutoff derives from those two constants via
`config.window_bounds()` / `config.claim_window()`; nothing computes a range
of its own.

It replaced a rolling `RETENTION_DAYS = 45` on 2026-08-06. A rolling cutoff
was not merely imprecise here, it was on course to destroy the data set: the
cutoff advanced a day per day, so from 2026-08-10 housekeeping would have
begun deleting 25 June, then 26 June, and so on — the earliest days of the
season the project exists to document — recording each deletion as a routine
success. Two literal dates cannot walk into their own data.

The window is enforced in three places, deliberately:

- **At write time** — `scan.py` and `scan_trafikverket.py` drop out-of-window
  rows before they ever reach Postgres. Both live feeds legitimately carry
  next-day trips, which is exactly how the day after 20 August would
  otherwise leak in. `backfill_koda.py` inherits this for free, since it runs
  its archived snapshots through `scan.process_trip_updates()`.
- **At read time** — every builder ranges over `config.window_bounds()`.
- **In housekeeping** — a two-sided delete, so anything that somehow got
  past the first two is removed. Operational log tables (`scan_runs`,
  `housekeeping_runs`) get the lower bound only; a two-sided window would
  have housekeeping delete its own audit row on post-season runs.

Once the season closes, `src/window_guard.py` winds the whole project down:
scanning stops at 20 August, building and housekeeping continue for a
two-day grace period so the finished season is guaranteed a final render and
a final purge, and then everything goes quiet permanently. See
docs/RUNBOOK.md, "After the season".

## Why rendering is decoupled from capture

Until 2026-08-06 the four page builds ran inside `scan.yml`, on every scan.
Each was a separate process with its own connection, and four of them
(`build_compensation.py`, `build_claims.py`, `build_mileage_claims.py`,
`data_quality_check.py`) independently ran the *same* full-window
`fetch_detail_rows()` + `merge_trafikverket()` pair, while
`build_dashboard.py` ran a fifth, narrower copy. Five passes over the same
rows, every run.

That put the Supabase organisation at **16.25 GB against a 5.5 GB free-tier
allowance**, with every project in the org — including the unrelated
BliGlömd production database, which shares the org — scheduled to start
returning 402s on 2026-08-07.

Three changes, none of which drop, thin or sample any data:

1. **`build_all.py`** — one fetch, all five consumers. The pages it produces
   are what the individual scripts produce; each `build_*.py` keeps a working
   `main()` for standalone use.
2. **Cadence** — rendering moved to its own workflow, every third day. Scanning
   kept the tightest schedule the platform will give, because polling cadence
   *is* data quality for a live GTFS-RT feed: anything missed between two
   polls is missed permanently. Rendering has no such property. The claim
   pages are the least time-sensitive of all — `SKANETRAFIKEN_REGISTRATION_LAG_DAYS`
   records Skånetrafiken support's own advice to wait 1–2 days before filing.
3. **Two wasteful queries fixed** — `build_alert_lookups()` no longer joins
   `alert_entities × alerts` unbounded (it fetched every alert's long
   `description_text` once per *entity*, ~6.4 copies each, with no date
   filter); `_fetch_announcement_groups()` now restricts `train_announcements`
   to train numbers that can actually be looked up, instead of pulling every
   train calling at a Skåne station.

## What a build actually costs

**671 MB of egress per build**, measured on the wire by `src/egress_meter.py`
and printed in every build log — not estimated from row counts.

That measurement is the reason the cadence above is every third day rather
than every three hours, and it is worth stating plainly because the first
attempt at this got it wrong: collapsing five query passes into one was a
real ~10× improvement, was reported as if it had solved the problem, and had
not. Against a 5.5 GB monthly allowance shared with BliGlömd's production
database, 671 MB per build is **about eight full builds per month**. Every
three hours projected to 157 GB/30d. Even *once a day* projects to 20 GB/30d.

| cadence | per 30 days |
|---|---|
| every 3h | 157 GB |
| every 6h | 78.7 GB |
| twice daily | 39.3 GB |
| once daily | 19.7 GB |
| **allowance** | **5.5 GB** |

The lesson worth keeping: **query count is not the billed unit.** This
architecture reads the entire season on every build and assumes reads are
free; on this tier reads are the scarce resource, and no cadence that keeps
pages usefully fresh fits inside the allowance while that stays true.

The proportionate fix was to size the cadence to the project's remaining
lifespan rather than re-architect. The season ends 2026-08-20, after which
`window_guard.py` stops every workflow permanently — from 2026-08-06 that is
~6 more builds, **~3.9 GB for the entire rest of this project's life**, which
fits. `build_all.py` prints exactly that figure (`_builds_remaining()`) at the
end of each run, so the number stays honest as the end date approaches.

**If this project ever had to keep running**, the real fix is incremental
builds: cache processed rows per day in the Actions cache and query Postgres
only for the last 2–3 days, since older days stop changing once
`SKANETRAFIKEN_REGISTRATION_LAG_DAYS` has passed, with a periodic full
rebuild to heal drift. That was deliberately *not* built here — it is a
meaningful piece of new machinery sitting directly under the numbers real
compensation claims are filed on, and it was not worth that risk for two
remaining weeks.

## Why static data is handled separately from realtime data

Trafiklab's static key has a very tight quota: 60 requests/30 days. If we
downloaded the raw GTFS zip (routes, stops, timetables for the whole region)
on every scan run — every 15 minutes, 96 times a day — the quota would be
exhausted in under half a day. Timetable data also changes rarely (a few
times a year at major schedule changes), so a week-long cache window gives
a large margin (~4 requests/month) without risking missing a timetable
change for more than a few days.

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

The fix: `coverage_check.py` establishes a **per-line baseline visibility
rate** first (`line_daily_visibility` — how often does line X normally
appear in the feed at all, over a rolling window), then only flags a line-
day as a genuine anomaly (`line_visibility_anomalies`) if it deviates well
below *that line's own* typical visibility — not from 100% schedule
coverage. Requires `MIN_BASELINE_DAYS` (7) of prior history per line before
it can evaluate anything, so `line_visibility_anomalies` stays empty for
the first couple of weeks after launch — that's correct, not a bug.

## Reason matching (ServiceAlerts)

`ServiceAlerts.pb` contains `cause`/`effect` codes (GTFS-RT spec) and free
text (`header_text`/`description_text`) in Swedish. Matching to a specific
delay is "best effort": we first look for an alert whose `informed_entity`
points exactly at the `trip_id`, then `stop_id`, then `route_id`. Most
routine delays (ordinary traffic congestion) have no published alert though
— `reason` is then `null`.

## GitHub Actions workflows

**`scan.yml`** — capture only. Writes to Postgres, publishes nothing.
- `cron: "*/15 * * * *"` — runs around the clock (UTC), raised from every 2
  hours on 2026-07-06 (see [COMPENSATION_RULES.md](COMPENSATION_RULES.md)
  §11). **What is requested is not what is delivered**: measured 2026-08-06,
  GitHub actually fires this ~12–14 times a day with gaps of 1h to 3.5h,
  including during peak daytime service. `*/15` is a request for as much as
  the platform will hand over, not a description of reality — budget quota
  and reason about coverage from the *observed* rate, not the cron string.
- `workflow_dispatch` — can also be run manually (`gh workflow run scan.yml`).
- `concurrency` with `cancel-in-progress: false` — prevents two runs from
  racing on the same static-index commit if a run takes a while.
- Secrets `TRAFIKLAB_STATIC_KEY`/`TRAFIKLAB_REALTIME_KEY`/`DATABASE_URL` are
  injected as environment variables — the actual values never appear in
  code or logs.
- The commit step only commits `data/static_index.sqlite`, and only when it
  actually changed (weekly, not every run) — delay data itself lives in
  Postgres, not git, so there's no git-history growth from it.
- Owns the `stop_times_cache.sqlite` actions/cache entry (restore *and*
  save), because `static_index.py` is what regenerates that file and this is
  the only scheduled workflow that refreshes the static index.

**`build.yml`** (every third day — see "What a build actually costs") — rendering and publishing, split out of
`scan.yml` on 2026-08-06. Runs `src/build_all.py`, which builds all four
content pages from a single database pass, then deploys to GitHub Pages. The
only workflow that writes a `data_quality_runs` row (a backfill or a plain
republish shouldn't pollute a table that tracks the live pipeline's health).
Restores the `stop_times_cache` entry read-only.

**`status.yml`** (every 30 min, halved from 15 on 2026-08-06): rebuilds
`status.html` alone. Monitoring metadata only — it holds no delay data, so
its cadence has no bearing on data quality.

**`housekeeping.yml`** (daily): runs the coverage check for yesterday, then
deletes everything outside the season window.

**`backfill.yml`** (manual only): one-off historical backfill via
`src/backfill_koda.py`, see [docs/RUNBOOK.md](RUNBOOK.md#backfill-historical-data-koda).
GTFS-RT itself has no history — this pulls past days from Trafiklab's
separate KoDa archive product and replays them through the same
`process_trip_updates`/`process_alerts` functions the live scanner uses.
Its default `--interval-hours 2` predates the 2026-07-06 cadence change and
was deliberately left at 2h rather than dropped to match the new 15-min
live cadence: KoDa's per-day archive is downloaded once regardless of
interval, so a finer interval only means picking (and locally processing)
many more snapshots out of an already-downloaded day — 8x more work per
backfilled day for a one-off historical approximation, against the
350-minute job timeout. Net effect: backfilled days have a coarser
(2-hourly) blind spot than freshly-scanned days now do (15-min) — pass
`--interval-hours` explicitly on a backfill run if closer parity matters
more than run time. `timeout-minutes: 350` because KoDa builds each day's
archive on first request, which can take up to ~60 minutes.

## Dashboard (`src/build_dashboard.py`)

Reads directly from Postgres (no local SQLite involved for delay data — the
`delays` rows already carry denormalized route/stop names written at scan
time) and generates a JSON payload embedded into
`src/dashboard_template.html` (static HTML/CSS/vanilla JS, no external
dependencies). The history-per-day trend is a cheap SQL aggregate over the
full season window; the raw detail log defaults to the last 3
days (or one specific day via `--date`) to keep the exported HTML bounded
as history grows — see [RUNBOOK.md](RUNBOOK.md#generate-a-dashboard).

The log is **one row per trip** (`trip_id` + `trip_start_date`), not per
stop: `fetch_detail_rows()` groups all of a trip's per-stop `delays` rows in
Python, taking the final stop's own delay (`finalDelayMin`) separately from
the largest delay seen anywhere along the trip (`maxDelayMin`) — see the
"two delay metrics" decision in [COMPENSATION_RULES.md](COMPENSATION_RULES.md).
Both the trend and the log are scoped to `sommarticket_valid = true` only —
Sommarbiljetten doesn't cover the Ven ferry or Öresund/Denmark-bound trips,
so those never show up in the dashboard at all, not just in a future
compensation calculation.

## Compensation estimate (`src/build_compensation.py`)

A second page (`compensation.html`), built on every scan alongside the main
dashboard. Reuses `fetch_detail_rows()` from `build_dashboard.py` — same
per-trip data, but queried across the **full season window**
(not just the last few days) since the point is catching claimable delays
before Skånetrafiken's 2-month application deadline passes.

Filters to trips delayed ≥20 minutes at the final stop (falling back to the
largest observed delay, flagged as approximate, when the final stop was
never captured), then computes two independent, non-additive estimates per
the rules in [COMPENSATION_RULES.md](COMPENSATION_RULES.md):
- **Price deduction** — tiered % (50/75/100%) of the Sommarbiljett's
  single-trip price (595 kr ÷ 40), cash or as a voucher code (+50%).
- **Car reimbursement** — `distance_km × 2.5 kr/km`, capped at the
  published per-trip maximum (2,960 kr from 2026-01-01). No voucher bonus
  is documented for this path, so cash and voucher are shown as equal —
  not an oversight.

Fully cancelled trips are listed (for visibility) but excluded from the
calculation — the rules don't specify a formula for a trip that never ran
at all. All constants live in `config.py`, next to `route_type_label()`.
