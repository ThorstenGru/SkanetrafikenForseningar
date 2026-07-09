# Delay Compensation, Travel Terms, and Sommarbiljetten

Research saved 2026-07-05, sources: skanetrafiken.se (web pages + official
PDF terms). This is the basis for the project's planned delay-compensation
feature — see [ARCHITECTURE.md](ARCHITECTURE.md) for how it connects to the
data model, and the `TODO` (open design decisions) at the end of this
document.

Swedish official/legal terms are kept in parentheses throughout, next to
their English translation, so this document stays traceable back to the
original source wording.

**All amounts/rules below are as published on skanetrafiken.se, retrieved
2026-07-05. Skånetrafiken can change these terms without notice (explicitly
permitted under clause 1.6 of their terms) — verify against a fresh source
before using these amounts for real, especially around New Year (several
amounts change on 2026-01-01).**

## Sources

- https://www.skanetrafiken.se/kundservice/forseningsersattning/ersattning-vid-forsening/ (marketing/help page)
- https://www.skanetrafiken.se/sa-reser-du-med-oss/villkor/villkor-for-ersattning-vid-forsening/ (legally binding special terms, effective from 15 June 2025)
- "Terms for journeys with a ticket purchased from Skånetrafiken" (Villkor för resor med biljett köpt av Skånetrafiken, PDF, effective from 2026-01-01) — the general travel terms; clause 8 refers onward to the special terms above
- https://www.skanetrafiken.se/sommarbiljetten

## 1. Who is covered

Skånetrafiken's delay compensation (förseningsersättning) applies to:
- Journeys within Skåne on general public transit
- Journeys to/from neighbouring counties with a ticket bought from Skånetrafiken
- Öresundståg journeys between Skåne and Denmark (ticket bought from Skånetrafiken or DSB)
- Öresundståg journeys within Denmark
- Journeys on a booked single ticket starting in Skåne or Denmark

Journeys with a transfer to/from another Danish operator: the EU rail
passenger regulation applies instead. Resplus tickets: apply via Resplus,
not Skånetrafiken. Tickets bought from another operator (Västtrafik,
Blekingetrafiken, etc.): apply with that operator.

## 2. Basic rule for when compensation applies

> You're entitled to compensation if you're at least **20 minutes** late to
> your **final destination**. The times in the app/skanetrafiken.se govern
> — for a booked ticket/Resplus, the time on the ticket governs instead.

- "Reasonable transfer time" (skälig bytestid — the transfer time the app/website shows when you search the journey) is covered if a transfer is missed due to a delay.
- If Skånetrafiken announced a planned change (track work, road work) **at least 3 days in advance**: no compensation. Exception: booked ticket/Resplus, where the ticket's time always governs.
- A journey counts as delayed if arrival at the final destination is later than the transport contract (or the published timetable) states.
- Skånetrafiken's liability is **limited to what's stated in these terms** — no other costs or damages are compensated (see section 6).

## 3. Compensation for a valid ticket — price deduction (prisavdrag)

Requires a **valid ticket**. For a period ticket, the rider must have
"specifically arranged themselves around" (särskilt inrättat sig efter) the
journey in question — i.e. actually planned to make that specific trip, not
a blanket right just from owning the ticket.

| Delay to final destination | Price deduction |
|---|---|
| 20–39 minutes | 50% of the journey's price |
| 40–59 minutes | 75% of the journey's price |
| 60 minutes or more | 100% of the journey's price |

**Voucher code (värdekod) bonus:** choosing compensation as a voucher code
(instead of cash) gets **+50% extra**. I.e. effective compensation via
voucher = table value × 1.5.

### How the "journey's price" is calculated for period tickets

The ticket's value is divided by a fixed number of "single trips"
(enkelresor) depending on ticket type:

| Ticket type | Divisor (number of single trips) |
|---|---|
| 30-day ticket (30-dagarsbiljett) | 20 |
| 24-hour ticket (24-timmarsbiljett) | 2 |
| Flex 10/30 | 20 |
| Tourist ticket (Turistbiljett) | 4 |
| 365-day ticket | 200 |
| **Sommarbiljetten (Summer Ticket)** | **40** |

The legal text (special terms) expresses this more generally as "the period
ticket's price / average utilization rate" (periodbiljettens pris/
genomsnittlig nyttjandegrad) — the table above is Skånetrafiken's published
implementation of that.

**Limits:**
- Price deductions can never, cumulatively over the ticket's validity period, exceed what the period ticket cost.
- Claiming for a shorter journey than a 30-day or 365-day ticket covers bases compensation on the price of a period ticket for the shorter distance.
- Free period tickets (Senior, Service Travel [Serviceresebiljetten], School [Skolbiljetten], Youth [Ungdomsbiljetten]) give **no right to price deduction** — only to alternative-transport compensation (section 4).
- You **cannot** get both price deduction AND alternative-transport compensation for the same journey — must choose one.

## 4. Compensation for alternative transport (taxi, own car, other operator)

Applies if you are (or risk being) at least 20 minutes late to your final
destination. The cost must be **reasonable**, kept as low as possible, and
**documented** (receipt + bank statement).

All maximum amounts are legally expressed as **1/20 of the current "price
base amount"** (prisbasbelopp — a Swedish government figure set annually).
Skånetrafiken's website states this in kronor:

| Mode of transport | Max amount through 2025-12-31 | Max amount from 2026-01-01 |
|---|---|---|
| Taxi (per paying passenger) | 2,925 kr | 2,960 kr |
| Own car/motorcycle (incl. parking + Öresund bridge toll) | 2,925 kr | 2,960 kr |
| Alternative transport (other operator) | 2,925 kr | 2,960 kr |

- **Own car:** compensated per the Swedish Tax Agency's tax-free mileage rate: **25 kr/mil (Swedish mile = 10 km) = 2.5 kr/km**, plus parking cost and any Öresund bridge toll — all within the same max amount above. Skånetrafiken only compensates **the distance corresponding to the delayed journey** (i.e. the distance you would have travelled with Skånetrafiken), not the whole car trip if it was longer.
- **Taxi:** the max amount is per paying passenger. Shared taxis must be declared in the application. Cannot claim if you yourself own the taxi company that did the trip.
- Special rules are mentioned for **Sommarbiljett/Serviceresebiljett/Kampanjbiljett** (campaign tickets) regarding taxi compensation, but no further specific rule text was found beyond the above — likely refers to the fact that multiple people can travel on one Sommarbiljett but only one paying passenger can claim. **Unclear, should be verified with Skånetrafiken when actually filing a claim.**
- **Cannot** be combined with price deduction for the same journey (see section 3).

## 5. Compensation for meals and refreshments (longer train journeys)

Trains **150 km or longer**, delay **60 minutes or more**: entitled to
compensation for meal/refreshment expenses, **up to 150 kr per person**.
Requires an original receipt (or digital receipt, not a copy).

## 6. What is NOT compensated

- Consequential costs: missed theatre visits, dentist appointments, lost income.
- Missed flights, ferries, or trains/buses outside Skånetrafiken's terms.

## 7. Forms of compensation and how to apply

- **Voucher code** (värdekod, via SMS or email) — +50% bonus, see section 3. Usable for ticket purchases in the app/machines/website/agents/customer centres.
- **Cash** — via Swedbank's payout system (requires registration with the account register, otherwise a payment notice). Foreign account: IBAN/BIC.
- **Apply within 2 months** of the delay (statutory claim deadline).
- ID verification: BankID/Freja+ (Sweden) or MitID (Denmark). A paper form exists for those without e-ID, without a ticket, or who travelled with Närtrafik/SkåneFlex.
- Every application is **investigated and assessed** individually before a decision.
- **Misuse:** false information or misuse voids the right to compensation and can be reported to police. Frequent claims can lead Skånetrafiken to require further supporting evidence (photos, certificates, receipts) for future claims.

## 8. Sommarbiljetten (Summer Ticket) — details

- **Price 2026: 595 kr** (all of Skåne). Extended variants: Skåne+Blekinge 1,290 kr, Skåne+Kronoberg 1,440 kr, all three counties 2,135 kr.
- **Validity: 15 June – 15 August** (24/7, every day).
- Valid for **up to 3 people** at once, of whom **at most 1 may be 20 or older**.
- **Does not** cover the Öresund bridge or the Ven ferry.
- Can be lent out 31 times (max once/day, to up to 5 recipients) if registered on "My Account" (Mitt Konto). Can be given away once (if never lent out).
- Counts as "not activated" until the first valid date.
- **Price-deduction divisor: 40 single trips** → journey price for price-deduction purposes = 595 kr / 40 = **14.875 kr per single trip** (Skåne-only variant).
- Supplementary/campaign terms can apply per the general travel terms (clause 4.3.18) — beyond the divisor rule, no further separate "special terms for Sommarbiljetten" page was found when searching skanetrafiken.se (2026-07-05).

## 9. Legal basis

- Swedish Act (2015:953) on public transport passengers' rights (Lag om kollektivtrafikresenärers rättigheter) — applies to domestic journeys <150 km
- EU 2021/782 (Rail Passenger Rights Regulation) — some articles don't apply to routes <150 km
- EU 181/2011 (Bus Passenger Rights Regulation) — articles 3, 4.1, 5, 6, 8, 19–23 also apply to routes <150 km
- Railway Traffic Act (Järnvägstrafiklagen, 1975:192), Traffic Damage Act (Trafikskadelagen, 1975:1410)
- Penalty fare for travelling without a valid ticket: **1,500 kr** (Act on penalty fares in public transport, SFS 1977:67) — not a delay rule, but relevant background info.

## TODO — open design decisions before this becomes a calculation feature

See the main conversation from 2026-07-05 for the full discussion. Final
decisions (as of the second round, same day — the user revised #1, #2 and
#3 after the first round):

1. **Journey model — DECIDED: per individual trip, network-wide,
   illustrative.** Each row in the dashboard represents one GTFS trip
   (start to end of that specific vehicle run), not a personally-defined
   multi-leg journey. Simpler to build, gives network-wide visibility, but
   is still an illustration rather than an exact representation of a real
   rider's claim — a real claim requires the rider to have "specifically
   arranged themselves" for that exact journey. **Implemented.**
2. **Which delay value to show — DECIDED: both, clearly labeled.** The
   dashboard shows two distinct columns per trip:
   - *Delay at final stop* — the delay when the trip actually reached its
     own final destination (or blank/"final stop not recorded" if that
     stop never appeared in the feed at all). This is what Skånetrafiken's
     rule literally measures ("delay to your final destination").
   - *Max delay observed* — the largest delay seen anywhere along the trip,
     across all its stops and polls. Can be higher than the final delay if
     time was made up before arrival, or the only data point available if
     the final stop was never captured. **Implemented.**
3. **km calculation — DECIDED: real distance from GTFS `shapes.txt`/
   `stop_times.txt`, not a routing API.** Verified empirically (2026-07-05)
   that Skånetrafiken populates `shape_dist_traveled` in `stop_times.txt`
   with real, accurate distances (checked against a known ~185 km regional
   route). Distance per trip = `shape_dist_traveled` at the last stop minus
   at the first stop. This is Skånetrafiken's own published distance along
   the route — no external routing API/account needed. For rail/tram this
   is track distance, which may differ from a driving-by-road distance;
   documented as a known approximation rather than adding a third-party
   dependency. **Implemented** — see `distance_km` in
   [DATA_DICTIONARY.md](DATA_DICTIONARY.md).
4. **Coverage check — DECIDED: redesign completely.** Only ~5% of all
   scheduled trips ever appear in the TripUpdates feed (empirically
   verified 2026-07-05). The original "scheduled minus seen" diff would
   flag ~95% of completely normal, on-time traffic as "never seen" — not a
   real coverage gap. Redesigned as per-line baseline visibility rates,
   flagging only genuine deviations from *that line's own* typical
   visibility. **Implemented** — see [ARCHITECTURE.md](ARCHITECTURE.md).
5. **Scope — DECIDED: only Skånetrafiken trips valid with the Sommarbiljett.**
   The Ven ferry and any trip touching a Danish stop (Öresundsbron/
   Copenhagen-bound) are excluded network-wide, not just from a future
   compensation feature — see `sommarticket_valid` in
   [DATA_DICTIONARY.md](DATA_DICTIONARY.md). **Implemented.**

**Implemented (2026-07-06):** `src/build_compensation.py` generates
`compensation.html`, an illustrative estimate of price-deduction (section 3)
and car-reimbursement (section 4) compensation per eligible trip, across the
full 45-day retention window. Known simplifications, by design:
- Uses the Sommarbiljett's 40-single-trip divisor only — no other ticket
  type is modeled, since the whole project is scoped to Sommarbiljett-valid
  trips.
- No documented voucher-code bonus was found for car reimbursement (only
  for price deduction, section 3), so cash and voucher amounts are shown
  as equal for the car-reimbursement path rather than assuming a bonus
  that isn't sourced.
- Taxi and other-operator reimbursement (also section 4) are not modeled —
  only car, since that's what the user asked for specifically.
- Meal/refreshment compensation (section 5, trains ≥150 km + 60 min delay)
  is documented above but not computed — out of the scope that was asked
  for.
- Fully cancelled trips are listed on the page but excluded from the
  calculation — the rules don't specify a clear formula for a trip that
  never ran, so estimating one would be inventing a number, not measuring
  one.

## 10. Reasonable claim chains (`claims.html`, added 2026-07-06)

Directly follows from item 1 above ("network-wide, illustrative... not an
exact representation of a real rider's claim"): `compensation.html` lists
every eligible trip on the network as if it were claimed, which is not what
a real claim looks like. A real claim is for a journey the rider actually
made, and a *set* of claims for the same day has to be internally
consistent — if you claim a trip ending in Ystad and separately a trip
starting in Simrishamn the same day, the obvious question is "how did you
get from Ystad to Simrishamn?"

**Decisions made with the user (2026-07-06):**
1. **Interaction model — both auto-suggested and manually adjustable.** The
   page auto-groups all eligible network trips per day into the longest
   connected chains and pre-checks the best one as a starting suggestion;
   the user then ticks/unticks individual legs, with the chain-and-gap
   check re-run live against exactly what's currently checked.
2. **Continuity scope — per calendar day.** A chain only has to be
   internally consistent within one day; each day resets (the rider is
   presumably home overnight).
3. **"Connects" — fuzzy geographic match, not exact stop_name.** Two stops
   count as the same place if they're within `CLAIM_CHAIN_CONNECT_RADIUS_M`
   (600 m straight-line, see `config.py`) of each other. This required
   adding `stop_lat`/`stop_lon` to `static_index.py`'s `stops` table (not
   previously stored) and forcing a one-off static-index rebuild
   (`FORCE_STATIC_REFRESH=true` env var on `scan.py`, wired to a
   `workflow_dispatch` input on `scan.yml`) to backfill coordinates for the
   already-committed index.
4. **No fixed home anchor.** Only consecutive legs are checked against each
   other; the first leg of a day's chain can start anywhere.

**Known simplifications:**
- A trip only "confirms" its destination (`destConfirmed`) when it actually
  reached its own final stop (status `DELAYED`). Partially cancelled trips
  (skipped their final stop) and trips whose final stop was never captured
  in the feed can start a chain but can never be relied on to extend one —
  where the rider actually ended up in those cases isn't known.
- Trip endpoints (origin/destination stop identity) come from
  `static_index.py`'s `trip_meta` table (derived from the GTFS static
  schedule), not from which stops happened to be polled in the realtime
  feed — more reliable, but tied to whichever schedule was current when the
  static index was last built (see item 4 in section 9 above for the same
  caveat on `destination_stop_name`).
- The chain-building algorithm is a simple greedy left-to-right grouping by
  time, not a globally optimal matching — good enough to illustrate which
  combinations are plausible, not guaranteed to find every possible
  grouping in unusual interleavings.

**Added 2026-07-06, second round:**
- **Day filter**, defaulting to the most recent day (same convention as the
  dashboard's day picker), scoped to the "Suggested reasonable chains"
  browsing section only — "Your claim list" always shows the full
  selection across all days regardless of the filter, since it's a
  tracking record, not something that should appear to lose entries when
  you're just narrowing your browsing view.
- **Ranking by reasonability then possible max amount.** "Reasonability" is
  chain length (a longer connected chain is a stronger, more concrete
  travel story than a lone leg); ties break on the highest possible claim
  value, using whichever of price-deduction-voucher or car-reimbursement is
  larger per leg (they're alternatives, not additive — section 3/4). Days
  are ordered by their single best chain; within a day, chains are shown
  best-first with a score badge. The gap narrative between chains stays
  computed and displayed in strict chronological order underneath (ranking
  the display would make "how did you get from X to Y" reference the wrong
  pair of places).
- **Claim tracking** (a "Claim started" checkbox + free-text field for
  Skånetrafiken's own claim number once filed) lives in "Your possible
  claim list". Originally shipped as browser `localStorage`
  (single-device, private) on 2026-07-06; moved to a Supabase table the
  same day at the user's request ("all data should stay in the database")
  — see §12 for the full design of that move, including the security
  trade-off it required.

## 11. Coverage: what fraction of delays does this system actually catch?

Asked directly by the user 2026-07-06: "did we catch all delays… how is
the gap between planning and reality done in the app?" Answered in full,
since missing a real trip means missing a real compensation opportunity.

**How planned-vs-actual is tracked today:**
1. **Planned** — the full timetable lives in `static_index.sqlite`
   (`trip_meta` + `calendar` + `calendar_dates`), rebuilt weekly. Every
   trip Skånetrafiken schedules for a given day can be listed from this
   alone, with no realtime data involved.
2. **Actual** — `TripUpdates.pb`, fetched on every scan, reports live
   delay/status for whichever vehicles happen to be reporting at that
   moment. `seen_trips` logs every `trip_id` that appeared in any poll
   that day (delayed or not) — the "we got some reality data for this one"
   signal.
3. **The gap** — `coverage_check.py` compares scheduled vs. seen per
   *line*, once daily, and flags a line-day only when its visibility rate
   drops well below **that line's own historical baseline** (see
   ARCHITECTURE.md). It deliberately does not flag "scheduled minus seen"
   directly, because of the finding below.

**Two distinct causes of missing data, only one of them fixable here:**
- **Not fixable from this side:** only ~5% of ALL scheduled trips ever
  appear in `TripUpdates.pb` at all, on any day, including days scanned
  continuously (verified empirically 2026-07-05). Skånetrafiken's realtime
  feed apparently only reports live predictions for a subset of
  GPS/AVL-tracked vehicles — the other ~95% of scheduled service has *no*
  realtime data available anywhere, from any polling frequency. If a rider
  was on one of those trips and it ran badly late, this system has no way
  to know — Skånetrafiken's own feed never said so. That rider's only
  option is a manual claim from personal memory of the journey; nothing
  here can surface or quantify it.
- **Fixable, and fixed today:** for the ~5% of trips that *are*
  realtime-tracked, a short trip whose entire live-tracking window falls
  strictly between two polls could be missed even though the data existed
  somewhere on Trafiklab's servers at the time. This was a real gap at the
  original 2-hour polling cadence. The realtime quota (30,000 requests/30
  days) was barely touched at that cadence (2 requests × 12 scans/day ≈
  2.4% of budget) — plenty of headroom to poll far more often. **Scan
  cadence raised from every 2 hours to every 15 minutes on 2026-07-06**
  (`.github/workflows/scan.yml`), now ~19% of the realtime quota. This
  doesn't create new data Skånetrafiken didn't already have, but it
  greatly narrows the window in which already-available data could be
  polled past without ever being captured.
- Net effect: this system now catches essentially everything Skånetrafiken
  itself makes visible in realtime, for the fraction of the network their
  feed actually tracks. It cannot see delays for trips their feed never
  reports on at all — that's an external, structural limit, not a scanner
  gap.

## 12. Claim tracking moved from localStorage to Supabase

Requested by the user 2026-07-06 ("all data should stay in the database,
all in Supabase") — claims.html's "Claim started" checkbox + claim-number
field, originally per-browser `localStorage`, now writes to a new
`claim_tracking` table (`src/migrations/001_claim_tracking.sql`) directly
from the browser via Supabase's PostgREST REST API, using the project's
public anon key embedded into the built page at compile time (by
`build_claims.py`, from the `SUPABASE_ANON_KEY` GitHub secret — never
committed to git).

**The core problem this raises:** a static GitHub Pages site has no server
of its own, so *some* credential allowing writes has to live inside the
page's own shipped JavaScript, visible to anyone who opens dev tools on
the live site. This is normal and expected for Supabase's anon key
specifically (it's designed to be public; access control is meant to come
from Row Level Security, not key secrecy) — but RLS still has to decide
who's allowed to write, and there is no login system here to check against
for a single-user personal tool.

**Options discussed with the user, and the choice made:**
1. Fully open anon read/write RLS — simplest, no real access control
   beyond "you found the table exists."
2. **Chosen: a shared write passphrase**, sent as a custom
   `x-claim-passphrase` header and checked inside the RLS policy via
   PostgREST's `current_setting('request.headers', true)` mechanism. This
   is explicitly **not real security** — the passphrase ships inside
   claims.html's own JS, exactly as visible as the anon key to anyone who
   inspects the page. Its only effect is raising the bar above a casual
   visitor or bot trivially POSTing to the table without first looking at
   the page source. Reads stay fully open (no sensitive content in this
   table beyond a self-chosen claim number; the rest of the site is
   already public network-wide data).
3. Full Supabase Auth (magic link / OTP login) — the only way to get an
   actual access-controlled write. Rejected as overkill for tracking one
   person's own claim numbers on a hobby project; would add a real sign-in
   flow to what's otherwise a fully static, login-free set of pages.
4. Keep localStorage — rejected per the user's explicit ask for
   database-backed storage.

**How the passphrase itself stays out of the public repo:** generated
once with Python's `secrets.token_urlsafe`, stored only as the
`CLAIM_TRACKING_PASSPHRASE` GitHub Actions secret, and substituted into
`src/migrations/001_claim_tracking.sql`'s RLS policy at apply-time by
`src/apply_migration.py` (see docs/RUNBOOK.md#applying-migrations) — the
committed `.sql` file only ever contains the `${CLAIM_TRACKING_PASSPHRASE}`
placeholder, never the real value. The same secret is passed to
`build_claims.py` at build time to embed into the shipped page, which is
the one place it's *meant* to become visible.

**Client behavior:** `claims_template.html` loads existing tracking rows
on page load (open read, no passphrase needed), and writes optimistically
— the checkbox/text field updates immediately in the UI, with the actual
Supabase write happening in the background (immediately for the checkbox,
debounced ~600ms for the free-text claim-number field so typing doesn't
fire a request per keystroke). A small status line next to the section
heading reports "synced with Supabase" or a visible error if a read/write
fails — failures don't roll back the UI, since this is personal
record-keeping, not a transactional system.

## 13. Ticket-purchase cutoff — hard restriction

Per the user (2026-07-06, emphatic): a specific Sommarbiljett's purchase
instant is a hard floor. No trip that happened before that instant can
ever be claimed under that ticket, because the rider didn't hold a valid
ticket yet — such trips must be excluded entirely from compensation.html
and claims.html, not merely deprioritized or shown-but-excluded like
cancelled trips are.

**Implementation:** `config.sommarbiljett_purchased_at()` reads the
cutoff from the `SOMMARBILJETT_PURCHASED_AT` environment variable (ISO
8601 with UTC offset) — deliberately **not hardcoded in this file or
anywhere else in the repo**, since the actual purchase timestamp is the
user's personal data and this repo is public (see README's Security
section for the same standard already applied to API keys). It's
provided as a GitHub Actions secret at build time instead, the same
pattern used for `SUPABASE_ANON_KEY`/`CLAIM_TRACKING_PASSPHRASE`.
`compute_compensation()` (`build_compensation.py`, shared by both pages)
computes each trip's earliest known timestamp — the earliest recorded
stop time if any per-stop detail exists, else `firstSeen` for cancelled
trips — and drops the trip entirely if that's before the cutoff, before
any other eligibility check runs. The accessor raises if the env var is
unset rather than defaulting to "include everything": a build that can't
apply this restriction must fail, not silently risk showing an ineligible
trip.

**Scope decision:** applies to compensation.html and claims.html only,
not index.html (the delay-history dashboard) — the dashboard serves this
project's other two stated purposes (evidence for a systemic complaint to
Skånetrafiken, personal stats/log — see top of README), which are about
network-wide delay patterns generally and have nothing to do with which
specific ticket was held when. Flagged to the user as an interpretation
of "discard... never shown... in the app," open to correction if a
narrower or broader scope was actually intended.

The ticket's own ID (for use when actually filing claims, e.g.
pre-filling a claim form) is tracked in the user's private assistant
memory, not in this repo — it has no role in any build script and isn't
needed by anything the app itself computes or displays.

## 14. Claim-initiation wizard + why personal details never reach Supabase

Requested by the user 2026-07-06: collect everything a claim needs (which
trip, compensation type, payout method) as a guided step before actually
filling out Skånetrafiken's form, and give an "already filed" overview so
the same trip never gets claimed twice.

**What's built:** ticking "Claim started" on a leg in "Your possible claim
list" reveals two dropdowns — compensation type (prisavdrag / taxi /
mileage) and payout method (värdekod SMS / värdekod e-post / cash) — saved
to `claim_tracking` alongside the existing claimed flag and claim number
(`src/migrations/002_claim_choices.sql` added the two columns). A new
"Already filed" section at the top of the page lists every trip flagged
this way, regardless of the current day filter, specifically so a repeat
visit doesn't risk re-claiming the same delay.

**The line that matters: personal details never touch Supabase, ever.**
`claim_tracking`'s SELECT policy is `USING (true)` — open to anyone with
the anon key, which is itself public (embedded in the page). That's an
acceptable trade-off for a trip identifier + a boolean + a claim number
(see §12), but would be a serious problem for a name, address, or
personnummer. So the two new columns are deliberately limited to
low-cardinality enums that reveal nothing about the person — and the
actual claim form's personal-details section (name, address, mobile,
email, and especially personnummer) is filled locally, by hand or by
Claude working locally, and **never stored in this repo or in Supabase**.
If cross-device access to the filled form itself is ever needed, the
right next step is Supabase Storage behind real Supabase Auth (per-user
RLS), not an extension of the current anon-key model — deliberately not
built now, since it's a meaningfully larger lift than this project's
single-user scope has needed so far.

**Hard line Claude holds regardless of instruction:** personnummer and any
bank/IBAN/BIC details are never typed into the claim form by Claude, even
when explicitly told sensitivity doesn't matter — the same category as not
handling passwords or payment credentials on someone's behalf. Choosing a
voucher payout (SMS/e-post) instead of cash sidesteps the bank-details
case entirely, which is why it's the default recommendation here.

## 15. Cart → checkout → mailed lifecycle

Requested by the user 2026-07-06 (shopping-cart language): a claim moves
through three explicit stages rather than one flat "claimed" flag.

1. **Cart** — a leg ticked in "Your claim cart" (client-side `selected`
   state, not persisted — same as before). Shown with just the trip info,
   no claim-processing UI yet.
2. **Checked out** (`claimed = true`) — a bulk "Check out N claims" button
   moves every cart item here at once. This is where compensation type and
   payout method get picked (per leg), and where the claim number gets
   recorded once Skånetrafiken issues one. Unticking "Claim started" here
   moves a leg straight back to the cart — checkout isn't a one-way door
   until the next stage.
3. **Archived** (`mailed = true`) — reached only by clicking "Mark printed
   & mailed", which asks the literal confirmation the user wanted: *"All
   forms printed and on the go?"* This is the one genuinely one-way
   transition (no UI to undo it, matching that it represents something
   that actually already happened in the physical world) and is what
   finally removes a claim from the "still needs a decision" set into
   the reference archive that prevents re-filing.

`003_claim_mailed.sql` added `mailed`/`mailed_at` — still no personal
content, same reasoning as `002_claim_choices.sql`.

**What this page cannot do, restated plainly:** it cannot guarantee
Skånetrafiken will approve any claim. It checks internal consistency
against their own published rules (delay thresholds, Sommarbiljett
validity and purchase-date cutoff, chain/gap consistency, their own
"reasonable transfer time" definition) — that's the strongest claim of
correctness this project can honestly make. Their decision depends on
data and judgment this project doesn't have access to. Asked directly by
the user whether claims can be "sure to be successful": no — that
guarantee doesn't exist for anyone to give, including Skånetrafiken's own
staff before they've reviewed a specific case.

**On "empty all tables for a clean start":** considered and declined. The
purchase-date cutoff (§13) already excludes ineligible data at the
application layer, which achieves the same practical goal (no ineligible
trip is ever shown) without the irreversible cost of deleting history that
also serves this project's other two purposes (systemic-complaint
evidence, personal stats — see README). Revisit only on an explicit,
specific instruction to actually delete data, not a "maybe."

## 16. Review pass, 2026-07-06 — bugs found and fixed

Requested by the user after going productive: a real review of
claims.html (by far the most-iterated page this session), not just a
"looks fine" assurance. Two genuine issues found and fixed, not cosmetic:

- **`#myClaimsStats` grid was still 5 columns** after the cart/checkout
  split reduced "Your claim cart" to 4 stats (the "Claims started" stat
  moved to its own section) — left an empty gap in the grid on desktop
  widths. Fixed to 4, added the same class to the new
  `#checkedOutStats` block.
- **"Checked out" section didn't detect chain gaps.** It rendered a
  day's checked-out claims as one flat list rather than running them
  through `buildChains()` like "Your claim cart" and "Suggested
  reasonable chains" both do — so two disconnected checked-out claims on
  the same day silently lost the "how did you get from X to Y" warning
  that's the whole point of this project. Fixed by regrouping through
  `buildChains()` and rendering the same gap warnings, plus added a
  totals/gap-count stats row that section didn't have before.

Also: added `aria-label`/`aria-expanded` to the stop-detail expand
toggle (icon-only button, no accessible name before this), and reworded
the H1 from "Is this a travelable set of claims?" (accurate when the page
was purely a consistency-checker) to "Build a travelable set of claims,
then file them" (accurate now that it also drives the whole cart →
checkout → mailed lifecycle).

**Scope note:** this was a direct, manual review (reading the file,
reasoning about it, fixing what was found) rather than delegating to a
research/review agent — the same turn's earlier legal-research request
fanned out into 30+ sub-agents and hit the session's usage limit, so a
contained, single-actor review was the deliberately safer choice here.

## 17. Print Claim — filling and storing the actual PDF, 2026-07-07

Requested by the user 2026-07-07: split "checked out" into three real,
separate steps (a form is printed and signed long before it's mailed,
and a claim number only exists once Skånetrafiken has responded), and
have the app itself fill the official paper form instead of the
previous plan of asking Claude to do it locally each time.

**This reverses §14's "personal details never touch Supabase, ever."**
That line still holds for `claim_tracking` (still only enums + a
self-chosen claim number, still openly readable). What changed is that
the *filled PDF* — which necessarily contains name and home address —
is now deliberately stored in Supabase, in a new private bucket,
because the user asked for it explicitly and confirmed the security
trade-off below.

**How the personal-details boundary is actually kept:** first name,
last name, street, postal code, city, mobile, e-post, and (optionally)
the ticket ID live **only in the browser's own `localStorage`** (key
`skaneClaimMyDetails`), entered once via "Edit my printing details" and
reused from then on. They are never sent to `claim_tracking`, and never
appear in the built static page's own JSON payload (`__DATA_JSON__` is
fully public with no gate at all — embedding them there would be worse
than not gating them).

Mobile and e-post were added to this list 2026-07-07, after initially
being grouped with personnummer under "never collected" — the user
pointed out they're needed for Skånetrafiken to actually deliver a
värdekod by SMS/e-post, and they're ordinary contact info, not a
government ID or bank credential. **Personnummer and bank/IBAN/BIC
remain a hard line Claude holds regardless of instruction** — never
collected, never filled, never stored anywhere, even when the user
pastes one directly into chat — same category as not handling
passwords or payment credentials on someone's behalf. The signature
also always stays hand-written.

**The form itself is filled, not retyped.** The blank official PDF
(`blankett_forseningsersattning_tap.pdf`, checked into the repo as
`src/assets/claim_form_template.pdf` — it's Skånetrafiken's own public,
blank form, no personal data in it) is not a fillable AcroForm; it's a
flat printed sheet with hand-drawn per-digit boxes and circles to mark,
whose reverse side doubles as a fold-and-tape return envelope. Exact
box/circle coordinates were measured directly off the template's own
vector layout with PyMuPDF (in a one-off local script, not committed)
and hard-coded into `claims_template.html`'s client-side fill function,
which uses pdf-lib (loaded from a CDN) to overlay: name, address,
ticket ID, date of travel, route/from/to/times, the matching
delay-length circle, compensation-type circle, and payout-method
circle — nothing else. The rendered result is visually close to a
hand-filled form; it is not pixel-perfect, and the user should glance
it over before signing.

**Storage: `claim_forms` bucket, gated by the existing passphrase, not
by real auth.** This site has no login — the anon key and even the
`claim_tracking` write passphrase are both readable in the deployed
page's own JavaScript. Given that, the strongest gate available for the
new bucket without adding real Supabase Auth (still judged overkill for
this single-user tool, per §14) is the same shared passphrase already
accepted for `claim_tracking` writes — added by
`src/migrations/007_claim_form_printing.sql` as SELECT/INSERT/UPDATE
policies on `storage.objects` scoped to `bucket_id = 'claim_forms'`.
Explicitly confirmed with the user (2026-07-07): this stops casual or
bot access, not a determined attacker who reads the page's own JS — an
accepted trade-off for this document specifically because it's what
the user asked to store, not a default this project would pick on its
own for a document containing a home address.

**No website can print silently.** "Print Claim" fills the PDF, uploads
it, records `printed_at`/`filled_pdf_path` on the `claim_tracking` row,
then opens the filled PDF in a hidden iframe and calls the browser's
own `print()` — the OS print dialog still appears and still needs one
click. That is the ceiling for any browser, by design, for any site.

**Lifecycle, restated (supersedes §15's two-stage "checked out"):**
cart → checked out (`claimed=true`) → **printed** (`printed_at` set,
`filled_pdf_path` recorded; requires compensation type + payout method
already chosen) → archived (`mailed=true`, now requires `printed_at`
first). The claim-number input is only rendered once `mailed=true` —
before that it's premature, since Skånetrafiken hasn't responded yet.

**Asked again, directly, 2026-07-07: could personnummer or the
signature be typed into a page field instead of handwritten, even if
never saved to Supabase?** No, and this is deliberate regardless of
where the data would end up. Both stay off every field this app
controls — not because of *where* they'd be stored, but because
auto-filling a government ID number, or capturing a signature image,
is the same category of action as handling a password or payment
credential on someone's behalf: declined even with explicit
authorization, even framed as transient/local-only. Practically:
Personnummer and Underskrift are the two things `claims_template.html`
now calls out explicitly in the "Checked out" section's own hint text,
right where printing happens, as a standing reminder they need a pen.

**Origin and final stop are now always recorded, 2026-07-07 — even at
zero delay.** `scan.py` used to skip any stop with no delay and no
irregular `schedule_relationship`, which meant a trip that departed or
arrived exactly on time (or was first observed mid-route) never got a
confirmed origin/destination time at all — shown as "?" in
claims.html, and the exact cause of the "unconfirmed" chain-breaking
behavior documented in §10/§11. `trip_meta.origin_stop_id` (already
computed by `static_index.py`, just not previously loaded into
`scan.py`) and `final_stop_sequence` are now checked before the
skip, so both endpoints are kept regardless of delay. Everything
in between the two endpoints is still delay-only — recording every
intermediate stop of every scanned trip would multiply live write
volume by roughly the average stops-per-trip count for no benefit to
compensation eligibility (which only ever looks at the final stop),
so that trade-off was deliberately not taken. claims.html's per-stop
drill-down also now flags the final stop's own delay value directly
(🏁), not just where the delay began (⚡).

## 18. Claimed Digitally — a second filing path, 2026-07-08

Requested by the user: Skånetrafiken also accepts some claims filed
directly through their own site/app, with no paper form at all. Print
Claim → mail was the only path claims.html supported; "Claimed
Digitally" is now a parallel alternative, not a replacement.

**Deliberately a separate flag, not an overload of `mailed`.**
`claim_tracking.claimed_digitally`/`claimed_digitally_at`
(`src/migrations/011_claimed_digitally.sql`) exist alongside
`mailed`/`mailed_at` rather than repurposing "mailed" to mean "filed,
however" — `mailed` should keep meaning literally that. Anywhere the
app previously asked "is this claim done" (`renderCheckedOut`'s filter,
`renderAlreadyFiled`'s filter, the claim-number input's gate), the
check is now `mailed OR claimedDigitally`.

**Available independent of the print step.** The "Claimed Digitally"
button appears any time a leg is checked out with both compensation
type and payout method chosen, regardless of whether it's also been
printed — someone might print a copy for their own paper trail but
still file through Skånetrafiken's site, and that's a legitimate
combination, not a contradiction. Same one-way confirmation gate as
"Mark sent in" (`window.confirm`), since it's equally a one-way
archiving action. The archived section now shows which path was used
("Mailed" vs "Filed digitally") so that distinction isn't lost once a
claim is archived.

## 19. Complete journey display — every station, not just delayed ones

Requested by the user 2026-07-08, showing screenshots of Skånetrafiken's
own app: the per-stop drill-down in claims.html only ever showed the
stations `delays` happened to have a row for (see `config.MIN_DELAY_TO_
RECORD_SEC`), so a trip's drill-down could start mid-route (e.g. "seq 8")
instead of at the actual origin — nothing like the complete, every-
station timeline their own app shows.

**Solved without touching Postgres or the storage floor.** The fix that
caused the 2026-07-07 quota incident (only storing meaningfully-delayed
stops) stays exactly as it was — this is a presentation-layer merge, not
a rollback of that fix. `static_index.py` now also stores a `stop_times`
table (every trip's complete scheduled stop-by-stop timetable) during the
same weekly GTFS download it already does — no new Trafiklab API calls,
since `stop_times.txt` is already inside that zip. `build_claims.py`
merges this complete static schedule with whatever sparse live data
exists in `delays`, matched by `stop_sequence` (not `stop_id` — see the
origin-detection fix in §17/scan.py's own note on loop routes revisiting
a stop_id). A station with no live-recorded row is shown as "on time" —
not "unknown" — because the absence of a row is itself a reliable signal
under this policy (anything ≥5 min would have been recorded), not a gap
in knowledge.

## 20. "Not claimable" — replacement-bus journeys, 2026-07-08

Requested by the user as a hard rule, after a real claim (train 11316,
Malmö Hyllie → Helsingborg C, 2026-07-08) was rejected by Skånetrafiken
citing "resalternativ" (alternative route) — an undocumented mechanism
(not found in any of their public terms, the ticket-terms PDF, or the
underlying statute) by which a delay can apparently be judged as
effectively under 20 minutes if an alternative route to the final
destination existed. See the Trafikverket integration doc's findings for
the full research. A replacement bus **is** exactly such an alternative
route — Skånetrafiken is providing it specifically so passengers still
reach their destination despite the train being cancelled/disrupted.

**Decision: any journey whose reason text mentions a replacement bus is
never claimable here, regardless of delay length.** Rather than try to
guess case-by-case whether a specific bus substitution would or wouldn't
survive Skånetrafiken's resalternativ argument, this project treats the
whole category as excluded — consistent with this project's standing
principle (established the same day) of only ever recommending a claim
when the compensation rule fully, confirmably applies, never on an
approximation: a replacement bus injects exactly the kind of uncertainty
that principle exists to filter out.

**Implementation** (`build_compensation.py`'s `_mentions_replacement_bus()`,
shared by `compute_compensation()` for both `compensation.html` and
`claims.html` via `build_claims.py`): matches `reason` against the same
patterns already validated empirically against 45 days of live data while
investigating the rejected claim (`ersättningsbuss`, `buss ... ersätter`,
`ersätter ... tåg`, `buss istället`) — found 198 distinct trips matching in
that window. A matching trip gets `calc: "bus_replaced"` — a third category
alongside `"eligible"` and `"cancelled"`, checked *before* the normal delay
threshold, so even a 60+ minute delay with a replacement bus is excluded.
Still listed (with its delay figure, for visibility — this project's own
"no silent caps" principle) with a distinct 🚌 "Not claimable" chip, never
with a computed deduction amount, and never picked up by `claims.html`'s
`ruleFullyApplies()` auto-suggestion (it already requires `calc ===
"eligible"`).

**Known limitation, accepted deliberately:** text matching over free-form
Swedish alert descriptions is inherently approximate — a phrasing this
project hasn't seen yet could slip through, and a mention of "buss" in an
unrelated context (rare, but not impossible) could over-exclude. Given the
rule's purpose (avoid recommending a claim that's likely to fail on
grounds this project can't verify), a false exclusion is the safer failure
mode than a false inclusion.

## 21. Interactive route map (added 2026-07-08)

Each expanded stops-panel
also renders a Leaflet map (OpenStreetMap tiles, loaded from a CDN — no
API key, no additional Trafiklab calls) with a polyline through every
geolocated stop and a marker per station: dark for the two endpoints,
green/amber/red for intermediate stops scaled by that stop's delay (green
also covers `recorded: false` "on time" stops), with a hover tooltip
showing the station name and its delay. Coordinates ride along on each
stop object (`lat`/`lon`, from `static_index.py`'s `stops` table — the
same source `enrich_with_endpoints()` already used for origin/destination)
rather than a second lookup. Maps are (re)created in `initStopMaps()`,
called at the end of every `renderAll()`, since a full innerHTML re-render
tears down whatever DOM node a previous Leaflet instance was bound to —
there's no way to "reattach" a live map, so a still-expanded panel just
gets a fresh one each time.

## 22. Resolution of the train 11316 rejection — the real cause, and a confirmed 1-2 day registration lag

§20 documents the "replacement bus = not claimable" rule, built after train
11316's rejection cited "resalternativ" — at the time, the best available
theory, since no specific alternative route could be found for that
journey (checked directly: the only other same-day, same-destination
service, train 1022 on route 805, was itself delayed to Helsingborg C by
23.2 min — 1 minute *later* than 11316's own confirmed 08:46:03 arrival,
so switching wouldn't have helped either).

**The real cause, confirmed 2026-07-09 directly by a Skånetrafiken support
agent** (chat transcript, reklamationsnummer `RG2026-07-WZ4T2Y`): the
rejection was an **automatic decision**, and the "resalternativ" wording in
the rejection email is generic template text covering multiple possible
reasons, not a specific finding for this journey. The agent (Michelle)
said outright: *"Resan har identifierats som 18 minuter försenad, vilket
inte berättigar till ersättning"* — Skånetrafiken's own system had this
trip at **18 minutes** delayed (under the 20-min threshold) when the
automatic check ran. On a manual re-check the same day she found **22
minutes** (arrival 08:42) and reopened the case — still short of this
project's own recorded **26.1 minutes** (arrival 08:46:03, per GTFS-RT).

Asked directly whether the first decision was automatic ("var första
besked en automatisk beslut?"), she confirmed: *"Ja, det var det."* Asked
how to avoid this in future, her answer: *"Det är ingenting som du har
gjort fel utan det är något litet strul i systemet bara. Ibland kan det
vara bra att vänta 1-2 dagar innan man ansöker för att alla förseningar
ska hinna registreras i systemet."* — nothing the rider did wrong; their
own system can take **1-2 days** after a trip to finish registering its
delay, and filing before that risks an automatic rejection against a
stale, too-low number.

**This is a third, independent source of delay-figure discrepancy**,
distinct from the two this project already handles:
- `delayApprox`/`finalStopUnconfirmed` (build_dashboard.py) — *this
  project's own* scanner never got a later poll to confirm a final
  number.
- `singleSourceOnly` (trafikverket_merge.py) — a trip only Trafikverket
  saw, never corroborated by Skånetrafiken's own feed.
- **`recentTrip`** (new, `config.SKANETRAFIKEN_REGISTRATION_LAG_DAYS = 2`)
  — *Skånetrafiken's own backend* hasn't finished registering the trip
  yet, confirmed by their own support staff, not inferred. Computed in
  `compute_compensation()`: `(today - trip_date).days <
  SKANETRAFIKEN_REGISTRATION_LAG_DAYS`. Excluded from `ruleFullyApplies()`
  in `claims_template.html` for the same reason as the other two — never
  auto-recommend a claim on a number that hasn't settled — and shown with
  a distinct "⏳ wait before filing" chip in both `claims.html` and
  `compensation.html`, carrying the same real-case explanation in its
  tooltip.

**Practical consequence:** don't file a claim within ~2 days of the trip
even when this project's own data already shows a clear, well-over-20-min
delay — Skånetrafiken's own system may not agree yet, and an early filing
can be auto-rejected on a number that later gets corrected upward once
their system catches up.
