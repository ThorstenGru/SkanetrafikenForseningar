"""Configuration and constants for the Skånetrafiken delay scanner."""

import os
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

# How long detailed history is kept in Postgres before daily housekeeping
# deletes it. Applies uniformly to delays, trip_cancellations, seen_trips,
# missing_trips, alerts, and scan_runs.
RETENTION_DAYS = 45

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
