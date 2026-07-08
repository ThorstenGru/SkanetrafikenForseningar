# Trafikverket TrainAnnouncement — a second, independent rail-delay source

Research + scoping done 2026-07-08, requested by the user after discovering
a concrete gap: two departures the user saw flagged in Skånetrafiken's own
app (a 04:50 delay, a 05:20 cancellation, both on 2026-07-08) had **zero**
rows in either `delays` or `trip_cancellations` when checked directly
against this project's own Supabase project. This isn't a scanner bug — see
[ARCHITECTURE.md](ARCHITECTURE.md)'s coverage-check section: only ~5% of all
scheduled trips ever appear in Trafiklab's GTFS-RT `TripUpdates.pb` feed at
all, verified empirically 2026-07-05. Skånetrafiken's own app clearly had
better information for those two trips than this project's data source can
ever see — the question was whether a different, independent data source
could close that gap.

## The source: Trafikverket's own open API

Trafikverket (the Swedish Transport Administration — the track/road
infrastructure owner, not an operator) publishes real-time train movement
data through `api.trafikinfo.trafikverket.se`, a completely separate
product/registration from Trafiklab. The relevant object is
`TrainAnnouncement`: one record per train's scheduled/estimated/actual
arrival or departure at a station, plus operator, track, and deviation
info.

**Why this plausibly covers what GTFS-RT misses:** this is Trafikverket's
own track-side train-describer system — the infrastructure owner tracking
trains on its own network, not dependent on which onboard AVL/GPS equipment
a given vehicle happens to carry and report back to Samtrafiken. It's the
source Trafikverket's own public "Tågläget" reporting is built on. Pågatåg,
Öresundståg, and Krösatåg (Skånetrafiken's rail services) all run on
Trafikverket-owned track, so in principle this should see traffic GTFS-RT
never reports on.

**Confirmed facts** (via web search, 2026-07-08 — see Sources):
- Free to use, registration at `api.trafikinfo.trafikverket.se`, license
  CC0 (public domain).
- Query language: XML request body (`LOGIN`/`QUERY`/`FILTER` elements),
  response as XML or JSON depending on the endpoint's own file extension.
- No push/webhook — polling only. Empirically, forecast fields (
  `EstimatedTimeAtLocation`) update roughly every 2–10 minutes, so a 15-min
  poll cadence (matching this project's existing `scan.yml` cadence) is a
  reasonable starting point, not an under- or over-poll.
- Incremental updates via a `changeid` mechanism: each response carries a
  changeid; the next request replays it to get only what changed since,
  instead of re-fetching a full window every time.
- No published hard rate limit found — Trafikverket's own docs describe
  monitoring usage and contacting integrators who exceed unspecified limits,
  rather than a fixed numeric quota like Trafiklab's.

## Question #1 — backfill/history: RESOLVED, 2026-07-08, with a real key. No.

A `TRAFIKVERKET_KEY` was registered and tested directly (not inferred from
blog posts). Three real queries against `TrainAnnouncement`, filtered to
`AdvertisedTrainIdent=1206` (a real Skåne train, the one behind the claim
that motivated this whole investigation):

| Query date | AdvertisedTimeAtLocation range | Rows returned |
|---|---|---|
| Today (2026-07-08) | that calendar day | **50** (full stop-by-stop detail) |
| 13 days back (2026-06-25) | that calendar day | **0** |
| ~8 weeks back (2026-05-15) | that calendar day | **0** |

A separate query with no date filter at all also confirmed the API happily
returns **~2 weeks of FUTURE schedule** per train (rows dated 2026-07-22
came back unprompted). So the shape is asymmetric: generous forward
visibility, essentially no backward one. **Confirmed: this cannot backfill
past delays.** It only helps for trips scanned after it's deployed and
running — same limitation as Trafiklab's GTFS-RT, which is exactly why this
project already has a separate `backfill_koda.py` for *that* feed. If
Trafikverket has an analogous historical-archive product, it wasn't found
here — a registered account's support channel would be the next place to
ask, but don't assume "yes" without confirming.

## Question #2 — station crosswalk: RESOLVED, no manual mapping needed

Trafikverket publishes its own `TrainStation` object type — the official
`LocationSignature → name/coordinates` table. Queried directly for a
handful of signatures seen in the train-1206 response:

| LocationSignature | AdvertisedLocationName | Matches our route? |
|---|---|---|
| `Trg` | Trelleborg | ✅ our route's origin |
| `Hm` | Hässleholm | ✅ where the delay began, per the original claim |
| `Mlb` | Mellby | ✅ intermediate stop |
| `Cr` | Kristianstad C | ✅ our route's destination |

Each `TrainStation` record also carries `WGS84`/`SWEREF99TM` coordinates —
directly usable with the same 600 m fuzzy-match radius `build_claims.py`
already uses for chain-building (`CLAIM_CHAIN_CONNECT_RADIUS_M`), so
`location_signature_map` can be populated by importing `TrainStation`
once and matching to our own `stops` table by coordinate proximity, not by
hand-typing station names. No need to touch `static_index.py`'s `stop_code`
handling at all.

## Question #3 — RESOLVED, 2026-07-08: identity confirmed, `Canceled` genuinely conflicts with reality, and that's fine — here's why

Pulled the complete raw record for `AdvertisedTrainIdent=1206`,
`LocationSignature=Cr` (Kristianstad C), `ActivityType=Ankomst`, on
2026-07-08 — every field, not just the ones the skeleton parses:

```
FromLocation: Trg (Trelleborg)         ToLocation: Cr (Kristianstad C)
InformationOwner: Skånetrafiken        ProductInformation: Pågatågen
Operator: ARRIVA                       OperationalTrainNumber: 1206
AdvertisedTimeAtLocation: 07:56        EstimatedTimeAtLocation: (null)
TimeAtLocation: (null)                 Canceled: true
Deviation: ["Inställt" (Cancelled), "Nästa avgång" (Next departure)]
```

**Train identity is no longer in doubt.** `FromLocation`/`ToLocation` are
exactly Trelleborg→Kristianstad C, `InformationOwner`/`ProductInformation`
confirm Skånetrafiken's Pågatåg product, and `OperationalTrainNumber`
matches `AdvertisedTrainIdent` (1206) exactly. This is unambiguously the
same physical train as the claim that started this whole investigation —
not a numeric coincidence with an unrelated national train (the earlier
50+-station result for a train-number-only query, with no station filter,
was pulling in an *unrelated* different train that also happens to be
numbered 1206 on a different, unrelated line — a real reminder that
`AdvertisedTrainIdent` alone is not a safe join key without also
constraining to known Skåne `LocationSignature`s, exactly as the module's
crosswalk-based filtering was already designed to do).

**But Trafikverket's own official record says this specific train's
Kristianstad arrival was cancelled** (`Inställt`) and reissued as a new
slot (`Nästa avgång`), with no `TimeAtLocation`/`EstimatedTimeAtLocation`
ever recorded — as if it never arrived at all. Searched a ±90 min window
around it at the same station for a "replacement" announcement under a
different train number: found none — the next Skåne train through
Kristianstad C (`1208`) was the *regularly scheduled* next departure,
unrelated to 1206's disruption, running on time.

**Cross-checked against two independent, agreeing sources — both say the
train ran:**
1. This project's own `delays` table (Trafiklab GTFS-RT): trip 1206 was
   consistently reported `SCHEDULED` (never `CANCELED`) across every poll
   that day, with a real recorded `arrival_time` of 08:28 at Kristianstad C.
   `trip_cancellations` has zero rows for 2026-07-08 at all.
2. Skånetrafiken's own customer-facing app — the original screenshot this
   entire investigation started from — showed the same journey with a real
   08:28 arrival and a computed +32.9 min delay, not a cancellation.

**Conclusion: Trafikverket's `Canceled` flag on this one record is the
outlier, not the two Skånetrafiken-side sources.** The most likely
explanation, based on how European infrastructure managers commonly handle
this: once a delay grows large enough to disrupt the following schedule,
Trafikverket's train-describer system can formally withdraw ("ställer in")
the *original advertised time-slot* and treat the continuation as a new,
loosely-linked path (hence `"Nästa avgång"`) — administrative
re-slotting, not "this train never moved." The `TrackAtLocation: "x"`
placeholder on this record (a real platform is normally a number) is
consistent with an auto-generated/never-finalized record. This wasn't
proven by finding the literal replacement record (none was found in the
searched window) — it's the most consistent explanation across three
independent signals, two of which directly agree with each other and with
what the rider actually saw happen.

**Practical consequence for this project — a hard rule, not a suggestion:**
`train_announcements.canceled` must **never override** an existing
GTFS-RT-based verdict in `delays`/`trip_cancellations`. Design rule for the
eventual merge logic in `build_claims.py`/`build_compensation.py`:
- **GTFS-RT has data for the trip** (delayed or cancelled): that's the
  source of truth. Use Trafikverket only to *enrich* — e.g. its structured
  `Deviation` codes are real, human-readable reasons (this record's
  `Inställt`/`Nästa avgång`; other trains in the same test pull showed
  `Djur i spår` = animal on track, `Buss ersätter` = bus replacement,
  `Spårändrat` = track changed) — genuinely better than this project's
  current best-effort fuzzy alert-matching, which is null for most routine
  delays.
- **GTFS-RT has zero data for the trip** (the original 04:50/05:20 gap):
  only then does Trafikverket become the sole signal — and even then, a
  lone `Canceled: true` with no corroborating GTFS-RT data should surface
  as "possible claim, verify manually" rather than being auto-included
  with full confidence, given it can misfire exactly as seen here.

This directly answers the question that motivated this whole check: **yes,
the original claim (route 812, Trelleborg→Kristianstad C, 2026-07-08,
+32.9 min) is grounded in real, corroborated data** — two independent
Skånetrafiken-side sources agree it happened. Trafikverket integration adds
real value (better reasons, and genuine new coverage for the 95% GTFS-RT
misses), but only as a *secondary, corroborating* source, never as an
overriding one.

## What's built (schema, scanner, and merge logic — see "Live end-to-end" below for current status)

- `src/migrations/012_trafikverket_train_announcements.sql` — three new
  tables:
  - `train_announcements` — one row per (train number, traffic date,
    station, arrival-or-departure), mirroring `TrainAnnouncement`'s own
    shape rather than GTFS's per-stop-sequence shape (Trafikverket has no
    `trip_id` or `stop_sequence` equivalent).
  - `location_signature_map` — the crosswalk from open question #2, empty
    until populated.
  - `trafikverket_poll_state` — single-row changeid bookkeeping, same
    pattern as `backfill_koda.py`'s own resume-point handling.
- `src/db.py` — `upsert_train_announcements_batch()` (same
  batched-`execute_values` + "don't let a stale poll clobber a newer value"
  pattern as `upsert_delays_batch()`, keyed on Trafikverket's own
  `ModifiedTime` instead of `last_seen_at`) and
  `get_/set_trafikverket_changeid()`.
- `src/config.py` — `trafikverket_key()` (new `TRAFIKVERKET_KEY` secret,
  separate from the existing `TRAFIKLAB_*` keys), API URL, lookback/
  lookahead window constants.
- `src/scan_trafikverket.py` — was an unverified skeleton; **field names now
  corrected against a real response** (2026-07-08): the train-number field
  is `AdvertisedTrainIdent`, not the guessed `AdvertisedTrainNumber`;
  `TrainOwner` is read (with `Operator` as a fallback, since the sample
  data never actually included `Operator`); rows with `Advertised: false`
  (internal/technical stops with no passenger relevance and often no
  `AdvertisedTimeAtLocation` at all) are now filtered out explicitly.
  `Deviation`'s shape is still an unverified guess — no real example
  appeared in the sample train's data.

`TRAFIKVERKET_KEY` is registered and live-tested (2026-07-08), and set as a
GitHub Actions secret on this repo (same `gh secret set` pattern as the
existing `TRAFIKLAB_*` keys — see [RUNBOOK.md](RUNBOOK.md)).

## Live end-to-end, 2026-07-08 — everything below is now actually running

Requested by the user explicitly, in this order: build the merge logic
(with the hard rule enforced in code) *first*, only then turn on
ingestion. All five previously-open items are done:

1. **Merge logic exists and enforces the hard rule**: `src/
   trafikverket_merge.py`. Two things only — enrich `reason` text on
   GTFS-RT rows that have none, and gap-fill trips GTFS-RT never saw at
   all, but ONLY when Trafikverket gives an unambiguous real recorded
   arrival time. The exact "Canceled, no time at all" pattern that turned
   out wrong for train 1206 (Question #3) is explicitly skipped, not
   guessed on. Gap-filled rows are tagged `singleSourceOnly`, which
   `claims_template.html`'s `ruleFullyApplies()` treats the same as an
   unconfirmed approximation — shown, never auto-recommended. Wired into
   both `build_compensation.py` and `build_claims.py`, right after
   `fetch_detail_rows()`.
2. **`location_signature_map` populated**: `src/
   build_location_signature_map.py`, matching Trafikverket's own
   `TrainStation` object against this project's GTFS stops by coordinates
   (500 m radius) — no manual station-by-station typing needed. **117
   stations matched** (Skåne plus a few cross-border/neighbouring-region
   ones, e.g. Karlskrona C, København H) out of 718 fetched nationally.
3. **Migration applied** to the live Supabase project.
4. **Wired into `scan.yml`** as a `continue-on-error` step — a Trafikverket
   outage or rate limit must not take down the main scan/build/deploy
   pipeline, since this is optional infrastructure. `merge_trafikverket()`
   itself also degrades to a no-op on any failure, for the same reason
   applied one layer deeper (a bug here must not break `claims.html`/
   `compensation.html` generation, which — unlike the scanner step — is
   NOT `continue-on-error`).
5. **Coverage checked** — see below.

**Two real bugs found by testing live rather than trusting the skeleton**,
both fixed same-day:
- `CardinalityViolation`: a single poll can return more than one
  `TrainAnnouncement` for the same (train, date, station, activity) key —
  e.g. a superseded record next to its replacement, different `ActivityId`.
  The batched `INSERT ... ON CONFLICT DO UPDATE` can't apply twice to the
  same key in one statement. Fixed by deduping to the latest `ModifiedTime`
  per key before the upsert.
- `NotNullViolation` on `trafikverket_poll_state.changeid`: the response
  only includes the `INFO.LASTCHANGEID` block needed to keep polling
  incrementally when the *request* itself carries a `changeid` attribute —
  confirmed live that this must be `"0"` on the very first request, not
  omitted. Omitting it (the original skeleton's behavior) silently gets a
  response with no `INFO` block at all, which then tried to persist
  `changeid = NULL`.

Both were caught immediately by actually triggering `scan.yml` and reading
the Action logs, not assumed away — the first run's `continue-on-error`
correctly contained the failure to just that one step (git commit, page
builds, and deploy all still succeeded that run) while the underlying bug
got found and fixed.

## Coverage: an early, promising, but not yet rigorous signal

A single poll (2026-07-08, ~90 min back to 4 h forward — Trafikverket's own
usable window, see Question #1) found:

| | Count |
|---|---|
| Distinct (train, date) trips Trafikverket reported | 476 |
| ...also present in GTFS-RT (`delays`/`trip_cancellations`) | 158 (33%) |
| ...GTFS-RT never saw at all | **318 (67%)** |

That's a large, promising signal — roughly 3x as many distinct Skåne rail
trip-instances visible through Trafikverket as through GTFS-RT in the same
window. It is **not** the same rigorous measurement that established the
5% GTFS-RT figure (`coverage_check.py`, a full day's schedule vs. a full
day's `seen_trips`) — this is one ~5.5-hour window, not a full day, and
doesn't yet say how many of those 318 were genuinely Sommarbiljett-eligible
rail trips vs. buses/other regions/unrelated national trains sharing a
number. `build_gapfill_rows()`'s own first live run only turned 0 of them
into actual claim candidates (114 skipped as unresolvable or ambiguous) —
expected for a first, narrow, 30-minutes-old dataset, not a sign the 318
figure is wrong; most of that gap needs either a longer accumulation
window or stricter within-window candidates than existed at that moment.
**Next step, not yet done:** let this run for a few real days, then re-run
this same comparison query over a full day's data, the way
`coverage_check.py` did for the original 5% figure — a single poll's
number is a hopeful early read, not a conclusion.

## Sources

- [Trafikverkets öppna API för trafikinformation](https://www.trafikverket.se/e-tjanster/trafikverkets-oppna-api-for-trafikinformation/)
- [Trafikverket Open API | Trafiklab](https://www.trafiklab.se/api/other-apis/trafikverket/)
- [Trafikverkets tågdata — Öppet API för förseningar (sjbets.se)](https://sjbets.se/guide/trafikverket)
- [Trafikverkets API — guide till öppna tågdata 2026 (sjbets.se)](https://sjbets.se/guide/trafikverket-api-guide/)
- [Review of Trafikverket open API for traffic information (Clear Byte)](https://www.clearbyte.org/?p=2516&lang=en)
- [GTFS Regional | Trafiklab](https://www.trafiklab.se/api/gtfs-datasets/gtfs-regional/)

None of the above were read against Trafikverket's own full schema
documentation (`api.trafikinfo.trafikverket.se/API/Model`), which requires
a registered account — this writeup should be treated as a strong starting
point, not a verified spec. Re-check field names and the retention question
directly against that documentation once a `TRAFIKVERKET_KEY` exists.
