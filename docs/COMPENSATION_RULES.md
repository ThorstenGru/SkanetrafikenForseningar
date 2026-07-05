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

**Not yet built:** an actual compensation-amount calculation (SEK values
per the price-deduction tiers and car/taxi reimbursement caps above) — the
underlying data (final-stop delay, max delay, distance, vehicle type,
Sommarbiljett scope) is now all in place for it, but the calculation itself
hasn't been wired up yet.
