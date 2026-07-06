# Skånetrafiken Delays

**Copyright (c) 2026 Thorsten Grund. All rights reserved. USE AT YOUR OWN RISK.**

Continuous scanner that collects delays, cancelled trips, and service alerts
for the whole Skånetrafiken network, via Trafiklab's open GTFS Regional data.
Runs automatically every 2 hours via GitHub Actions and builds up a history
in Postgres (Supabase) — intended as evidence for compensation claims,
complaints to Skånetrafiken about recurring problems, and personal stats.

**Live dashboard:** https://thorstengru.github.io/SkanetrafikenForseningar/
(rebuilt automatically on every scan run).

**Compensation estimate:** https://thorstengru.github.io/SkanetrafikenForseningar/compensation.html
— illustrative delay-compensation figures per trip (price deduction and car
reimbursement), based on the rules in
[docs/COMPENSATION_RULES.md](docs/COMPENSATION_RULES.md). Not a real claim
tool — see the disclaimer on the page itself.

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
2. **Realtime data** is fetched every 2 hours (`TripUpdates.pb` +
   `ServiceAlerts.pb`) and written batched to **Postgres** (Supabase, its
   own dedicated project — see [docs/RUNBOOK.md](docs/RUNBOOK.md)), with
   deduplication per (trip, date, stop order).
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
| `src/scan.py` | Runs a scan (refreshes the static index if needed + realtime data → Postgres). Runs automatically every 2 hours. |
| `src/coverage_check.py` | Compares a finished day's timetable against what actually showed up in the feed. Runs automatically daily. |
| `src/housekeeping.py` | Deletes data older than 45 days. Runs automatically daily. |
| `src/build_dashboard.py` | Builds the standalone HTML dashboard. Runs automatically on every scan. |
| `src/build_compensation.py` | Builds the compensation-estimate page (`compensation.html`). Runs automatically on every scan. |
| `src/static_index.py` | Can be run standalone to force a static-index refresh. |
| `src/backfill_koda.py` | One-off backfill of past days from Trafiklab's KoDa historical archive. Manually triggered (`backfill.yml`), see [docs/RUNBOOK.md](docs/RUNBOOK.md#backfill-historical-data-koda). |

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
- Polling happens every 2 hours — short delays that occur and resolve
  within that window can be missed or underestimated. The quota (30,000
  requests/30 days) allows much more frequent polling if that becomes
  worthwhile.
- Only ~5% of scheduled trips ever appear in the realtime feed at all — see
  the coverage-check caveat above.
