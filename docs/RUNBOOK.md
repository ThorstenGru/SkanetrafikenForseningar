# Runbook

## Rotate the API keys (do this soon — see security warning in README)

The keys currently in use were exposed in plaintext in an earlier chat
session.

1. Log in at https://developer.trafiklab.se
2. Rotate/generate new keys for **GTFS Regional Static** and
   **GTFS Regional Realtime** (Bronze tier is enough).
3. Update GitHub secrets:
   ```bash
   gh secret set TRAFIKLAB_STATIC_KEY --body "NEW_STATIC_KEY" -R ThorstenGru/SkanetrafikenForseningar
   gh secret set TRAFIKLAB_REALTIME_KEY --body "NEW_REALTIME_KEY" -R ThorstenGru/SkanetrafikenForseningar
   ```
4. Run a manual scan to verify the new keys work:
   ```bash
   gh workflow run scan.yml -R ThorstenGru/SkanetrafikenForseningar
   gh run list --workflow=scan.yml -R ThorstenGru/SkanetrafikenForseningar --limit 1
   ```
5. If you also run locally: update your local environment variables
   (`TRAFIKLAB_STATIC_KEY`, `TRAFIKLAB_REALTIME_KEY`).

Also remember to change the password for `ThorstenGrund@icloud.com`, which
was exposed in the same earlier conversation.

## Trafikverket API key

`TRAFIKVERKET_KEY` — a separate registration from the `TRAFIKLAB_*` keys
above, at `data.trafikverket.se` (not developer.trafiklab.se). Powers
`src/scan_trafikverket.py`, the second rail-delay source described in
[TRAFIKVERKET_INTEGRATION.md](TRAFIKVERKET_INTEGRATION.md). **Live since
2026-07-08** — `scan.yml` runs it on the same `*/15 * * * *` cron as the
main scan (as a `continue-on-error` step, since it's still optional
infrastructure — see TRAFIKVERKET_INTEGRATION.md for what that means in
practice). Corrected 2026-07-08: this used to say "not yet wired into any
scheduled workflow," which stopped being true the same day it was written.
Rotate the same way as the Trafiklab keys: generate a new key under "Mina
nycklar" at `data.trafikverket.se/mypage/systems`, then
`gh secret set TRAFIKVERKET_KEY --body "NEW_KEY" -R ThorstenGru/SkanetrafikenForseningar`.

## Run a manual scan

**Via GitHub Actions (recommended, nothing to set up locally):**
```bash
gh workflow run scan.yml -R ThorstenGru/SkanetrafikenForseningar
```

**Locally:**
```bash
cd SkanetrafikenForseningar
pip install -r requirements.txt
export TRAFIKLAB_STATIC_KEY=...
export TRAFIKLAB_REALTIME_KEY=...
export DATABASE_URL=...   # Postgres connection string, see below
python src/scan.py

# Second, independent rail-delay source (optional -- degrades gracefully
# if skipped, see TRAFIKVERKET_INTEGRATION.md). scan.yml runs this as its
# own step in the same job; added here 2026-07-08 since this section
# previously only listed the TRAFIKLAB_* keys even after that changed.
export TRAFIKVERKET_KEY=...
python src/scan_trafikverket.py
```

## Generate a dashboard

No network access or API key needed — reads only from Postgres.

```bash
export DATABASE_URL=...
python src/build_dashboard.py                 # full history trend + last 3 days of detail
python src/build_dashboard.py --days 7        # last 7 days of detail
python src/build_dashboard.py --date 20260705 # exactly one day (smaller file once history has grown)
python src/build_dashboard.py --out other_file.html
```

Open the resulting `dashboard.html` directly in a browser. At the top is a
"History by day" table — click a row to zoom into that day, or use the
"Showing day" selector. Everything else (stats, per-line, the log) filters
by the selected day.

```bash
export DATABASE_URL=...
python src/build_compensation.py                 # compensation.html, full 45-day window
python src/build_compensation.py --out other.html
```

Illustrative delay-compensation estimate (price deduction + car
reimbursement) — see [docs/COMPENSATION_RULES.md](COMPENSATION_RULES.md).

## Backfill historical data (KoDa)

The live scanner only sees delays from the moment it starts polling — GTFS-RT
itself is a live feed with no history. To fill in the past, Trafiklab's
[KoDa](https://www.trafiklab.se/api/our-apis/koda/) archive stores daily
snapshots of TripUpdates/ServiceAlerts going back years. `src/backfill_koda.py`
downloads each requested day, picks the snapshot closest to each of a chosen
set of poll marks (`--interval-hours`, default 2 — coarser than the live
scanner's current 15-min cadence, see caveat below), and runs it through the
exact same processing pipeline as a live scan, using that snapshot's own
embedded timestamp (not wall-clock time) — so backfilled rows are
indistinguishable from ones the live scanner would have written, just after
the fact.

Requires its own API key — KoDa is a separate Trafiklab product from GTFS
Regional Static/Realtime:
1. Log in at https://developer.trafiklab.se → add the **KoDa** API to a
   project → copy the key.
2. `gh secret set KODA_API_KEY --body "..." -R ThorstenGru/SkanetrafikenForseningar`

**Via GitHub Actions (recommended — this can run for a long time):**
```bash
gh workflow run backfill.yml -R ThorstenGru/SkanetrafikenForseningar -f days=32 -f interval_hours=2
```

**Locally:**
```bash
export TRAFIKLAB_STATIC_KEY=...
export KODA_API_KEY=...
export DATABASE_URL=...
python src/backfill_koda.py --days 32
python src/backfill_koda.py --start 2026-06-01 --end 2026-06-30
```

Caveats:
- KoDa builds each day's archive on first request — this can take anywhere
  from a few seconds up to ~60 minutes per day, hence the long CI timeout.
- Sampling every `--interval-hours` (default 2h) means a delay that appears
  and fully resolves between two marks is invisible — the same kind of
  blind spot the live scanner has, just wider by default now that the live
  scanner polls every 15 min instead of every 2h (kept at 2h here since a
  finer interval means re-processing many more snapshots per already-
  downloaded day — see ARCHITECTURE.md). Pass a smaller `--interval-hours`
  on a backfill run for closer parity with live data, at the cost of a
  longer run.
- Reuses today's static index (routes/trip metadata) for the whole
  backfilled range. Fine in practice since Skånetrafiken's timetable
  changes only a few times a year, but a schedule change inside the
  backfilled window could cause a handful of `trip_id` lookups to miss.
- Safe to re-run: all writes go through the same `ON CONFLICT` upserts as a
  live scan, so re-backfilling a day just updates it, never duplicates it.

## Applying migrations

`schema.sql` is the original baseline (applied once, by hand, when the
project started). Anything after that lives in `src/migrations/`, numbered
in application order, and is applied via `src/apply_migration.py` — a
small generic runner that substitutes `${ENV_VAR_NAME}` placeholders in the
SQL with real environment variables first, so a migration can reference a
secret (e.g. a passphrase baked into an RLS policy) without that secret
ever being committed to the file itself.

**Via GitHub Actions (recommended — has access to `DATABASE_URL` and any
other repo secret the migration needs):**
```bash
gh workflow run migrate.yml -R ThorstenGru/SkanetrafikenForseningar -f file=src/migrations/001_claim_tracking.sql
```

**Locally**, if you have `DATABASE_URL` (and whatever secrets the specific
migration substitutes) in your environment:
```bash
export DATABASE_URL=...
export CLAIM_TRACKING_PASSPHRASE=...   # only needed for 001_claim_tracking.sql specifically
python src/apply_migration.py src/migrations/001_claim_tracking.sql
```

Migrations are written to be safe to re-run (`CREATE TABLE IF NOT EXISTS`,
`DROP POLICY IF EXISTS` before `CREATE POLICY`), so re-applying one after a
passphrase rotation or a policy tweak just updates it in place.

**A database provisioned from `schema.sql` alone is not the current
schema.** Every migration in `src/migrations/` must be applied, in order,
for the application code to actually run — e.g. `housekeeping.py`
references a column that only exists after `008_split_housekeeping_counter.sql`,
and `scan.py`/`cleanup_delay_noise.py` need `010_add_origin_stop_flag.sql`.
`004`/`006`/`009` are destructive one-off data wipes, not schema changes —
don't re-run those as part of setting up a fresh database.

## Inspect the database directly

```bash
psql "$DATABASE_URL"
=> SELECT route_short_name, COUNT(*) FROM delays WHERE trip_start_date = '2026-07-05' GROUP BY 1 ORDER BY 2 DESC;
=> \d delays
```

The static routes/stops/calendar cache is a local SQLite file:
```bash
sqlite3 data/static_index.sqlite
sqlite> SELECT COUNT(*) FROM trip_meta;
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| GH Actions job fails on `Run scanner` with HTTP 403 | Key invalid/rotated without updating secrets | Redo step 3 above with the correct key |
| HTTP 429 or quota error on the static fetch | Static quota (60/30 days) exhausted | Wait, or raise `STATIC_CACHE_MAX_AGE_DAYS` in `src/config.py` |
| All `route_short_name` shows `okand` | `trip_id` lookup against the static index is missing | Static index may be stale/out of sync — delete `data/static_index.sqlite` and rerun (costs 1 static request) |
| `ON CONFLICT DO UPDATE command cannot affect row a second time` | A batch contains two rows with the same primary key (e.g. malformed feed entities with an empty `trip_id`) | Already guarded in `scan.py` (skips empty `trip_id`, dedupes defensively before each batch) — if it recurs, inspect the feed for a new edge case |
| Workflow commits nothing most runs even though scans succeeded | Normal — `data/static_index.sqlite` only changes ~weekly; delay data lives in Postgres, not git | No action needed |
| GH Actions job's "Run Trafikverket scanner" step shows a red X but the overall job/run is still green | Expected — that step is `continue-on-error: true` on purpose (optional infrastructure, must not take down the main pipeline). It does NOT alert anywhere automatically (found by code review 2026-07-08 — no monitoring surface currently checks this specific step) | Check the step's own log directly for the real error (usually `TRAFIKVERKET_KEY` invalid/unset, or a Trafikverket API schema drift — see TRAFIKVERKET_INTEGRATION.md's own `VERIFY:` notes) |
| `train_announcements` stays empty / `location_signature_map` has 0 rows | The one-off `python src/build_location_signature_map.py` import was never run after the migration | Run it once (needs `TRAFIKVERKET_KEY` + `DATABASE_URL` locally, or via `supabase db query`) — see TRAFIKVERKET_INTEGRATION.md |
| `missing_trips` shows a huge number for a day the scanner wasn't running yet | The coverage check has a guard against checking dates before the scanner's first run, but only from the point that guard was added | Truncate `missing_trips` for that date range if it predates the guard |
| Writes fail with `psycopg2.errors.DiskFull` / `No space left on device`, or reads intermittently fail with `QueryCanceled: canceling statement due to statement timeout` or `server didn't return client encoding` | Supabase Free Plan's 0.5 GB database-size quota exceeded (2026-07-07 incident: a multi-day backfill at pre-`MIN_DELAY_TO_RECORD_SEC` density pushed the DB to 947 MB/202% of quota — a project restart fixes the "unhealthy" symptom but never the underlying quota, since restarts don't free space) | Run `db_usage_report.yml` first to see what's actually using space. If it's `delays` noise, run `cleanup_delay_noise.yml` (deletes sub-`MIN_DELAY_TO_RECORD_SEC` rows, then `VACUUM FULL`s the table — a plain `DELETE` alone doesn't shrink the file). Check status.html — a plain `SELECT 1` succeeds even when the DB can't accept writes at all, so read-only reachability isn't a reliable health signal on its own. |
| No scheduled (`schedule:`) workflow run for hours despite the workflow being active and nothing queued | Either two workflows sharing one `concurrency:` group (a long backfill run silently starves every scan cron behind it — fixed 2026-07-07 by splitting scan/backfill into separate groups), or GitHub's own scheduler delaying triggers under load (no fix available, platform behavior) | `gh run list --workflow=<name>.yml` to check for a gap; if it's a concurrency conflict, verify the group names in the relevant workflow YAMLs actually differ |

## Check run history

Fastest first check: https://thorstengru.github.io/SkanetrafikenForseningar/status.html
— last-run status of every workflow, Supabase reachability + table sizes,
and page reachability, all on one page, rebuilt every 15 minutes
independent of the scanner.

```bash
gh run list --workflow=scan.yml -R ThorstenGru/SkanetrafikenForseningar --limit 10
gh run list --workflow=housekeeping.yml -R ThorstenGru/SkanetrafikenForseningar --limit 10
gh run list --workflow=status.yml -R ThorstenGru/SkanetrafikenForseningar --limit 10
gh run view <run-id> --log -R ThorstenGru/SkanetrafikenForseningar
```

Direct database size/table breakdown without opening the Supabase
dashboard: `gh workflow run db_usage_report.yml`.
