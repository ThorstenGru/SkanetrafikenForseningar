# Skånetrafiken Delays

**Copyright (c) 2026 Thorsten Grund. All rights reserved. USE AT YOUR OWN RISK.**

Continuous scanner that collects delays, cancelled trips, and service alerts
for the whole Skånetrafiken network, via Trafiklab's open GTFS Regional data.
Runs automatically every 15 minutes via GitHub Actions and builds up a history
in Postgres (Supabase) — intended as evidence for compensation claims,
complaints to Skånetrafiken about recurring problems, and personal stats.

**Live dashboard:** https://thorstengru.github.io/SkanetrafikenForseningar/
(rebuilt automatically on every scan run).

**Compensation estimate:** https://thorstengru.github.io/SkanetrafikenForseningar/compensation.html
— illustrative delay-compensation figures per trip (price deduction and car
reimbursement), based on the rules in
[docs/COMPENSATION_RULES.md](docs/COMPENSATION_RULES.md). Not a real claim
tool — see the disclaimer on the page itself.

**Reasonable claim chains:** https://thorstengru.github.io/SkanetrafikenForseningar/claims.html
— checks whether a set of claims could plausibly be one real rider's day:
groups eligible trips per day into chains where one trip's destination is
the next trip's origin (same place, in order), and flags any gap between
chains with the question an investigator would ask ("how did you get from
X to Y?"). Illustrative and network-wide like the other pages, not
personalized — you still pick which trips were actually yours. Also
drives the actual filing: a picked trip moves through cart → checked out →
**printed** (fills Skånetrafiken's real paper form client-side — route,
date, times, delay length, compensation/payout choice — using coordinates
measured off the template's own layout, then opens the OS print dialog) →
archived once mailed. Personnummer, bank details, and the signature are
never collected or filled, regardless of instruction — see
[docs/COMPENSATION_RULES.md](docs/COMPENSATION_RULES.md) §14/§17.

**System status:** https://thorstengru.github.io/SkanetrafikenForseningar/status.html
— live health of every moving part (Supabase reachability + table sizes,
every GitHub Actions workflow's last run, page reachability, static-index
freshness), rebuilt independently every 15 minutes and designed to still
say something useful when the database itself is down.

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — the pipeline in detail, design decisions and why.
- [docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md) — every table and column.
- [docs/RUNBOOK.md](docs/RUNBOOK.md) — key rotation, manual scan, dashboard, troubleshooting.
- [docs/COMPENSATION_RULES.md](docs/COMPENSATION_RULES.md) — Skånetrafiken's delay-compensation rules, travel terms, and Sommarbiljetten specifics (research, not yet wired into the scanner).

## Quickstart

```bash
git clone https://github.com/ThorstenGru/SkanetrafikenForseningar.git
cd SkanetrafikenForseningar
pip install -r requirements.txt
export TRAFIKLAB_STATIC_KEY=...      # from developer.trafiklab.se
export TRAFIKLAB_REALTIME_KEY=...
export DATABASE_URL=...              # Postgres connection (Supabase), see docs/RUNBOOK.md
python src/scan.py                   # run one scan, writes to Postgres
python src/build_dashboard.py        # build dashboard.html (history + recent days in detail)
```

In production none of the above is needed locally — GitHub Actions runs
everything automatically (see below) and deploys the dashboard to GitHub
Pages.

## Architecture at a glance

1. **Static index** (`data/static_index.sqlite`, committed to git) — routes,
   stops, each trip's destination, and calendar rules (which days a trip
   actually runs). Rebuilt about once a week to conserve the tight static
   quota (60 requests/30 days).
2. **Realtime data** is fetched every 15 minutes (`TripUpdates.pb` +
   `ServiceAlerts.pb`) and written batched to **Postgres** (Supabase, its
   own dedicated project — see [docs/RUNBOOK.md](docs/RUNBOOK.md)), with
   deduplication per (trip, date, stop order). Chosen to minimize the
   chance of a short trip starting and finishing entirely between two polls
   (see "Known limitations" below) — well within the realtime quota
   (30,000 requests/30 days; 2 requests every 15 min ≈ 5,760/30 days, ~19%
   of budget). Only delays **≥5 minutes** are actually stored (plus each
   trip's origin/final stop and any irregular — e.g. skipped — stop,
   always, regardless of delay) — GTFS-RT reports jitter down to the
   second, which was 94% of this table's rows/bytes for zero compensation
   value (only ≥20-min delays are ever eligible). See
   `config.MIN_DELAY_TO_RECORD_SEC`.
3. **Coverage check** — once a day, compares which trips actually showed up
   in the realtime feed against the timetable. ⚠️ Known limitation: only
   ~5% of scheduled trips ever appear in Skånetrafiken's realtime feed at
   all (most vehicles aren't live-tracked), so this can't simply diff
   "scheduled" vs. "seen" — see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
   for the per-line baseline approach this requires.
4. **Housekeeping** — once a day, rows older than **45 days** are deleted
   from every table.
5. **Dashboard** is rebuilt on every scan and deployed to GitHub Pages — the
   history trend covers the full 45-day window, the row log shows the most
   recent days in full detail (or one specific day via `--date`).

Full detail: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

⚠️ **Important limitation:** only a subset of delays will have a matched
alert with a reason. Most "routine" delays have no registered reason in
Trafiklab's feed — the `alerts` table is a best-effort match, not a
guarantee.

## Security

API keys and the database connection are **never** hardcoded — they're read
from environment variables (`TRAFIKLAB_STATIC_KEY`, `TRAFIKLAB_REALTIME_KEY`,
`DATABASE_URL`), and from repo secrets in GitHub Actions.

⚠️ The Trafiklab keys used during this project's development were previously
exposed in plaintext in a chat conversation and should be rotated on
developer.trafiklab.se as soon as possible — see
[docs/RUNBOOK.md](docs/RUNBOOK.md#rotate-the-api-keys).

The repo is **public** (required by GitHub Free to use Pages) — source code
and the distilled static cache are visible to everyone. Raw data (every
individual delay) lives in a separate, non-public Postgres database.

## Tools in this repo

| Script | Purpose |
|---|---|
| `src/scan.py` | Runs a scan (refreshes the static index if needed + realtime data → Postgres). Runs automatically every 15 minutes. |
| `src/coverage_check.py` | Compares a finished day's timetable against what actually showed up in the feed. Runs automatically daily. |
| `src/housekeeping.py` | Deletes data older than 45 days. Runs automatically daily. |
| `src/build_dashboard.py` | Builds the standalone HTML dashboard. Runs automatically on every scan. |
| `src/build_compensation.py` | Builds the compensation-estimate page (`compensation.html`). Runs automatically on every scan. |
| `src/build_claims.py` | Builds the reasonable-claim-chains + claim-filing page (`claims.html`). Runs automatically on every scan. |
| `src/build_status.py` | Builds the system-status page (`status.html`). Runs automatically every 15 min on its own schedule, independent of the scanner. |
| `src/static_index.py` | Can be run standalone to force a static-index refresh. |
| `src/backfill_koda.py` | One-off backfill of past days from Trafiklab's KoDa historical archive. Manually triggered (`backfill.yml`), see [docs/RUNBOOK.md](docs/RUNBOOK.md#backfill-historical-data-koda). |
| `src/apply_migration.py` | Applies a `src/migrations/*.sql` file against Postgres. Manually triggered (`migrate.yml`), see [docs/RUNBOOK.md](docs/RUNBOOK.md#applying-migrations). |
| `src/db_usage_report.py` | Read-only diagnostic: total DB size, per-table breakdown, delay-magnitude histogram. Manually triggered (`db_usage_report.yml`). |
| `src/cleanup_delay_noise.py` | One-off: deletes sub-5-minute delay noise (from before `MIN_DELAY_TO_RECORD_SEC` existed) and `VACUUM FULL`s `delays`. Manually triggered (`cleanup_delay_noise.yml`) — not meant for routine use. |

## Known limitations / future ideas

- No weather data correlated yet (would strengthen pattern analysis).
- No individual vehicle ID (would require `VehiclePositions.pb`, not implemented).
- The dashboard covers the whole network scoped to Sommarbiljett validity,
  not "my specific commute" — every row is a standalone trip, not a
  personally-defined multi-leg journey. See
  [docs/COMPENSATION_RULES.md](docs/COMPENSATION_RULES.md) for the reasoning.
- Compensation amounts (`compensation.html`) are an illustrative estimate,
  not a real claim calculation — see the page's own disclaimer and
  [docs/COMPENSATION_RULES.md](docs/COMPENSATION_RULES.md) for caveats
  (e.g. no documented voucher bonus for car reimbursement, cancelled trips
  are listed but not scored).
- Polling happens every 15 minutes (raised from every 2 hours on 2026-07-06,
  see COMPENSATION_RULES.md §11) — a trip whose entire live-tracking window
  falls between two polls is still theoretically possible but now a 15-min
  gap instead of a 2-hour one. Still ~19% of the realtime quota, so this
  could be tightened further if it turns out to still miss things.
- Only ~5% of scheduled trips ever appear in the realtime feed at all — see
  the coverage-check caveat above.
- Supabase's **Free Plan caps database size at 0.5 GB**. A multi-day
  backfill at pre-`MIN_DELAY_TO_RECORD_SEC` density once pushed this to
  1 GB+ and triggered write failures across the board (see
  [docs/RUNBOOK.md](docs/RUNBOOK.md) for the incident and fix). At the
  current ~5-min storage floor this isn't a near-term concern, but a
  future change that widens what gets recorded should re-run
  `db_usage_report.yml` first, not assume there's headroom.
