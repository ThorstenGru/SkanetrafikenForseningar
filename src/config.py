"""Configuration and constants for the Skånetrafiken delay scanner."""

import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

# Always use this explicitly for any human-facing time display — never bare
# dt.astimezone() with no argument. That converts to whatever timezone the
# MACHINE RUNNING THE CODE happens to be set to, which is fine on a
# developer's own PC but silently wrong in GitHub Actions (UTC runners):
# it displayed every stop time 2 hours early in summer (CEST = UTC+2).
# Found 2026-07-06 by comparing the live dashboard against the real
# Skånetrafiken app for the same trip.
LOCAL_TZ = ZoneInfo("Europe/Stockholm")

OPERATOR = "skane"

STATIC_URL_TMPL = "https://opendata.samtrafiken.se/gtfs/{op}/{op}.zip?key={key}"
TRIPUPDATES_URL_TMPL = "https://opendata.samtrafiken.se/gtfs-rt/{op}/TripUpdates.pb?key={key}"
SERVICEALERTS_URL_TMPL = "https://opendata.samtrafiken.se/gtfs-rt/{op}/ServiceAlerts.pb?key={key}"

# Static data changes rarely (timetable updates a few times a year). The static
# API key has a very low quota (60 requests / 30 days), so we refresh weekly,
# not daily, to keep a safe margin.
STATIC_CACHE_MAX_AGE_DAYS = 7

# ---------------------------------------------------------------------------
# Data window -- the single source of truth for "which days exist"
# ---------------------------------------------------------------------------
# This project documents exactly one Sommarbiljett season, not a rolling
# window of "recent" data: 25 June .. 20 August 2026, per the user
# (2026-08-06). Nothing before, nothing after -- both bounds are hard, and
# every query, every page build and every housekeeping pass derives its own
# range from here rather than computing one of its own.
#
# Replaces the previous rolling RETENTION_DAYS = 45, which was actively
# dangerous here rather than merely imprecise: its cutoff advanced one day
# per day, so on 2026-08-10 it would have reached 2026-06-25 and housekeeping
# would have begun DELETING the earliest days of the very season this project
# exists to document -- silently, a day at a time, with the deletions
# recorded as routine successes in housekeeping_runs. A fixed window cannot
# drift into its own data.
WINDOW_START = date(2026, 6, 25)
WINDOW_END = date(2026, 8, 20)

# How long the build and housekeeping workflows keep running after WINDOW_END
# before going quiet for good. Long enough to guarantee at least one final
# build+deploy of the completed season and one final housekeeping pass; short
# enough that this project stops touching Supabase entirely a couple of days
# later. Scanning stops dead at WINDOW_END -- no new data can belong to the
# season after it ends, so there is nothing to poll for.
WINDOW_GRACE_DAYS = 2


def today_local():
    """Today in Europe/Stockholm. Never date.today(), which is UTC on a
    GitHub Actions runner and therefore the PREVIOUS calendar date for the
    last couple of hours of every Stockholm day -- the same bug class
    LOCAL_TZ's own note above describes."""
    return datetime.now(LOCAL_TZ).date()


def window_bounds():
    """(start_date, end_date) for every query and page build.

    `end` is clamped to today so an in-season build never advertises a window
    running into the future, and freezes at WINDOW_END once the season is
    over -- which is what makes the finished site stable rather than
    re-rendering a wider empty range every day."""
    return WINDOW_START, min(WINDOW_END, today_local())


def in_window(d):
    """Is this trip_start_date / traffic_date inside the season at all?
    Used at WRITE time (scan.py) as well as read time -- a row outside the
    window should never reach Postgres in the first place, not just be
    filtered out of the pages afterwards."""
    return WINDOW_START <= d <= WINDOW_END


def window_is_closed(today=None):
    """The season is over: no new data can arrive, so scanning stops."""
    return (today or today_local()) > WINDOW_END


def past_grace_period(today=None):
    """Even the post-season wind-down is done -- building and housekeeping
    stop permanently from here, and this project's Supabase egress goes to
    zero. See docs/RUNBOOK.md, "After the season"."""
    return (today or today_local()) > WINDOW_END + timedelta(days=WINDOW_GRACE_DAYS)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO_ROOT, "data")
STATIC_INDEX_PATH = os.path.join(DATA_DIR, "static_index.sqlite")
# Every trip's full scheduled stop-by-stop timetable (added 2026-07-08 for
# claims.html's complete-journey view) is ~150+ MB for the whole network --
# far past GitHub's 100 MB per-file commit limit. Kept as a separate,
# NEVER-COMMITTED file (see .gitignore), persisted across GH Actions runs
# via actions/cache instead of git, since it only needs to survive between
# workflow runs, not be version-controlled.
STOP_TIMES_CACHE_PATH = os.path.join(DATA_DIR, "stop_times_cache.sqlite")
RAW_STATIC_CACHE_DIR = os.path.join(REPO_ROOT, ".gtfs_static_raw")  # never committed


def database_url():
    """Postgres connection string (Supabase). Set as the DATABASE_URL secret."""
    return get_key("DATABASE_URL")


def get_key(env_var):
    """Read an API key from the environment (GitHub Actions secret)."""
    value = os.environ.get(env_var)
    if not value:
        raise RuntimeError(
            "Saknar API-nyckel: satt miljovariabeln %s (t.ex. via GitHub Actions secret)." % env_var
        )
    return value


def static_key():
    return get_key("TRAFIKLAB_STATIC_KEY")


def realtime_key():
    return get_key("TRAFIKLAB_REALTIME_KEY")


def koda_key():
    """API key for KoDa (Kollektivtrafikens Datalabb), Trafiklab's historical
    GTFS-RT archive — a separate product/key from the live realtime feed,
    used only by backfill_koda.py."""
    return get_key("KODA_API_KEY")


def trafikverket_key():
    """API key for Trafikverket's own open API (api.trafikinfo.trafikverket.se)
    — a completely separate registration/product from Trafiklab, used only
    by scan_trafikverket.py. See docs/TRAFIKVERKET_INTEGRATION.md."""
    return get_key("TRAFIKVERKET_KEY")


TRAFIKVERKET_API_URL = "https://api.trafikinfo.trafikverket.se/v2/data.json"

# CONFIRMED (not just inferred), 2026-07-08, with a real key: TrainAnnouncement
# is a live departure board, not an archive. Querying AdvertisedTrainIdent=1206
# (a real Skåne train) for AdvertisedTimeAtLocation on 2026-06-25 (13 days
# before "today") and on 2026-05-15 (~8 weeks before) both returned zero rows,
# while the same query for "today" returned a full 50+ row stop-by-stop result.
# The API DOES return ~2 weeks of FUTURE schedule per train (also confirmed),
# just no past history beyond a short recent window. There is no way to
# backfill past delays through this endpoint — this integration can only ever
# improve coverage going forward, exactly like Trafiklab's own GTFS-RT (which
# is why backfill_koda.py exists as a *separate* historical product for that
# feed). See docs/TRAFIKVERKET_INTEGRATION.md for the full writeup.
TRAFIKVERKET_ANNOUNCEMENT_LOOKBACK_MIN = 90
TRAFIKVERKET_ANNOUNCEMENT_LOOKAHEAD_HOURS = 4


# Supabase project serving this data — used only by build_claims.py to let
# the built claims.html write directly to Postgres via Supabase's REST API
# (PostgREST), bypassing the need for any server this static site doesn't
# have. The project ref itself isn't sensitive (same one documented in
# project memory/RUNBOOK.md); SUPABASE_ANON_KEY and
# CLAIM_TRACKING_PASSPHRASE are secrets read at build time and embedded
# into the built page — see docs/COMPENSATION_RULES.md §12 for why that's
# an accepted trade-off for this table specifically.
#
# Deliberately soft (returns None, doesn't raise like get_key()) since
# these two are only needed for one optional feature on one of three
# pages — until SUPABASE_ANON_KEY exists as a GH secret (set once the
# claim_tracking migration has been applied), every other page must still
# build and deploy normally. claims.html's own JS degrades gracefully when
# these come through as null (see claims_template.html).
def supabase_anon_key():
    return os.environ.get("SUPABASE_ANON_KEY")


def claim_tracking_passphrase():
    return os.environ.get("CLAIM_TRACKING_PASSPHRASE")


SUPABASE_URL = "https://fwwtrtgefdltfazwcrwa.supabase.co"


# GTFS-RT Alert.Cause / Alert.Effect enum labels (protobuf spec)
CAUSE_LABELS = {
    1: "UNKNOWN_CAUSE",
    2: "OTHER_CAUSE",
    3: "TECHNICAL_PROBLEM",
    4: "STRIKE",
    5: "DEMONSTRATION",
    6: "ACCIDENT",
    7: "HOLIDAY",
    8: "WEATHER",
    9: "MAINTENANCE",
    10: "CONSTRUCTION",
    11: "POLICE_ACTIVITY",
    12: "MEDICAL_EMERGENCY",
}

EFFECT_LABELS = {
    1: "NO_SERVICE",
    2: "REDUCED_SERVICE",
    3: "SIGNIFICANT_DELAYS",
    4: "DETOUR",
    5: "ADDITIONAL_SERVICE",
    6: "MODIFIED_SERVICE",
    7: "OTHER_EFFECT",
    8: "UNKNOWN_EFFECT",
    9: "STOP_MOVED",
    10: "NO_EFFECT",
    11: "ACCESSIBILITY_ISSUE",
}

SCHEDULE_RELATIONSHIP_LABELS = {
    0: "SCHEDULED",
    1: "SKIPPED",
    2: "NO_DATA",
    3: "UNSCHEDULED",
}

TRIP_SCHEDULE_RELATIONSHIP_LABELS = {
    0: "SCHEDULED",
    1: "ADDED",
    2: "UNSCHEDULED",
    3: "CANCELED",
    5: "DUPLICATED",
    6: "DELETED",
}

# GTFS route_type. Skånetrafiken uses the "extended" hierarchical vehicle
# type codes (100s/700s/900s/1000s/1500s), not just the basic 0-7 enum.
# Confirmed present in their feed (2026-07-05): 100 (rail), 700 (bus),
# 900 (tram), 1000 (ferry), 1501 (demand-responsive/Närtrafik).
ROUTE_TYPE_LABELS = {
    0: "TRAM", 1: "METRO", 2: "RAIL", 3: "BUS", 4: "FERRY",
    5: "CABLE_TRAM", 6: "AERIAL_LIFT", 7: "FUNICULAR", 11: "TROLLEYBUS", 12: "MONORAIL",
    100: "RAIL", 109: "RAIL", 400: "METRO",
    700: "BUS", 701: "BUS", 702: "BUS", 704: "BUS", 715: "DEMAND_RESPONSIVE_BUS",
    900: "TRAM", 1000: "FERRY",
    1500: "TAXI", 1501: "DEMAND_RESPONSIVE_BUS",
}


def route_type_label(route_type):
    if route_type is None:
        return "UNKNOWN"
    return ROUTE_TYPE_LABELS.get(route_type, "OTHER")


# Delay-compensation constants, per docs/COMPENSATION_RULES.md (retrieved
# 2026-07-05 from skanetrafiken.se — they can change these without notice).
# Only used by build_compensation.py; the estimate is illustrative, not a
# real claim calculation.
MIN_DELAY_FOR_COMPENSATION_MIN = 20  # below this, no compensation applies at all

# Requested by the user 2026-07-20: a claim worth less than this isn't
# worth listing at all. Checked against the best-case amount across both
# payout paths (voucher price-deduction, or mileage reimbursement) -- see
# compute_compensation()'s own note on why that's the same metric
# claims_template.html's chain-scoring already uses.
MIN_CLAIM_VALUE_SEK = 150

# Confirmed directly by a Skånetrafiken support agent (chat, 2026-07-09,
# reklamationsnummer RG2026-07-WZ4T2Y), not inferred: a claim filed too soon
# after the trip can be auto-rejected against a delay figure their own
# system hasn't finished registering yet. On this specific claim, their
# system showed 18 min (under the 20-min threshold, triggering an automatic
# rejection) when first checked, then 22 min on a manual re-check the same
# day -- still short of this project's own recorded 26.1 min. The agent's
# own words: "Ibland kan det vara bra att vänta 1-2 dagar innan man ansöker
# för att alla förseningar ska hinna registreras i systemet." See
# docs/COMPENSATION_RULES.md for the full writeup.
SKANETRAFIKEN_REGISTRATION_LAG_DAYS = 2

# Below this, a stop-level delay isn't even written to `delays` at all (a
# 2026-07-07 fix -- GTFS-RT reports delay down to the second for completely
# routine timing jitter, which was 94% of the table's rows and bytes for
# zero compensation-relevant value: only ~1.8 MB of ~896 MB actually fell in
# the >=20-min eligible range). Origin/final stops and irregular
# (SKIPPED/etc.) stops are still always recorded regardless of this floor --
# see scan.py's is_endpoint/is_irregular handling.
MIN_DELAY_TO_RECORD_SEC = 300  # 5 minutes

SOMMARBILJETT_PRICE_SEK = 595
SOMMARBILJETT_DIVISOR = 40  # "single trips" the ticket price is divided by for price-deduction purposes
SOMMARBILJETT_SINGLE_TRIP_PRICE_SEK = SOMMARBILJETT_PRICE_SEK / SOMMARBILJETT_DIVISOR  # 14.875 kr


def sommarbiljett_purchased_at():
    """Hard cutoff (2026-07-06, per the user): no trip before the instant
    this specific ticket was purchased can ever be claimed under it — the
    rider didn't hold a valid ticket yet. compute_compensation() in
    build_compensation.py excludes any such trip entirely from both
    compensation.html and claims.html, not just from the $ calculation.

    Read from an env var (ISO 8601 with offset, e.g.
    "2026-06-25T11:38:00+02:00") rather than hardcoded here, deliberately —
    this repo is public, and a specific purchase timestamp is the user's
    personal data, not project configuration. Raises if unset: a build
    that can't apply this cutoff must fail loudly, not silently include
    ineligible trips. See docs/COMPENSATION_RULES.md §13."""
    from datetime import datetime
    return datetime.fromisoformat(get_key("SOMMARBILJETT_PURCHASED_AT"))

def claim_window():
    """The window every claim-facing page (compensation, claims, mileage)
    builds over: the season, additionally clamped so it can never reach back
    before the ticket was actually bought.

    Both bounds already coincide today (the ticket was bought on
    WINDOW_START), but they are separate facts -- the season is a project
    scope decision, the purchase instant is the user's own and lives in a
    secret because this repo is public. Keeping the clamp means a
    re-purchased or differently-dated ticket can't silently pull ineligible
    days onto a claim page. See sommarbiljett_purchased_at() and
    docs/COMPENSATION_RULES.md §13."""
    start, end = window_bounds()
    return max(start, sommarbiljett_purchased_at().date()), end


VOUCHER_BONUS = 1.5  # +50% for choosing a voucher code (värdekod) instead of cash — price-deduction only (section 3); no such bonus is documented for alternative-transport reimbursement (section 4)

CAR_RATE_SEK_PER_KM = 2.5  # Swedish Tax Agency's tax-free mileage rate, 25 kr/mil
ALT_TRANSPORT_CAP_SEK = 2960  # max per journey for car/taxi/other-operator reimbursement, effective 2026-01-01


# "Reasonable claim chain" page (build_claims.py): two trips are treated as
# happening at the same physical place — close enough that one could
# realistically have walked from one stop to the other — if their stops are
# within this radius. Covers cases like a bus stop and a train station in
# the same small town having different stop_ids. Not a routing distance,
# just straight-line (haversine).
CLAIM_CHAIN_CONNECT_RADIUS_M = 600


def price_deduction_pct(delay_min):
    """Price-deduction tier for a given final-destination delay, in minutes."""
    if delay_min >= 60:
        return 1.00
    if delay_min >= 40:
        return 0.75
    if delay_min >= 20:
        return 0.50
    return 0.0
