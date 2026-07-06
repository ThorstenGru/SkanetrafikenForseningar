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
downloads each requested day, picks the snapshot closest to each of our normal
2-hourly poll marks, and runs it through the exact same processing pipeline
as a live scan, using that snapshot's own embedded timestamp (not wall-clock
time) — so backfilled rows are indistinguishable from ones the live scanner
would have written, just after the fact.

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
- Sampling every 2 hours means a delay that appears and fully resolves
  between two marks is invisible — exactly the same blind spot the live
  scanner has, so backfilled and live data stay consistent with each other.
- Reuses today's static index (routes/trip metadata) for the whole
  backfilled range. Fine in practice since Skånetrafiken's timetable
  changes only a few times a year, but a schedule change inside the
  backfilled window could cause a handful of `trip_id` lookups to miss.
- Safe to re-run: all writes go through the same `ON CONFLICT` upserts as a
  live scan, so re-backfilling a day just updates it, never duplicates it.

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
| `missing_trips` shows a huge number for a day the scanner wasn't running yet | The coverage check has a guard against checking dates before the scanner's first run, but only from the point that guard was added | Truncate `missing_trips` for that date range if it predates the guard |

## Check run history

```bash
gh run list --workflow=scan.yml -R ThorstenGru/SkanetrafikenForseningar --limit 10
gh run list --workflow=housekeeping.yml -R ThorstenGru/SkanetrafikenForseningar --limit 10
gh run view <run-id> --log -R ThorstenGru/SkanetrafikenForseningar
```
